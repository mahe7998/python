import select

import numpy as np
from OpenGL.GLU import *
import pygame
from math import *
import numpy as np
from .Transformations import *
from .Uniform import *
from .PickingTexture import *

class Camera:
    def __init__(self, width, height):
        self.transformation = identity_mat()
        self.last_mouse_pos = pygame.math.Vector2(0, 0)
        self.mouse_sensitivity = 0.1
        self.key_sensitivity = 0.01
        self.update_perspective(width, height)

    def update_perspective(self, width, height):
        self.projection_mat = self.perspective_mat(60, width/height, 0.01, 100)

    def perspective_mat(self, angle, aspect_ratio, near_plane, far_plane):
        a = radians(angle)
        d = 1.0/tan(a/2)
        r = aspect_ratio
        b = (far_plane + near_plane) / (near_plane - far_plane)
        c = far_plane * near_plane / (near_plane - far_plane)
        return np.array(
            [[d/r, 0,  0,  0],
             [0,   d,  0,  0],
             [0,   0,  b,  c],
             [0,   0, -1,  0]], np.float32)

    def rotate(self, yaw, pitch):
        forward = pygame.Vector3(self.transformation[0,2], self.transformation[1,2], self.transformation[2,2])
        up = pygame.Vector3(0, 1, 0)
        angle = forward.angle_to(up)
        self.transformation = rotate(self.transformation, yaw, "Y", False)
        if (angle < 170 and pitch > 0) or (angle > 30.0 and pitch < 0):
            self.transformation = rotate(self.transformation, pitch, "X")

    def relative_move(self, forward=0.0, right=0.0, up=0.0):
        self.transformation = translate(self.transformation, right, up, forward)

    def update_projection(self, program_id):
        Uniform("mat4").load(program_id, "projection_mat", self.projection_mat)

    def update_view(self, program_id):
        Uniform("mat4").load(program_id, "view_mat", self.transformation)

    def update_mouse_and_keyboard(self, track_mouse, selected_object):
        # Mouse
        mouse_pos = pygame.mouse.get_pos()
        if track_mouse and selected_object.cube_index == -1:
            mouse_change = pygame.mouse.get_rel()
            self.rotate(mouse_change[0] * self.mouse_sensitivity,
                        -mouse_change[1] * self.mouse_sensitivity)
        self.last_mouse_pos = mouse_pos

        # Keyboard
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            if keys[pygame.K_DOWN]:
                self.transformation = translate(self.transformation, 0, -self.key_sensitivity, 0)
            if keys[pygame.K_UP]:
                self.transformation = translate(self.transformation, 0, self.key_sensitivity, 0)
        else:
            if keys[pygame.K_DOWN]:
                self.transformation = translate(self.transformation, 0, 0, self.key_sensitivity)
            if keys[pygame.K_UP]:
                self.transformation = translate(self.transformation, 0, 0, -self.key_sensitivity)
        if keys[pygame.K_RIGHT]:
            self.transformation = translate(self.transformation, self.key_sensitivity, 0, 0)
        if keys[pygame.K_LEFT]:
            self.transformation = translate(self.transformation, -self.key_sensitivity, 0, 0)

    def zoom(self, zoom_in, flipped):
        if flipped:
            direction = -1
        else:
            direction = 1
        direction *= zoom_in
        self.transformation = translate(self.transformation, 0, 0, direction * self.mouse_sensitivity)
