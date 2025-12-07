"""
Torus - Procedural torus geometry for WebGPU.
"""

import numpy as np
from ..graphics.mesh import Mesh3D
from ..graphics.transformations import identity_mat, rotateA


class Torus(Mesh3D):
    """
    Procedural torus (donut shape) geometry.

    Creates a torus with configurable outer radius, inner radius,
    and resolution (slices and loops).
    """

    def __init__(self, device, shader_library,
                 outer_radius=2.0, inner_radius=0.5,
                 slices=20, loops=40,
                 initial_rotation=(0.0, 0.0, 0.0),
                 color=(1.0, 1.0, 1.0),
                 location=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1),
                 move_rotation=(0, 0, 0), move_location=(0, 0, 0)):
        """
        Create torus geometry.

        Args:
            device: WebGPU device
            shader_library: ShaderLibrary instance
            outer_radius: Distance from center to tube center
            inner_radius: Tube radius
            slices: Number of outer rings (around the donut)
            loops: Number of inner rings (around the tube)
            initial_rotation: Pre-rotation applied to geometry
            color: Vertex color (r, g, b)
            location: Initial position
            rotation: Initial rotation in degrees
            scale: Scale factors
            move_rotation: Rotation per frame
            move_location: Translation per frame
        """
        self.outer_radius = outer_radius
        self.inner_radius = inner_radius
        self.slices = slices
        self.loops = loops
        self.initial_rotation = initial_rotation
        self.color = list(color)

        vertices, normals, vertex_uvs, colors = self._create_torus()

        super().__init__(
            device, shader_library,
            vertices, colors,
            location=location,
            rotation=rotation,
            scale=scale,
            move_rotation=move_rotation,
            move_location=move_location
        )

        self.vertex_normals = normals
        self.vertex_uvs = vertex_uvs

    def _create_torus(self):
        """Generate torus vertices, normals, UVs, and colors."""
        raw_vertices = []
        raw_normals = []
        raw_vertex_uvs = []

        # Pre-rotation transformation
        transformation_mat = identity_mat()
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[0], (1, 0, 0))
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[1], (0, 1, 0))
        transformation_mat = rotateA(transformation_mat, self.initial_rotation[2], (0, 0, 1))

        # Generate vertices on torus surface
        for slice_idx in range(self.slices + 1):
            v = slice_idx / self.slices
            slice_angle = v * 2 * np.pi
            cos_slices = np.cos(slice_angle)
            sin_slices = np.sin(slice_angle)
            slice_radius = self.outer_radius + self.inner_radius * cos_slices

            for loop_idx in range(self.loops + 1):
                u = loop_idx / self.loops
                loop_angle = u * 2 * np.pi
                cos_loops = np.cos(loop_angle)
                sin_loops = np.sin(loop_angle)

                # Torus parametric equations
                x = slice_radius * cos_loops
                y = slice_radius * sin_loops
                z = self.inner_radius * sin_slices

                # Apply pre-rotation
                vertex = np.array([x, y, z, 1])
                vertex = np.matmul(transformation_mat, vertex)
                raw_vertices.append([vertex[0], vertex[1], vertex[2]])

                # Calculate normal
                normal = np.array([
                    cos_slices * cos_loops,
                    sin_loops * cos_slices,
                    sin_slices,
                    1
                ])
                normal = np.matmul(transformation_mat, normal)
                raw_normals.append([normal[0], normal[1], normal[2]])

                raw_vertex_uvs.append([u, v])

        # Generate triangle indices
        vertices = []
        normals = []
        vertex_uvs = []
        colors = []
        verts_per_slice = self.loops + 1

        for slice_idx in range(self.slices):
            v1 = slice_idx * verts_per_slice
            v2 = v1 + verts_per_slice

            for j in range(self.loops):
                # Two triangles per quad
                # Triangle 1
                vertices.append(raw_vertices[v1])
                vertices.append(raw_vertices[v1 + 1])
                vertices.append(raw_vertices[v2])
                # Triangle 2
                vertices.append(raw_vertices[v2])
                vertices.append(raw_vertices[v1 + 1])
                vertices.append(raw_vertices[v2 + 1])

                normals.append(raw_normals[v1])
                normals.append(raw_normals[v1 + 1])
                normals.append(raw_normals[v2])
                normals.append(raw_normals[v2])
                normals.append(raw_normals[v1 + 1])
                normals.append(raw_normals[v2 + 1])

                vertex_uvs.append(raw_vertex_uvs[v1])
                vertex_uvs.append(raw_vertex_uvs[v1 + 1])
                vertex_uvs.append(raw_vertex_uvs[v2])
                vertex_uvs.append(raw_vertex_uvs[v2])
                vertex_uvs.append(raw_vertex_uvs[v1 + 1])
                vertex_uvs.append(raw_vertex_uvs[v2 + 1])

                # 6 vertices per quad
                for _ in range(6):
                    colors.append(self.color)

                v1 += 1
                v2 += 1

        return vertices, normals, vertex_uvs, colors

    def get_boundaries(self):
        """Get axis-aligned bounding box."""
        extent = self.outer_radius + self.inner_radius
        return [
            -extent, -extent, -self.inner_radius,
            extent, extent, self.inner_radius
        ]

    def resize(self, outer_radius, inner_radius=None, slices=None, loops=None):
        """Resize torus with new parameters."""
        self.outer_radius = outer_radius
        if inner_radius is not None:
            self.inner_radius = inner_radius
        if slices is not None:
            self.slices = slices
        if loops is not None:
            self.loops = loops

        vertices, normals, vertex_uvs, colors = self._create_torus()
        self._recreate_vertex_buffer(vertices, colors)
        self.vertex_normals = normals
        self.vertex_uvs = vertex_uvs

    def _recreate_vertex_buffer(self, vertices, colors):
        """Recreate vertex buffer with new geometry."""
        # Interleave position and color
        vertex_data = []
        for i, pos in enumerate(vertices):
            color = colors[i] if i < len(colors) else (1, 1, 1)
            vertex_data.extend([pos[0], pos[1], pos[2], color[0], color[1], color[2]])

        self.vertex_count = len(vertices)
        vertex_array = np.array(vertex_data, dtype=np.float32)

        self.device.queue.write_buffer(self.vertex_buffer, 0, vertex_array.tobytes())
