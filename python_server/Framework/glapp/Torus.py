from .Mesh import *
import random

class Torus(Mesh):
    def __init__(self,
            shader_program,
            image_filename,
            outer_radius=2.0,
            inner_radius=0.5,
            slices=20, # How many outer rings
            loops=40, # How many inner rings
            initial_rotation=(0.0, 0.0, 0.0),
            color=(1.0, 1.0, 1.0),
            gl_draw_type=GL_TRIANGLES,
            boundaries=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            location=(0.0, 0.0, 0.0),
            scale=(1.0, 1.0, 1.0),
            rotation=(0, 0, 0),
            move_rotation=(0, 0, 0),
            move_location=(0, 0, 0)):
     
        self.outer_radius = outer_radius
        self.inner_radius = inner_radius
        self.slices = slices
        self.loops = loops
        self.initial_rotation = initial_rotation
        self.color = [color[0], color[1], color[2]]
        vertices, normals, vertex_uvs, colors = self.create_torus()
        super().__init__(
            shader_program,
            vertices,
            image_filename,
            vertex_normals=normals,
            vertex_uvs=vertex_uvs,
            vertex_colors=colors,
            gl_draw_type=gl_draw_type,
            location=location,
            scale=scale,
            rotation=rotation,
            move_rotation=move_rotation,
            move_location=move_location)

    def create_torus(self):
        raw_vertices = []
        raw_normals = []
        raw_vertex_uvs = []

        transformation_mat = identity_mat()
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[0], (1, 0, 0))
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[1], (0, 1, 0))
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[2], (0, 0, 1))
    
        for slice in range(self.slices+1):
            v = slice / self.slices
            slice_angle = v * 2 * np.pi
            cos_slices = np.cos(slice_angle)
            sin_slices = np.sin(slice_angle)
            slice_radius = self.outer_radius + self.inner_radius * cos_slices

            for loop in range(self.loops+1):
                #   x=(R+r·cos(v))cos(w)
                #   y=(R+r·cos(v))sin(w)
                #   z=r.sin(v)
                u = loop / self.loops 
                loop_angle = u * 2 * np.pi
                cos_loops = np.cos(loop_angle)
                sin_loops = np.sin(loop_angle)

                x = slice_radius * cos_loops
                y = slice_radius * sin_loops
                z = self.inner_radius * sin_slices

                vertex = np.array([x, y, z, 1])
                vertex = np.matmul(transformation_mat, vertex)
                raw_vertices.append([vertex[0], vertex[1], vertex[2]])
                normal = np.array([
                    cos_slices*cos_loops,
                    sin_loops*cos_slices, 
                    sin_slices,
                    1
                ])
                normal = np.matmul(transformation_mat, normal)
                raw_normals.append([normal[0], normal[1], normal[2]])
                raw_vertex_uvs.append([u, v])
        
        vertices = []
        normals = []
        vertex_uvs = []
        colors = []
        vertsPerSlice = self.loops + 1

        for slice in range(self.slices):
            v1 = slice * vertsPerSlice
            v2 = v1 + vertsPerSlice

            for j in range(self.loops):

                vertices.append(raw_vertices[v1])
                vertices.append(raw_vertices[v1+1])
                vertices.append(raw_vertices[v2])
                vertices.append(raw_vertices[v2])
                vertices.append(raw_vertices[v1+1])
                vertices.append(raw_vertices[v2+1])

                normals.append(raw_normals[v1])
                normals.append(raw_normals[v1+1])
                normals.append(raw_normals[v2])
                normals.append(raw_normals[v2])
                normals.append(raw_normals[v1+1])
                normals.append(raw_normals[v2+1])

                vertex_uvs.append(raw_vertex_uvs[v1])
                vertex_uvs.append(raw_vertex_uvs[v1+1])
                vertex_uvs.append(raw_vertex_uvs[v2])
                vertex_uvs.append(raw_vertex_uvs[v2])
                vertex_uvs.append(raw_vertex_uvs[v1+1])
                vertex_uvs.append(raw_vertex_uvs[v2+1])

                for k in range(6):
                    colors.append(self.color)

                v1 = v1 + 1
                v2 = v2 + 1
        return vertices, normals, vertex_uvs, colors

    def resize(self, outer_radius, inner_radius=None, slices=None, loops=None):
        self.outer_radius = outer_radius
        if inner_radius is not None:
            self.inner_radius = inner_radius
        if slices is not None:
            self.slices = slices
        if loops is not None:
            self.loops = loops
        self.vertices, self.vertex_normals, self.vertex_uvs, self.vertex_colors = self.create_torus()
        self.length = len(self.vertices)
        for i in range(len(self.vertices)):
            self.vertex_indices.append([i//3, 0])
        self.load()
        self.update_boundaries()

    def update_boundaries(self):
        self.boundaries = [
            -self.outer_radius - self.inner_radius,
            -self.outer_radius - self.inner_radius,
            -self.inner_radius,
            self.outer_radius + self.inner_radius,
            self.outer_radius + self.inner_radius,
            self.inner_radius]
        return self.boundaries
