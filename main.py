'''Train CIFAR10 with PyTorch.'''
import torch, torch.nn as nn, torch.optim as optim, torch.nn.functional as F, torch.backends.cudnn as cudnn  
import torchvision, torchvision.transforms as transforms
import os, argparse, yaml, math, numpy as np
from model import build_model


# Training
def train(epoch, config):
    print('\nEpoch: %d' % epoch)
    net.train()
    train_loss = 0
    correct = 0
    total = 0
    train_losses = [] 
    train_acc = [] 
    for batch_idx, (inputs, targets) in enumerate(trainloader):
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        outputs = net(inputs)
        loss = criterion(outputs, targets)
        loss.backward()
        if config["grad_clip"]: nn.utils.clip_grad_value_(net.parameters(), clip_value=config["grad_clip"]) 
        optimizer.step()

        train_loss += loss.item()
        train_losses.append(train_loss)
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item() 

        train_acc.append(100.*correct/total) 
        print('Batch_idx: %d | Train Loss: %.3f | Train Acc: %.3f%% (%d/%d)'% (batch_idx, train_loss/(batch_idx+1), 100.*correct/total, correct, total)) 

    
# Testing 
def test(epoch, config, savename):
    global best_acc
    net.eval()
    test_loss = 0
    test_losses = [] 
    test_acc = [] 
    correct = 0
    total = 0
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            test_losses.append(test_loss)
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item() 
            test_acc.append(100.*correct/total) 
            print('Batch_idx: %d | Test Loss: %.3f | Test Acc: %.3f%% (%d/%d)'% ( batch_idx, test_loss/(batch_idx+1), 100.*correct/total, correct, total)) 


    # Save checkpoint.
    acc = 100.*correct/total
    if acc > best_acc: 
        print('Saving..')
        state = {
            'net': net.state_dict(),
            'acc': acc,
            'epoch': epoch,
            'config': config
        }
        torch.save(state, os.path.join('./summaries/', savename, 'checkpoint.pth'))
        best_acc = acc


if __name__ == '__main__': 

    parser = argparse.ArgumentParser(description='PyTorch CIFAR10 Training')
    parser.add_argument('--config', default='resnet_configs/config.yaml', type=str, help='path to config file for resnet architecture') 
    parser.add_argument('--resnet_architecture', default='best_model', type=str, help='name of resnet architecture from config') 

    args = parser.parse_args()

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    best_acc = 0  # best test accuracy
    start_epoch = 0  # start from epoch 0 or last checkpoint epoch 

    # Model
    print('==> Building model..')
    config=None 
    with open(args.config, "r") as stream:
        try: config = yaml.safe_load(stream) 
        except yaml.YAMLError as exc: print(exc) 

    config=config[args.resnet_architecture]
    
    exp = args.resnet_architecture 

    # Data
    print('==> Preparing data..')
    train_trans = [transforms.ToTensor()]
    test_trans = [transforms.ToTensor()]
    
    additional_train_trans = []
    if config["data_augmentation"]:
        train_trans.append(transforms.RandomCrop(32, padding=4))
        train_trans.append(transforms.RandomHorizontalFlip())
    if config["data_normalize"]: 
        train_trans.append(transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))) 
        test_trans.append(transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))) 
    transform_train = transforms.Compose(train_trans) 
    transform_test = transforms.Compose(test_trans) 
    trainset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform_train)
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=config["batch_size"], shuffle=True, num_workers=config["num_workers"])
    testset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True, transform=transform_test)
    testloader = torch.utils.data.DataLoader(testset, batch_size=int(config["batch_size"]/4), shuffle=False, num_workers=config["num_workers"])

    classes = ('plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck')
    
    net, total_params = build_model(config=config) 
    config['total_params'] = total_params 
    print(net)
    print('Total Parameters: ', total_params) 

    if total_params > 5_000_000: 
        print("===============================")
        print("Total parameters exceeding 5M") 
        print("===============================")
        exit()
    # exit()


    net = net.to(device)
    if device == 'cuda':
        net = torch.nn.DataParallel(net)
        cudnn.benchmark = True

    """
    Weight initialization for ResNet 
    """
    if ("weights_init_type" in config): 
        def init_weights(m, type='default'): 
            if (isinstance(m, nn.Linear) or isinstance(m, nn.Conv2d)) and hasattr(m, 'weight'): 
                if type == 'xavier_uniform_': torch.nn.init.xavier_uniform_(m.weight.data)
                elif type == 'normal_': torch.nn.init.normal_(m.weight.data, mean=0, std=0.02)
                elif type == 'xavier_normal': torch.nn.init.xavier_normal(m.weight.data, gain=math.sqrt(2))
                elif type == 'kaiming_normal': torch.nn.init.kaiming_normal(m.weight.data, a=0, mode='fan_in')
                elif type == 'orthogonal': torch.nn.init.orthogonal(m.weight.data, gain=math.sqrt(2))
                elif type == 'default': pass 
        net.apply(lambda m: init_weights(m=m, type=config["weights_init_type"])) 

    if config["resume_ckpt"]:        
        # Load checkpoint.
        print('==> Resuming from checkpoint..')
        checkpoint = torch.load(config["resume_ckpt"])
        net.load_state_dict(checkpoint['net'])
        best_acc = checkpoint['acc']
        start_epoch = checkpoint['epoch']
    criterion = nn.CrossEntropyLoss()

    if config["optim"] == 'sgd': optimizer = optim.SGD(net.parameters(), lr=config["lr"], momentum=config["momentum"], weight_decay=config["weight_decay"]) 
    if config["optim"] == 'adam': optimizer = optim.Adam(net.parameters(), lr=config["lr"], weight_decay=config["weight_decay"])   
    if config["lr_sched"] == 'CosineAnnealingLR': scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=200) # Good 
    

    for epoch in range(start_epoch, config["max_epochs"]): 
        train(epoch, config) 
        test(epoch, config, savename=exp) 
        scheduler.step()
