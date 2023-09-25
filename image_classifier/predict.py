# This app loads a trained network model and prodicts a flower name
# This file is part of the Udacity Own Image Classifier Project
# Author: Jacques Mahe, October 2019
import argparse
import os, sys, errno
import train_class
from train_class import TrainingModel
import json

# Use argparse tp parse application parameters
parser = argparse.ArgumentParser(description='Predicts a floawer name from a picture')
parser.add_argument('path_to_image', type=str, 
                    help='image to load (JPEG, PNG, etc...)')
parser.add_argument('checkpoint', type=str, 
                    help='file name to load a previously saved model checkpoint')
parser.add_argument('-g', '--gpu', action='store_true',
                    help='Enable GPU (CUDA) processing if available')
parser.add_argument('-c', '--category_names', nargs='?', default="",
                    help='JSON file mapping categories to names')
parser.add_argument('-t', '--top_k', nargs='?', type=int, default=5,
                    help='Top K probabilities to display')
args = parser.parse_args()

if not os.path.isfile(args.path_to_image):
	print(f"Error: image file not found: {args.path_to_image}")
	sys.exit(-1)

print(f"Predicting flower type for {args.path_to_image}")

if not os.path.isfile(args.checkpoint):
	print(f"Error: checkpoint file not found: {args.checkpoint}")
	sys.exit(-2)

# Create our learning/trained model (see train_util.py)
model = TrainingModel("")
if not model.load_checkpoint(args.checkpoint, args.gpu):
	print(f"Error: could not load checkpoint {args.checkpoint}")
	sys.exit(-3)

probs, classes = model.predict(args.path_to_image, args.gpu, args.top_k)
if len(args.category_names) > 0:
	if not os.path.isfile(args.category_names):
		print(f"Error: categories file not found: {args.category_names}")
		sys.exit(-4)
	with open(args.category_names, 'r') as f:
	    cat_to_name = json.load(f)
	flower_names = [cat_to_name[c] for c in classes]
	for i in range(args.top_k):
		print(f"{flower_names[i]} : {probs[i]*100:.2f}%")
else:
	for i in range(args.top_k):
		print(f"{classes[i]} : {probs[i]*100:.2f}%")
