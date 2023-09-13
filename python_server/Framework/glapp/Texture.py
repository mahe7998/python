from OpenGL.GL import *
from PIL import Image
import numpy as np

class Texture():

    def __init__(self, filename=None):

        self.texture_id = glGenTextures(1)
        image = Image.open(filename)
        self.load(image)
        image.close()

    def load(self, image):

        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        pixel_data = np.array(list(image.getdata()), np.uint8)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, image.width, image.height, 0, GL_RGB, GL_UNSIGNED_BYTE, pixel_data)
        glGenerateMipmap(GL_TEXTURE_2D) # Used for fuziness in the distance
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR) # What to do when magnifying pixel values
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR) # What to do in the distance
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT) # GL_CLAMP_TO_EDGE
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glBindTexture(GL_TEXTURE_2D, 0)
