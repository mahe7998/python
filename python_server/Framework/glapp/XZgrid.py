from .Mesh import *

class XZGrid(Mesh):
    def __init__(self, shader_program, location, size, material=None):
        self.vertices = []
        self.vertex_indices = []
        self.boundaries = [-size, -size, -size, size, size, size] # Box around object
        self.selected = False
        colors = []

        axis_s = int(size)
        current_index = len(self.vertex_indices) // 2
        for s in range(-axis_s, axis_s, 1):
            self.vertices.append([-size, 0.0, s])
            self.vertices.append([size, 0.0, s])
            self.vertices.append([s, 0.0, -size])
            self.vertices.append([s, 0.0, size])
            self.vertex_indices.append([current_index, 0])
            self.vertex_indices.append([current_index, 0])
            self.vertex_indices.append([current_index + 1, 0])
            self.vertex_indices.append([current_index + 1, 0])
            current_index += 2
            colors.append([0.3, 0.3, 0.3])
            colors.append([0.3, 0.3, 0.3])
            colors.append([0.3, 0.3, 0.3])
            colors.append([0.3, 0.3, 0.3])

        super().__init__(
            shader_program,
            self.vertices,
            image_filename=None,
            vertex_normals=None,
            vertex_uvs=None,
            vertex_colors=colors,
            gl_draw_type=GL_LINES,
            location=location,
            scale=(1.0, 1.0, 1.0),
            rotation=(0, 0, 0),
            move_rotation=(0, 0, 0),
            move_location=(0, 0, 0))

    def get_transformation_matrix(self):
        return identity_mat()