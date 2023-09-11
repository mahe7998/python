# This loads .OBJ 3D objects
import random

from OpenGL.GL import *
from .Mesh import *
from .Utils import *

class LoadMesh(Mesh):
    def __init__(
            self,
            filename,
            image_filename,
            gl_draw_type=GL_TRIANGLES,
            location=(0, 0, 0),
            scale=(1.0, 1.0, 1.0),
            rotation=(0, 0, 0),
            move_rotation=(0, 0, 0),
            move_location=(0, 0, 0),
            color=[1.0, 1.0, 1.0]):

        raw_vertices, triangles, uvs, uv_ind, normals, normal_ind = self.load_drawing(filename)
        vertices = format_vertices(raw_vertices, triangles)
        # Calculate boundaries
        boundaries = self.get_boundaries(raw_vertices)
        vertex_uvs = format_vertices(uvs, uv_ind)
        vertex_normals = format_vertices(normals, normal_ind)
        vertex_colors = []
        for i in range(len(vertices)):
            vertex_colors.append(color);
        super().__init__(
            vertices,
            image_filename=image_filename,
            vertex_normals=vertex_normals,
            vertex_uvs=vertex_uvs,
            vertex_colors=vertex_colors,
            gl_draw_type=gl_draw_type,
            location=location,
            scale=scale,
            rotation=rotation,
            move_rotation=move_rotation,
            move_location=move_location,
            boundaries=boundaries)

    def get_boundaries(self, raw_vertices):
        boundaries = [raw_vertices[0][0], raw_vertices[0][1], raw_vertices[0][2],
                      raw_vertices[0][0], raw_vertices[0][1], raw_vertices[0][2]] # Box around object
        for vertex in raw_vertices:
            if vertex[0] < boundaries[0]:  # X min
                boundaries[0] = vertex[0]
            if vertex[1] < boundaries[1]:  # Y min
                boundaries[1] = vertex[1]
            if vertex[2] < boundaries[2]:  # Z min
                boundaries[2] = vertex[2]
            if vertex[0] > boundaries[3]:  # X max
                boundaries[3] = vertex[0]
            if vertex[1] > boundaries[4]:  # Y max
                boundaries[4] = vertex[1]
            if vertex[2] > boundaries[5]:  # Z max
                boundaries[5] = vertex[2]
        return boundaries

    def load_drawing(self, filename):
        vertices = []
        normals = []
        normal_ind = []
        triangles = []
        uvs = []
        uv_ind = []
        first_line = True
        with open(filename) as fp:
            line = fp.readline()
            while line:
                if line[:2] == "v ":
                    vx, vy, vz = [float(value) for value in line[2:].split()]
                    vertices.append((vx, vy, vz))
                elif line[:2] == "f ":
                    t1, t2, t3 = [value for value in line[2:].split()]
                    triangle_list1 = [int(value) for value in t1.split('/')]
                    triangle_list2 = [int(value) for value in t2.split('/')]
                    triangle_list3 = [int(value) for value in t3.split('/')]
                    triangles.append(triangle_list1[0] - 1)
                    triangles.append(triangle_list2[0] - 1)
                    triangles.append(triangle_list3[0] - 1)
                    uv_ind.append(triangle_list1[1] - 1)
                    uv_ind.append(triangle_list2[1] - 1)
                    uv_ind.append(triangle_list3[1] - 1)
                    normal_ind.append(triangle_list1[2] - 1)
                    normal_ind.append(triangle_list2[2] - 1)
                    normal_ind.append(triangle_list3[2] - 1)
                elif line[:3] == "vn ":
                    nx, ny, nz = [float(value) for value in line[3:].split()]
                    normals.append((nx, ny, nz))
                elif line[:3] == "vt ":
                    u, v = [float(value) for value in line[3:].split()]
                    uvs.append((u, v))
                line = fp.readline()
        return vertices, triangles, uvs, uv_ind, normals, normal_ind

