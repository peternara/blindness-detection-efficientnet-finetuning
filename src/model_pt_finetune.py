import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
import torchvision
from torchvision import transforms, models
import matplotlib.pyplot as plt
from sklearn.metrics import cohen_kappa_score
import time
import copy

from data_aug import *
from config import *
import utils

device = utils.getDevice()


def train_model(model, dataloaders, dataset_sizes, criterion, optimizer, scheduler, num_epochs=25):
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.
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

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)
                optimizer.zero_grad()
                with torch.set_grad_enabled(phase == "train"):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)
                    if phase == "train":
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
            epoch_loss = running_loss/dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]
            print("{} Loss: {:.4f} Acc: {:.4f}".format(
                phase, epoch_loss, epoch_acc))

            if phase == "val" and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
        print()

    time_elapsed = time.time() - since
    print("Training copmlete in {:.0f}m{:.0f}s".format(
        time_elapsed//60, time_elapsed % 60))
    print("Best val Acc: {:4f}".format(best_acc))

    model.load_state_dict(best_model_wts)
    return model


if __name__ == "__main__":
    data_transform = transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    dataset = BD_Dataset(transform=data_transform)

    train_size = int((1-VALIDATION_FRACTION)*len(dataset))
    validation_size = len(dataset) - train_size
    train_dataset, validation_dataset = torch.utils.data.random_split(
        dataset, [train_size, validation_size])

    dataset_sizes = {"train": train_size, "val": validation_size}
    dataloaders = {
        "train": DataLoader(
            train_dataset, batch_size=4, shuffle=True, num_workers=4),
        "val": DataLoader(
            validation_dataset, batch_size=4, shuffle=True, num_workers=4)}

    # load pre trained model
    model_ft = models.resnet50(pretrained=True)
    num_ftrs = model_ft.fc.in_features
    model_ft.fc = nn.Linear(num_ftrs, len(dataset.class_labels))

    model_ft = model_ft.to(device)
    criterion = nn.CrossEntropyLoss()

    optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.01, momentum=0.9)

    exp_lr_scheduler = optim.lr_scheduler.StepLR(
        optimizer_ft, step_size=7, gamma=0.1)

    model_ft = train_model(model_ft, dataloaders, dataset_sizes, criterion,
                           optimizer_ft, exp_lr_scheduler, 100)

    torch.save(model_ft, "finetuned_resnet50.pt")