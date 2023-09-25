import os
import numpy as np
import torch
from torch import nn
from torch import optim
import torch.nn.functional as F
from torchvision import datasets, transforms, models
from collections import OrderedDict
from PIL import Image

class TrainingModel:
	train_dir = ""
	valid_dir = ""
	loader_initialized = False

	def __init__(self, data_dir):
		self.train_dir = os.path.join(data_dir, 'train')
		self.valid_dir = os.path.join(data_dir, 'valid')
		self.loader_initialized = False
		self.model_initialized = False

	def is_valid_train_dir(self):
		return os.path.isdir(self.train_dir) and os.path.isdir(self.valid_dir)

	def init_loaders(self):

		if not self.is_valid_train_dir():
			print("Invalid training or validation directories")
			return False

		train_transforms = transforms.Compose([
			transforms.RandomRotation(30),
			transforms.RandomResizedCrop(224),
			transforms.RandomHorizontalFlip(),
			transforms.ToTensor(),
			transforms.Normalize(
				[0.485, 0.456, 0.406],
				[0.229, 0.224, 0.225]
			)
		])

		validation_transforms = transforms.Compose([
			transforms.Resize(255),
			transforms.CenterCrop(224),
			transforms.ToTensor(),
			transforms.Normalize(
				[0.485, 0.456, 0.406],
				[0.229, 0.224, 0.225]
			)
		])

		# Load the datasets with ImageFolder
		train_image_datasets = datasets.ImageFolder(self.train_dir, transform=train_transforms)
		validation_image_datasets = datasets.ImageFolder(self.valid_dir, transform=validation_transforms)
		self.class_to_idx = train_image_datasets.class_to_idx

		# Using the image datasets and the trainforms, define the dataloaders
		self.trainloader = torch.utils.data.DataLoader(train_image_datasets, batch_size=64, shuffle=True)
		self.validationloader = torch.utils.data.DataLoader(validation_image_datasets, batch_size=64, shuffle=False)
		self.loader_initialized = True
		return True
	
	def init(self, base_model_name, hidden_units, learn_rate = 0.001, output_size = 102, nb_dropouts = 0.5): 
		if base_model_name == 'VGG':
			self.model = models.vgg16(pretrained=True)
		elif base_model_name == 'DenseNet':
			self.model = models.densenet161(pretrained=True)
		elif base_model_name == 'ShuffleNet':
			self.model = models.shufflenet_v2_x1_0(pretrained=True)
		elif base_model_name == 'AlexNet':
			self.model = models.alexnet(pretrained=True)
		elif base_model_name == 'GoogleNet':
			self.model = models.googlenet(pretrained=True)
		else:
			return False

		# Save model parameters
		self.base_model_name = base_model_name
		self.hidden_units = hidden_units
		self.output_size = output_size
		self.nb_dropouts = nb_dropouts
		self.learn_rate = learn_rate
		self.epochs = 0 # Track previous learning iterations
		
		# Freeze parameters so we don't backprop through them
		for param in self.model.parameters():
			param.requires_grad = False
			
		# every model uses a different number of inputs on the classifier. The following code
		# calculates the number of inputs by searching the first Linear structure
		nb_inputs = 0
		if (base_model_name == 'VGG') or (base_model_name == 'DenseNet') or (base_model_name == 'AlexNet'):
			if type(self.model.classifier) == torch.nn.modules.container.Sequential:
				classif = 0
				while(type(self.model.classifier[classif]) != torch.nn.modules.linear.Linear):
					classif += 1
				nb_inputs = self.model.classifier[classif].in_features
			else: # 'ShuffleNet', 'GoogleNet'
				nb_inputs = self.model.classifier.in_features 
		else:
			if type(self.model.fc) == torch.nn.modules.container.Sequential:
				classif = 0
				while(type(self.model.fc[classif]) != torch.nn.modules.linear.Linear):
					classif += 1
				nb_inputs = self.model.fc[classif].in_features
			else:
				nb_inputs = self.model.fc.in_features 

		# Note: we used the same parameters as above as a starting point. Only change is 102 features
		# on the ouput (102 features instead of 1000)
		classifier = nn.Sequential(OrderedDict([
			('fc', nn.Linear(nb_inputs, hidden_units, bias=True)),
			('relu', nn.ReLU()),
			('drop', nn.Dropout(p = nb_dropouts)),
			('fc_output', nn.Linear(hidden_units, output_size, bias=True)),
			('output', nn.LogSoftmax(dim=1))
		]))
		if (base_model_name == 'VGG') or (base_model_name == 'DenseNet') or (base_model_name == 'AlexNet'):
			self.model.classifier = classifier
		else:
			self.model.fc = classifier

		# Only train the classifier parameters, feature parameters are frozen
		self.optimizer = optim.Adam(classifier.parameters(), lr=learn_rate)
		self.model_initialized = True
		return True

	def train(self, use_gpu, nb_epochs):

		if not self.loader_initialized:
			print("The train and validation data loader are not initialized. Please call init_loaders(...) first")
			return False

		if not self.model_initialized:
			print("The based trained model is not initialized. Please call init(...) or load_checkpoint(...) first")
			return False

		if use_gpu and not torch.cuda.is_available():
			print("No GPU has been found... Please disable GPU usage")
			return False
		
		self.device = torch.device("cuda:0" if use_gpu and torch.cuda.is_available() else "cpu")
		self.model.to(self.device)
		criterion = nn.NLLLoss()

		print_every = 5
		epoch_start =  self.epochs
		for epoch in range(nb_epochs):
			self.epochs += 1
			running_loss = 0
			step = 0

			for inputs, labels in self.trainloader:
				step += 1
				# Move input and label tensors to the GPU
				inputs, labels = inputs.to(self.device), labels.to(self.device)

				self.optimizer.zero_grad()

				outputs = self.model(inputs)
				loss = criterion(outputs, labels)
				loss.backward()
				self.optimizer.step()
				running_loss += loss.item()

				if step % print_every == 0:
					self.model.eval()
					test_loss = 0
					accuracy = 0

					for inputs, labels in self.validationloader:

						inputs, labels = inputs.to(self.device), labels.to(self.device)

						outputs = self.model(inputs)
						loss = criterion(outputs, labels)
						test_loss += loss.item()

						# Calculate our accuracy
						ps = torch.exp(outputs)
						top_ps, top_class = ps.topk(1, dim=1)
						equality = top_class == labels.view(*top_class.shape)
						accuracy += torch.mean(equality.type(torch.FloatTensor))

					print(
						f"Epoch {self.epochs}/{epoch_start + nb_epochs}, step {step }.."
						f"Train Loss: {running_loss/print_every:.3f}.."
						f"Validation Loss: {test_loss/len(self.validationloader):.3f}.."
						f"Validation accuracy: {accuracy*100/len(self.validationloader):.2f}%..")
					running_loss = 0
					self.model.train()
		return True

	def save_checkpoint(self, path):
		checkpoint = {
			'base_model_name': self.base_model_name,
            'hidden_units': self.hidden_units,
            'output_size': self.output_size, 
            'learn_rate': self.learn_rate,
            'nb_dropouts': self.nb_dropouts,
            'epochs': self.epochs,
            'state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'class_to_idx': self.class_to_idx 
		}
		torch.save(checkpoint, path)
		return True

	def load_checkpoint(self, path, use_gpu):
		if use_gpu:
			checkpoint = torch.load(path)
		else:
			checkpoint = torch.load(path, map_location = 'cpu')
		# def init(self, base_model_name, hidden_units, learn_rate = 0.001, output_size = 102, nb_dropouts = 0.5): 
		self.init(
			checkpoint['base_model_name'], 
			checkpoint['hidden_units'], 
			checkpoint['learn_rate'],
			checkpoint['output_size'], 
			checkpoint['nb_dropouts']
		)
		self.model.load_state_dict(checkpoint['state_dict'])
		self.epochs = checkpoint['epochs']
		self.class_to_idx = checkpoint['class_to_idx']
		if (self.base_model_name == 'VGG') or (self.base_model_name == 'DenseNet') or (self.base_model_name == 'AlexNet'):
			self.optimizer = optim.Adam(self.model.classifier.parameters())
		else:
			self.optimizer = optim.Adam(self.model.fc.parameters())
		self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
		if use_gpu: # self.optimizer.step() fails later on PC env (command line) if we don't do this!
			for state in self.optimizer.state.values(): # Found https://github.com/pytorch/pytorch/issues/2830
				for k, v in state.items():				# Found https://github.com/pytorch/pytorch/issues/2830
					if  torch.is_tensor(v):				# Found https://github.com/pytorch/pytorch/issues/2830
						state[k] = v.cuda()				# Found https://github.com/pytorch/pytorch/issues/2830
		return True

	def test(self, data_dir, use_gpu):
		test_dir =  os.path.join(data_dir, 'test')
		if not  os.path.isdir(test_dir):
			print("invalid data directory (/test not found)")
			return False

		if not self.model_initialized:
			print("The based trained model is not initialized. Please call init(...) or load_checkpoint(...) first")
			return False

		if use_gpu and not torch.cuda.is_available():
			print("No GPU has been found... Please disable GPU usage")
			return False
		
		self.device = torch.device("cuda:0" if use_gpu and torch.cuda.is_available() else "cpu")
		self.model.to(self.device)
		criterion = nn.NLLLoss()
	
		test_transforms = transforms.Compose([
			transforms.Resize(255),
			transforms.CenterCrop(224),
			transforms.ToTensor(),
			transforms.Normalize(
				[0.485, 0.456, 0.406],
				[0.229, 0.224, 0.225]
			)
		])
		test_image_datasets = datasets.ImageFolder(test_dir, transform=test_transforms)
		testloader = torch.utils.data.DataLoader(test_image_datasets, shuffle=False)

		self.model.eval()
		test_loss = 0
		accuracy = 0

		for inputs, labels in testloader:

			inputs, labels = inputs.to(self.device), labels.to(self.device)

			outputs = self.model(inputs)
			loss = criterion(outputs, labels)
			test_loss += loss.item()

			# Calculate our accuracy
			ps = torch.exp(outputs)
			top_ps, top_class = ps.topk(1, dim=1)
			equality = top_class == labels.view(*top_class.shape)
			accuracy += torch.mean(equality.type(torch.FloatTensor))

		print(
			f"Number of Epochs: {self.epochs}.."
			f"Test Loss: {test_loss/len(testloader):.3f}.."
			f"Test accuracy: {accuracy*100/len(testloader):.2f}%.."
		)

	def predict(self, image_path, use_gpu, topk=5):
		''' Predict the class (or classes) of an image using a trained deep learning model.
		'''
		if not self.model_initialized:
			print("The based trained model is not initialized. Please call init(...) or load_checkpoint(...) first")
			return False

		if use_gpu and not torch.cuda.is_available():
			print("No GPU has been found... Please disable GPU usage")
			return False
		
		self.device = torch.device("cuda:0" if use_gpu and torch.cuda.is_available() else "cpu")
		self.model.to(self.device)
		self.model.eval()

		# Process image
		image_transform = transforms.Compose([
			transforms.Resize(255),
			transforms.CenterCrop(224),
			transforms.ToTensor(),
			transforms.Normalize(
				[0.485, 0.456, 0.406],
				[0.229, 0.224, 0.225]
			)
		])
		image = Image.open(image_path)
		image = image_transform(image)
		image = torch.unsqueeze(image, 0) # Converts [1, 2, 3, 4] to [[1, 2, 3, 4]] to add image into array of images
		with torch.no_grad():
			if use_gpu:
				output = self.model(image.cuda())
			else:
				output = self.model(image)
		
		probability = F.softmax(output.data, dim=1)
		probabilities, classes = probability.topk(topk)
		idx_to_class = {val:key for key, val in self.class_to_idx.items()}
		return [p for p in np.array(probabilities.cpu()[0])], [idx_to_class[c] for c in np.array(classes.cpu()[0])]
