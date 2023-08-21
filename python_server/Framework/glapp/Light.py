import pygame
from .Transformations import *
from .Uniform import *

class Light:
    def __init__(
            self, light_number, 
            position=pygame.Vector3(0, 0, 0),
            color=pygame.Vector3(1, 1, 1)):
        
        self.transformation = identity_mat()
        self.position = position
        self.color = color
        self.light_pos_variable = "light_sources[" + str(light_number) + "].position"
        self.light_color_variable = "light_sources[" + str(light_number) + "].color"

    def update(self, program_id):
        Uniform("vec3").load(program_id, self.light_pos_variable, self.position)
        Uniform("vec3").load(program_id, self.light_color_variable, self.color)
