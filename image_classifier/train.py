# This app trains a new network on a dataset and saves the model as a checkpoint
# This file is part of the Udacity Own Image Classifier Project
# Author: Jacques Mahe, October 2019
# Launch: 
#  python train.py  ./flowers --arch VGG --gpu --save_dir ./output/VGG_checkpoint.pthS
#  python train.py  ./flowers --arch  VGG --gpu --save_dir ./output/VGG_checkpoint.pth --load_dir ./output/VGG_checkpoint.pth
#  python predict.py ./flowers/valid/28/image_05265.jpg output/checkpoint.pth --category_names cat_to_name.json --gpu
import argparse
import os, sys, errno
import train_class
from train_class import TrainingModel

# Use argparse tp parse application parameters
parser = argparse.ArgumentParser(description='Train a new netwrork on a dataset')
parser.add_argument('train_dir', type=str, 
                    help='directory where image are stored')
parser.add_argument('--save_dir', type=str, default="",
                    help='file name to save the trained model checkpoint')
parser.add_argument('--load_dir', type=str, default="",
                    help='file name to load a previously saved model checkpoint')
parser.add_argument('-a', '--arch', type=str, default="VGG",
                    help='Pre-trained model base (Choose between VGG, D*enseNet, ShuffleNet, AlexNet and GoogleNet)')
parser.add_argument('-l', '--learning_rate', type=float, default=0.001,
                    help='Training learning rate (default: 0.001)')
parser.add_argument('-u', '--hidden_units', type=int, default=512,
                    help='Number of hidden units')
parser.add_argument('-d', '--dropouts', type=float, default=0.5,
                    help='Nb dropouts to avoid overfitting')
parser.add_argument('-e', '--epochs', type=int, default=10,
                    help='Number of epochs (i.e training passes)')
parser.add_argument('-g', '--gpu', action='store_true',
                    help='Enable GPU (CUDA) processing if available')
parser.add_argument('-t', '--test', action='store_true',
                    help='Test model after training (use --load_dir to load a previously saved model checkpoint)')
args = parser.parse_args()

# Check trainig path
train_dir = args.train_dir
if os.path.isdir(os.path.join(os.getcwd(), train_dir)):
	train_dir = os.path.join(os.getcwd(), train_dir)
if not os.path.isdir(train_dir): 
	print(f"Invalid trainingg directory: {args.train_dir}")
	sys.exit(-1)
print(f"Train/test dir: {train_dir}")

# Create our learning/trained model (see train_util.py)
model = TrainingModel(train_dir)
if not model.is_valid_train_dir():
	print(f"Invalid trainingg directories: {model.train_dir} or {model.valid_dir}")
	sys.exit(-2)

# Init training loaders if traning required
if args.epochs > 0:
	model.init_loaders()

# Initialize model or load it from checkpint
if args.load_dir == "":
	print(f"Pre-trained model base: {args.arch}")
	print(f"Learning rate: {args.learning_rate}")
	print(f"Hidden units: {args.hidden_units}")
	print(f"Dropouts: {args.dropouts}")
	print(f"Epochs: {args.epochs}")

	if not model.init(args.arch, args.hidden_units, args.learning_rate, 112, args.dropouts):
		print("Invalid pre-trained modep: choose between VGG, DenseNet, ShuffleNet, AlexNet and GoogleNet ")
		sys.exit(-3)
else:

	print(f"loading pre-trained mode from {args.load_dir}")
	model.load_checkpoint(args.load_dir, args.gpu)

# Train if requested
print(f"Use GPU: {'yes' if args.gpu else 'no'}")
if args.epochs > 0 and not model.train(args.gpu, args.epochs):
	sys.exit(-4)

# Save trained model if requested
if args.epochs > 0 and args.save_dir != "":
	print(f"Saving model checkpoint: {args.save_dir}")
	model.save_checkpoint(args.save_dir)

# Test model if requested
if args.test:
	print("Testing model")
	model.test(train_dir, args.gpu)
