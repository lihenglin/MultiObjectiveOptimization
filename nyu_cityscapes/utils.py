import torch
import torch.nn as nn
import torch.nn.functional as F

mask = None

def model_fit(x_pred, x_output, task_type, dataset='NYUv2'):
    device = x_pred.device
    
    binary_mask = (torch.sum(x_output, dim=1) != 0).float().unsqueeze(1).to(device)

    if task_type in ['semantic', 'segment_semantic']:
        # semantic loss: depth-wise cross entropy
        ignore_index = 255 if dataset == 'Taskonomy' else -1
        loss = F.nll_loss(x_pred, x_output, ignore_index=ignore_index)

    if task_type in ['depth', 'depth_zbuffer', 'keypoints2d', 'edge_texture']:
        # depth loss: l1 norm
        loss = torch.sum(torch.abs(x_pred - x_output) * binary_mask) / torch.nonzero(binary_mask, as_tuple=False).size(0)

    if task_type == 'normal':
        # normal loss: dot product
        loss = 1 - torch.sum((x_pred * x_output) * binary_mask) / torch.nonzero(binary_mask, as_tuple=False).size(0)

    return loss

class ConfMatrix(object):
    def __init__(self, num_classes):
        self.num_classes = num_classes
        self.mat = None

    def update(self, pred, target):
        with torch.no_grad():
            n = self.num_classes
            if self.mat is None:
                self.mat = torch.zeros((n, n), dtype=torch.int64, device=pred.device)
            with torch.no_grad():
                k = (target >= 0) & (target < n)
                inds = n * target[k].to(torch.int64) + pred[k]
                self.mat += torch.bincount(inds, minlength=n ** 2).reshape(n, n)

    def get_metrics(self):
        with torch.no_grad():
            h = self.mat.float()
            acc = torch.diag(h).sum() / h.sum()
            iu = torch.diag(h) / (h.sum(1) + h.sum(0) - torch.diag(h))
            return torch.mean(iu).item(), acc.item()


def depth_error(x_pred, x_output, dataset='NYUv2'):
    with torch.no_grad():
        device = x_pred.device
        binary_mask = (torch.sum(x_output, dim=1) != 0).unsqueeze(1).to(device)
        if mask is not None:
            binary_mask *= (mask.int() == 1)
        x_pred_true = x_pred.masked_select(binary_mask)
        x_output_true = x_output.masked_select(binary_mask)
        abs_err = torch.abs(x_pred_true - x_output_true)
        rel_err = torch.abs(x_pred_true - x_output_true) / x_output_true
        return (torch.sum(abs_err) / torch.nonzero(binary_mask, as_tuple=False).size(0)).item(), \
               (torch.sum(rel_err) / torch.nonzero(binary_mask, as_tuple=False).size(0)).item()


def normal_error(x_pred, x_output, dataset='NYUv2'):
    with torch.no_grad():
        binary_mask = (torch.sum(x_output, dim=1) != 0)
        if mask is not None:
            binary_mask *= (mask[:,0,:,:].int() == 1)
        error = torch.acos(torch.clamp(torch.sum(x_pred * x_output, 1).masked_select(binary_mask), -1, 1))#.detach().cpu().numpy()
    #     error = np.degrees(error)
        error = torch.rad2deg(error)
        return torch.mean(error).item(), torch.median(error).item(), \
               torch.mean((error < 11.25)*1.0).item(), torch.mean((error < 22.5)*1.0).item(), \
               torch.mean((error < 30)*1.0).item()
    
   