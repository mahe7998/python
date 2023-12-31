import glfw
import glfw.GLFW as GLFW_CONSTANTS
import numpy as np
from OpenGL.GLU import *
from math import *
import numpy as np
from .Transformations import *
from .Uniform import *
from .Utils import *

class Camera:
    def __init__(self, width, height):
        self.transformation = identity_mat()
        self.last_mouse_pos = (0, 0)
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
        forward = (self.transformation[0,2], self.transformation[1,2], self.transformation[2,2])
        up = (0, 1, 0)
        angle = degrees(angle_to(forward, up))
        self.transformation = rotate(self.transformation, yaw, "Y", False)
        if (angle < 170 and pitch > 0) or (angle > 30.0 and pitch < 0):
            self.transformation = rotate(self.transformation, pitch, "X")

    def relative_move(self, forward=0.0, right=0.0, up=0.0):
        self.transformation = translate(self.transformation, right, up, forward)

    def update_projection(self, program_id):
        Uniform("mat4").load(program_id, "projection_mat", self.projection_mat)

    def update_view(self, program_id):
        Uniform("mat4").load(program_id, "view_mat", self.transformation)

    def update_mouse(self, delta_x, delta_y):
        self.rotate(delta_x * self.mouse_sensitivity, -delta_y * self.mouse_sensitivity)

    def update_keyboard(self, window):
        if glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_DOWN) == GLFW_CONSTANTS.GLFW_PRESS:
            if glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_RIGHT_SHIFT) == GLFW_CONSTANTS.GLFW_PRESS or glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_LEFT_SHIFT) == GLFW_CONSTANTS.GLFW_PRESS:
                self.transformation = translate(self.transformation, 0, -self.key_sensitivity, 0)
            else:
                self.transformation = translate(self.transformation, 0, 0, self.key_sensitivity)
        elif glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_UP) == GLFW_CONSTANTS.GLFW_PRESS:
            if glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_RIGHT_SHIFT) == GLFW_CONSTANTS.GLFW_PRESS or glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_LEFT_SHIFT) == GLFW_CONSTANTS.GLFW_PRESS:
                self.transformation = translate(self.transformation, 0, self.key_sensitivity, 0)
            else:
                self.transformation = translate(self.transformation, 0, 0, -self.key_sensitivity)
        elif glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_RIGHT) == GLFW_CONSTANTS.GLFW_PRESS:
            self.transformation = translate(self.transformation, self.key_sensitivity, 0, 0)
        elif glfw.get_key(window, GLFW_CONSTANTS.GLFW_KEY_LEFT) == GLFW_CONSTANTS.GLFW_PRESS:
            self.transformation = translate(self.transformation, -self.key_sensitivity, 0, 0)

    def zoom(self, zoom_in, flipped):
        if flipped:
            direction = -1
        else:
            direction = 1
        direction *= zoom_in
        self.transformation = translate(self.transformation, 0, 0, direction * self.mouse_sensitivity)
