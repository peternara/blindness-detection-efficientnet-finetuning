from datetime import datetime
import torch
from sklearn.metrics import cohen_kappa_score
import scipy as sp
import numpy as np
from functools import partial
import torch


def getDevice():
    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def get_model_stamp():
    return datetime.now().strftime('%Y-%m-%d-%H-%M-%S')


def get_actual_predictions(preds, coeff=[0.5, 1.5, 2.5, 3.5]):
    device = getDevice()
    actual_preds = torch.zeros(preds.shape, device=device)
    for i, p in enumerate(preds):
        if p < coeff[0]:
            ap = 0
        elif p < coeff[1]:
            ap = 1
        elif p < coeff[2]:
            ap = 2
        elif p < coeff[3]:
            ap = 3
        else:
            ap = 4
        actual_preds[i] = torch.tensor(ap, device=device, dtype=torch.float)
    return actual_preds


class OptimizedRounder(object):
    def __init__(self):
        self.coef_ = 0

    def _kappa_loss(self, coef, X, y):
        X_p = np.copy(X)
        for i, pred in enumerate(X_p):
            if pred < coef[0]:
                X_p[i] = 0
            elif pred >= coef[0] and pred < coef[1]:
                X_p[i] = 1
            elif pred >= coef[1] and pred < coef[2]:
                X_p[i] = 2
            elif pred >= coef[2] and pred < coef[3]:
                X_p[i] = 3
            else:
                X_p[i] = 4

        ll = cohen_kappa_score(y, X_p, weights='quadratic')
        return -ll

    def fit(self, X, y):
        loss_partial = partial(self._kappa_loss, X=X, y=y)
        initial_coef = [0.5, 1.5, 2.5, 3.5]
        self.coef_ = sp.optimize.minimize(
            loss_partial, initial_coef, method='nelder-mead')

    def predict(self, X, coef):
        X_p = np.copy(X)
        for i, pred in enumerate(X_p):
            if pred < coef[0]:
                X_p[i] = 0
            elif pred >= coef[0] and pred < coef[1]:
                X_p[i] = 1
            elif pred >= coef[1] and pred < coef[2]:
                X_p[i] = 2
            elif pred >= coef[2] and pred < coef[3]:
                X_p[i] = 3
            else:
                X_p[i] = 4
        return X_p

    def coefficients(self):
        return self.coef_['x']


import time
import copy
from sklearn.metrics import cohen_kappa_score

def train_model(model, dataloaders, dataset_sizes, criterion, optimizer, scheduler, num_epochs=25, model_name = "temp.pt"):
    device = getDevice()
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_kappa_score = -float("inf")
    for epoch in range(num_epochs):
        print("Epoch{}/{}".format(epoch, num_epochs-1))
        print("-"*10)
        for phase in ["train", "val"]:
            if phase == "train":
                scheduler.step()
                model.train()
            else:
                model.eval()

            running_loss = 0.
            running_corrects = 0.

            predictions_all = torch.empty(size=(0,), device=device)
            labels_all = torch.empty(size=(0,), device=device)
            curr_batch = -1
            for inputs, labels in dataloaders[phase]:
                curr_batch += 1
                if curr_batch % 10 == 0:
                    print("\tBatch: ", curr_batch)

                inputs = inputs.to(device, dtype=torch.float)
                labels = labels.to(device, dtype=torch.float)
                labels = labels.view(-1, 1)
                optimizer.zero_grad()
                with torch.set_grad_enabled(phase == "train"):
                    outputs = model(inputs)
                    loss = criterion(outputs, labels)
                    if phase == "train":
                        loss.backward()
                        optimizer.step()

                    actual_preds = get_actual_predictions(outputs[:, 0])
                    predictions_all = torch.cat(
                        (predictions_all, actual_preds), 0)
                    labels_all = torch.cat((labels_all, labels[:, 0]), 0)

                batch_loss = loss.item() * inputs.size(0)
                running_loss += batch_loss
                batch_corrects = torch.sum(actual_preds == labels[:, 0])
                running_corrects += batch_corrects
                if curr_batch % 10 == 0:
                    print("\t\tBatch loss: ", batch_loss)
                    print("\t\tBatch corrects: ", batch_corrects)
            epoch_loss = running_loss/dataset_sizes[phase]
            epoch_acc = running_corrects.double()*100 / dataset_sizes[phase]
            epoch_kappa_score = cohen_kappa_score(
                predictions_all.tolist(), labels_all.tolist(), weights="quadratic")
            print("{} Loss: {:.4f} Acc: {:.4f} Kappa: {:.4f}".format(
                phase, epoch_loss, epoch_acc, epoch_kappa_score))

            if phase == "val" and epoch_kappa_score > best_kappa_score:
                best_kappa_score = epoch_kappa_score
                best_model_wts = copy.deepcopy(model.state_dict())
                torch.save(model, model_name)
        print()

    time_elapsed = time.time() - since
    print("Training copmlete in {:.0f}m{:.0f}s".format(
        time_elapsed//60, time_elapsed % 60))
    print("Best val kappa score: {:4f}".format(best_kappa_score))

    model.load_state_dict(best_model_wts)
    return model


if __name__ == "__main__":
    scores = [0.3, 1.67, 2.3, 0.6, 0.75, 2.45, 3.2, 3.3, 3.7, 8, 0.3, 1.67, 2.3, 0.6,
              0.75, 2.45, 3.2, 3.3, 3.7, 8, 0.3, 1.67, 2.3, 0.6, 0.75, 2.45, 3.2, 3.3, 3.7, 8]
    target = [0, 2, 2, 0, 1, 3, 2, 4, 4, 4, 0, 2, 2, 0,
              1, 3, 2, 4, 4, 4, 0, 2, 2, 0, 1, 3, 2, 4, 4, 4]
    optR = OptimizedRounder()
    optR.fit(scores, target)

    coeff = optR.coefficients()
    print("Learned coeff: ", coeff)

    preds = optR.predict(scores, coeff)
    correct = sum(np.array(preds) == np.array(target))
    print(correct, len(scores))
