'''
THIS FILE CONTAINS CODE TO EVALUATE THE SAVED RESNET-50 MODEL ON THE TEST SET.

CREDITS: Much of this code was selectively borrowed and adapted from: https://pytorch.org/tutorials/beginner/finetuning_torchvision_models_tutorial.html
'''
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
from torchvision import datasets, models, transforms
import matplotlib.pyplot as plt
import time
import os
import cv2
import copy
%matplotlib inline
from sklearn.feature_extraction.image import extract_patches_2d
from sklearn.model_selection import train_test_split
from sklearn.model_selection import KFold,StratifiedKFold
from sklearn.metrics import roc_auc_score
import torch
from torch.utils.data import TensorDataset, DataLoader,Dataset
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import torchvision.transforms as transforms
import torch.optim as optim
from torch.optim import lr_scheduler
import torch.backends.cudnn as cudnn
import time
import tqdm
import random
from PIL import Image
train_on_gpu = True
from torch.utils.data.sampler import SubsetRandomSampler
from torch.optim.lr_scheduler import StepLR, ReduceLROnPlateau, CosineAnnealingLR
try:
    import torchbearer
except:
    !pip install torchbearer
    import torchbearer
from torchbearer import Trial
import scipy
import scipy.special
import bagnets.pytorchnet
print("[libraries successfully installed...]")

# Top level data directory. Here we assume the format of the directory conforms to the ImageFolder structure
data_dir = './flowers_tvtsplit/'

# Save our result (model checkpoints, loss_acc data, plots)to this directory
saved_model_dir = './model_performance_results/resnet50_baseline_results/'

model_name = 'resnet50'

# Number of classes in  the dataset
num_classes = 5

# Batch size for training (standardized to BagNet baseline)
batch_size = 32

# Flag for feature extracting. When False, we finetune the whole model, when True we only update the reshaped layer params
feature_extract = True

#-------------------- Some Helper Functions ---------------------------
def set_parameter_requires_grad(model, feature_extracting):
    """
    This function sets all parameters of model to False, which means we don't fine
    tune all parameters but only feature extract and compute gradients
    for newly initialized layer.
    """
    if feature_extracting:
        for param in model.parameters():
            param.requires_grad = False

def initialize_model(model_name, num_classes, feature_extract, use_pretrained=True):
    """
    This function initializes these variables which will be set in this
    if statement. Each of these variables is model specific.
    """
    model_ft = None

    if model_name == "bagnet":
        model_ft = bagnets.pytorchnet.bagnet33(pretrained=use_pretrained)
    if model_name == "resnet":
        model_ft = models.resnet50(pretrained=use_pretrained)

    set_parameter_requires_grad(model_ft, feature_extract)

    # Change the last layer
    num_ftrs = model_ft.fc.in_features
    model_ft.fc = nn.Linear(num_ftrs, num_classes)

    return model_ft

#--------------------- Load test datasets ------------------------------
data_transforms = {
    "train": transforms.Compose([
        transforms.RandomResizedCrop(224),  # resize the image to 224*224 pixels
        transforms.CenterCrop(224),  # crop the image to 224*224 pixels about the center
        transforms.RandomHorizontalFlip(),  # convert the image to PyTorch Tensor data type
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    # Just normalization for validation
    "val": transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    "test": transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

print("Initializing Datasets and Dataloaders...")

# Create training and validation datasets
train_data = torchvision.datasets.ImageFolder(data_dir + "train/", data_transforms["train"])
val_data = torchvision.datasets.ImageFolder(data_dir + "val/", data_transforms["val"])
test_data = torchvision.datasets.ImageFolder(data_dir + "test/", data_transforms["test"])

# Create training and validation dataloaders
dataloaders_dict = {"train": torch.utils.data.DataLoader(train_data, batch_size=batch_size,
                    shuffle=True, num_workers=2),
                    "val": torch.utils.data.DataLoader(val_data, batch_size=batch_size,
                    shuffle=False, num_workers=2),
                    "test": torch.utils.data.DataLoader(test_data, batch_size=batch_size,
                    shuffle=False, num_workers=2)}

train_loader = dataloaders_dict['train']
val_loader = dataloaders_dict['val']
test_loader = dataloaders_dict['test']

#--------------------- Load and modify models ------------------------------
model_ft_resnet = initialize_model(model_name, num_classes, feature_extract, use_pretrained=True)
model_ft_resnet = model_ft_resnet.to(device)

print("Params to learn:")
if feature_extract:
    params_to_update = []
    for name, param in model_ft_resnet.named_parameters():
        if param.requires_grad == True:
            params_to_update.append(param)
            print("\t",name)
else:
    for name,param in model_ft_resnet.named_parameters():
        if param.requires_grad == True:
            print("\t",name)

# Observe that all parameters are being optimized
optimizer_ft_resnet = optim.SGD(params_to_update, lr=0.001, momentum=0.9)

# Setup the loss fxn
print("[Using CrossEntropyLoss ...]")
criterion = nn.CrossEntropyLoss()

#--------------- Load saved weights --------------------------------
checkpoint = torch.load(saved_model_dir + "resnet50_baseline_model.pth", map_location=device)
model_ft_resnet.load_state_dict(checkpoint['model_resnet50_state_dict'])
optimizer_ft_resnet.load_state_dict(checkpoint['optimizer_resnet50_state_dict'])
print("--------Saved resnet50 weights loaded--------------------")

#--------------- Investigate performance on test datasets ----------

print("--------Investigate performance on test datasets---------")
trial = Trial(model_ft_resnet, optimizer_ft_resnet, criterion, metrics=['loss', 'accuracy']).to(device)
trial.with_generators(train_loader, val_generator=val_loader, test_generator=test_loader)
predictions = trial.predict()
predicted_classes = predictions.argmax(1).cpu()


#--------------- Some model performance visualizations & stats ----------
'''
CREDITS: Code adapted from tutorial: https://pytorch.org/tutorials/beginner/blitz/cifar10_tutorial.html#sphx-glr-beginner-blitz-cifar10-tutorial-py
'''
# Function to show an image
def imshow(img):
    img = img / 2 + 0.5     # unnormalize
    npimg = img.numpy()
    plt.imshow(np.transpose(npimg, (1, 2, 0)))
    plt.show()

# Define classes
classes = ('daisy', 'dandelion', 'rose', 'sunflower', 'tulip')

# Show ground truth (4 images with labels)
dataiter = iter(test_loader)
images, labels = dataiter.next()
print(labels)
imshow(torchvision.utils.make_grid(images))
print('GroundTruth: ', ' '.join('%5s' % classes[labels[j]] for j in range(4)))

# Check class prediction accuracies
class_correct = list(0. for i in range(5))
class_total = list(0. for i in range(5))
with torch.no_grad():
    for data in test_loader:
        images, labels = data
        images = images.to(device)
        labels = labels.to(device)
        outputs = model_ft_resnet(images)
        _, predicted = torch.max(outputs, 1)
        c = (predicted == labels).squeeze()
        if c.size()[0] == 4:
            for i in range(4):
                label = labels[i]
                class_correct[label] += c[i].item()
                class_total[label] += 1


for i in range(5):
    print('Accuracy of %5s : %2d %%' % (
        classes[i], 100 * class_correct[i] / class_total[i]))
