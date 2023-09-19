from OpenGL import *
from .GraphicsData import *
from .Uniform import *
from .Transformations import *
from .Texture import *
from .Utils import *
import numpy as np

class Mesh:
    def __init__(
            self,
            shader_program,
            vertices,
            image_filename=None,
            vertex_normals=None,
            vertex_uvs=None,
            vertex_colors=None,
            gl_draw_type=GL_TRIANGLES,
            location=(0, 0, 0),
            scale=(1.0, 1.0, 1.0),
            rotation=(0, 0, 0),
            move_rotation=(0, 0, 0),
            move_location=(0, 0, 0),
            boundaries=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]):

        self.shader_program = shader_program
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
        self.mouse_sensitivity = 0.01
        self.vao_ref = glGenVertexArrays(1)
        self.vertex_indices = [] # Only used for selection in 3D space
        self.selectable = True
        for i in range(len(vertices)):
            self.vertex_indices.append([i//3, 0])
        self.image = None
        if image_filename is not None:
            self.image = Texture(image_filename)
        self.graghics_data_position = GraphicsData("vec3")
        self.graghics_data_vertex_normals = GraphicsData("vec3")
        self.graghics_data_uvs = GraphicsData("vec2")
        self.graphics_data_colors = GraphicsData("vec3")
        self.load()

    def load(self):
        glBindVertexArray(self.vao_ref)
        self.graghics_data_position.load(self.shader_program.program_id, "position", self.vertices)
        if self.vertex_normals is not None:
            self.graghics_data_vertex_normals.load(self.shader_program.program_id, "vertex_normal", self.vertex_normals)
        if self.vertex_uvs is not None:
            self.graghics_data_uvs.load(self.shader_program.program_id, "vertex_uv", self.vertex_uvs)
        if self.vertex_colors is not None:
            self.graphics_data_colors.load(self.shader_program.program_id, "vertex_color", self.vertex_colors)

    def set_selectable(self, selectable):
        self.selectable = selectable

    def get_selectable(self):
        return self.selectable

    def update_mouse_pos(self, selected_object, edit_mode, delta_x, delta_y):
        if selected_object.cube_index != -1:
            value_to_modify = None
            if edit_mode == EditMode.POSITION:
                value_to_modify = self.location
            elif edit_mode == EditMode.SCALE:
                value_to_modify = self.scale
            else:
                raise Exception("Not a valid editing mode!")
            delta_pos = (delta_x - delta_y) * self.mouse_sensitivity
            if selected_object.cube_index == 0 or selected_object.cube_index == 3:
                value_to_modify = (value_to_modify[0] + delta_pos, value_to_modify[1], value_to_modify[2])
            elif selected_object.cube_index == 1 or selected_object.cube_index == 4:
                value_to_modify = (value_to_modify[0], value_to_modify[1] + delta_pos, value_to_modify[2])
            elif selected_object.cube_index == 2 or selected_object.cube_index == 5:
                value_to_modify = (value_to_modify[0], value_to_modify[1], value_to_modify[2] + delta_pos)
            if edit_mode == EditMode.POSITION:
                self.location = value_to_modify
            elif edit_mode == EditMode.SCALE:
                self.scale = value_to_modify

    def set_transfornation(self, location, scale, rotation):
        self.location = location
        self.scale = scale
        self.rotation = rotation

    def get_transformation_matrix(self):
        transformation_mat = identity_mat()
        transformation_mat = translate(transformation_mat, self.location[0], self.location[1], self.location[2])
        transformation_mat = rotateA(transformation_mat, self.rotation[0], (1, 0, 0))
        transformation_mat = rotateA(transformation_mat, self.rotation[1], (0, 1, 0))
        transformation_mat = rotateA(transformation_mat, self.rotation[2], (0, 0, 1))
        transformation_mat = scale3(transformation_mat, self.scale[0], self.scale[1], self.scale[2])
        return transformation_mat

    def update_transformation(self):
        Uniform("mat4").load (self.shader_program.program_id, "model_mat", self.transformation_mat)

    def update_selection_color(self):
        if self.selected:
            Uniform("vec4").load(self.shader_program.program_id, "selection_color_mask", self.selection_color_mask)
        else:
            Uniform("vec4").load(self.shader_program.program_id, "selection_color_mask", [1.0, 1.0, 1.0, 1.0])

    def draw(self, camera, lights=None):
        self.shader_program.use()
        camera.update_projection(self.shader_program.program_id)
        camera.update_view(self.shader_program.program_id)
        if lights is not None:
            for _, light in lights.items():
                light.update(self.shader_program.program_id)
        if self.image is not None:
            Uniform("sample2D").load(self.shader_program.program_id, "texture_id", [self.image.texture_id, 1])
        self.transformation_mat = self.get_transformation_matrix()
        self.update_transformation()
        self.update_selection_color()
        glBindVertexArray(self.vao_ref)
        glDrawArrays(self.gl_draw_type, 0, self.length)
        # Animation needs to be done after to match related object (axis) location
        self.rotation = (self.rotation[0]+self.move_rotation[0], 
                         self.rotation[1]+self.move_rotation[1], 
                         self.rotation[2]+self.move_rotation[2])
        self.location = (self.location[0]+self.move_location[0], 
                         self.location[1]+self.move_location[1], 
                         self.location[2]+self.move_location[2])
