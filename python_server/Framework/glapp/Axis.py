from .Mesh import *

class Axis(Mesh):
    def __init__(self,
            location=(0, 0, 0),
            boundaries=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            scale=(1.0, 1.0, 1.0),
            rotation=(0, 0, 0),):
        
        self.vertices = [[ boundaries[0],           0.0,           0.0],
                         [ boundaries[3],           0.0,           0.0],
                         [           0.0, boundaries[1],           0.0],
                         [           0.0, boundaries[4],           0.0],
                         [           0.0,           0.0, boundaries[2]],
                         [           0.0,           0.0, boundaries[5]]]
        self.vertex_indices = [[0, 0], [0, 0], [1, 0], [1,0], [2, 0], [2, 0]]
        self.boundaries = boundaries # Box around object
        self.selected = False
        colors = [[1.0, 0.0, 0.0],
                  [1.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0],
                  [0.0, 1.0, 0.0],
                  [0.0, 0.0, 1.0],
                  [0.0, 0.0, 1.0]]
        super().__init__(
            self.vertices,
            image_filename=None,
            vertex_normals=None,
            vertex_uvs=None,
            vertex_colors=colors,
            gl_draw_type=GL_LINES,
            location=location,
            scale=scale,
            rotation=rotation,
            move_rotation=(0, 0, 0),
            move_location=(0, 0, 0),
            boundaries=boundaries)
