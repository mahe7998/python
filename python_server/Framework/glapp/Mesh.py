from OpenGL import *
import pygame
from .GraphicsData import *
from .Uniform import *
from .Transformations import *
from .Texture import *
from .Utils import *
import numpy as np

class Mesh:
    def __init__(
            self,
            vertices,
            image_filename=None,
            vertex_normals=None,
            vertex_uvs=None,
            vertex_colors=None,
            gl_draw_type=GL_TRIANGLES,
            location=pygame.Vector3(0, 0, 0),
            scale=pygame.Vector3(1.0, 1.0, 1.0),
            rotation=pygame.Vector3(0, 0, 0),
            move_rotation=pygame.Vector3(0, 0, 0),
            move_location=pygame.Vector3(0, 0, 0),
            boundaries=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]):

        self.vertices = vertices
        self.length = len(vertices)
        self.vertex_normals = vertex_normals
        self.vertex_uvs = vertex_uvs
        self.vertex_colors = vertex_colors
        self.gl_draw_type = gl_draw_type
        self.location = location
        self.move_location = move_location
        self.rotation = rotation
        self.move_rotation = move_rotation
        self.scale = scale
        self.selected = False
        self.selection_color_mask = [0.5, 0.5, 1.0, 1.0]
        self.boundaries = boundaries
        self.last_mouse_pos = (0, 0)
        self.mouse_sensitivity = 0.01
        self.vao_ref = glGenVertexArrays(1)
        self.vertex_indices = [] # Only used for selection in 3D space
        for i in range(len(vertices)):
            self.vertex_indices.append([i // 3, 0])
        self.image = None
        if image_filename is not None:
            self.image = Texture(image_filename)
        self.material = None

    def load(self, material):
        self.material = material
        glBindVertexArray(self.vao_ref)
        GraphicsData("vec3").load(self.material.program_id, "position", self.vertices)
        if self.vertex_normals is not None:
            GraphicsData("vec3").load(self.material.program_id, "vertex_normal", self.vertex_normals)
        if self.vertex_uvs is not None:
            GraphicsData("vec2").load(self.material.program_id, "vertex_uv", self.vertex_uvs)
        if self.vertex_colors is not None:
            GraphicsData("vec3").load(self.material.program_id, "vertex_color", self.vertex_colors)

    def update_mouse_and_keyboard(self, track_mouse, selected_object, edit_mode):
        # Mouse
        mouse_pos = pygame.mouse.get_pos()
        if track_mouse and selected_object.cube_index != -1:
            mouse_change = self.last_mouse_pos - mouse_pos
            format_to_modify = None
            if edit_mode == EditMode.POSITION:
                format_to_modify = self.location
            elif edit_mode == EditMode.SCALE:
                format_to_modify = self.scale
            else:
                raise Exception("Not a valid editing mode!")
            if selected_object.cube_index == 0 or selected_object.cube_index == 3:
                format_to_modify[0] -= (mouse_change.x + mouse_change.y) * self.mouse_sensitivity
            elif selected_object.cube_index == 1 or selected_object.cube_index == 4:
                format_to_modify[1] += (mouse_change.x + mouse_change.y) * self.mouse_sensitivity
            elif selected_object.cube_index == 2 or selected_object.cube_index == 5:
                format_to_modify[2] -= (mouse_change.x + mouse_change.y) * self.mouse_sensitivity
        self.last_mouse_pos = mouse_pos

    def set_transfornation(self, location, scale, rotation):
        self.location = location
        self.scale = scale
        self.rotation = rotation

    def get_transformation_matrix(self):
        transformation_mat = identity_mat()
        transformation_mat = translate(transformation_mat, self.location.x, self.location.y, self.location.z)
        transformation_mat = rotateA(transformation_mat, self.rotation[0], pygame.Vector3(1, 0, 0))
        transformation_mat = rotateA(transformation_mat, self.rotation[1], pygame.Vector3(0, 1, 0))
        transformation_mat = rotateA(transformation_mat, self.rotation[2], pygame.Vector3(0, 0, 1))
        transformation_mat = scale3(transformation_mat, self.scale.x, self.scale.y, self.scale.z)
        return transformation_mat

    def update_transformation(self):
        Uniform("mat4").load (self.material.program_id, "model_mat", self.transformation_mat)

    def update_selection_color(self):
        if self.selected:
            Uniform("vec4").load(self.material.program_id, "selection_color_mask", self.selection_color_mask)
        else:
            Uniform("vec4").load(self.material.program_id, "selection_color_mask", [1.0, 1.0, 1.0, 1.0])

    def draw(self, camera, lights=None):
        self.material.use()
        camera.update_projection(self.material.program_id)
        camera.update_view(self.material.program_id)
        if lights is not None:
            for light in lights:
                light.update(self.material.program_id)
        if self.image is not None:
            Uniform("sample2D").load(self.material.program_id, "tex", [self.image.texture_id, 1])
        self.transformation_mat = self.get_transformation_matrix()
        self.update_transformation()
        self.update_selection_color()
        glBindVertexArray(self.vao_ref)
        glDrawArrays(self.gl_draw_type, 0, self.length)
        # Animation needs to be done after to match related object (axis) location
        self.rotation += self.move_rotation
        self.location += self.move_location
