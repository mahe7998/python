"""
LoadMesh - OBJ file loader for WebGPU.
Loads .obj 3D models with vertices, normals, and UVs.
"""

import wgpu
import numpy as np
from ..graphics.mesh import Mesh3D


def format_vertices(raw_vertices, indices):
    """Convert indexed vertices to flat list."""
    return [raw_vertices[i] for i in indices]


class LoadMesh(Mesh3D):
    """
    Loads 3D models from .obj files.

    Supports:
    - Vertex positions
    - Texture coordinates (UVs)
    - Vertex normals
    - Face indices
    """

    def __init__(self, device, shader_library, filename,
                 location=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1),
                 move_rotation=(0, 0, 0), move_location=(0, 0, 0),
                 color=(1.0, 1.0, 1.0)):
        """
        Load mesh from OBJ file.

        Args:
            device: WebGPU device
            shader_library: ShaderLibrary instance
            filename: Path to .obj file
            location: Initial position
            rotation: Initial rotation in degrees
            scale: Scale factors
            move_rotation: Rotation per frame
            move_location: Translation per frame
            color: Default vertex color
        """
        # Load OBJ data
        raw_vertices, triangles, uvs, uv_ind, normals, normal_ind = self.load_drawing(filename)

        # Format into flat lists
        vertices = format_vertices(raw_vertices, triangles)
        vertex_uvs = format_vertices(uvs, uv_ind) if uvs else None
        vertex_normals = format_vertices(normals, normal_ind) if normals else None

        # Create vertex colors
        colors = [color] * len(vertices)

        # Store for boundary calculations
        self._raw_vertices = vertices

        super().__init__(
            device, shader_library,
            vertices, colors,
            location=location,
            rotation=rotation,
            scale=scale,
            move_rotation=move_rotation,
            move_location=move_location
        )

        # Store additional data
        self.vertex_uvs = vertex_uvs
        self.vertex_normals = vertex_normals

    def load_drawing(self, filename):
        """
        Parse OBJ file.

        Returns:
            vertices: List of (x, y, z) positions
            triangles: Vertex indices for faces
            uvs: List of (u, v) texture coordinates
            uv_ind: UV indices for faces
            normals: List of (nx, ny, nz) normals
            normal_ind: Normal indices for faces
        """
        vertices = []
        normals = []
        normal_ind = []
        triangles = []
        uvs = []
        uv_ind = []

        with open(filename) as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if line.startswith("v "):
                    parts = line[2:].split()
                    vx, vy, vz = float(parts[0]), float(parts[1]), float(parts[2])
                    vertices.append((vx, vy, vz))

                elif line.startswith("vn "):
                    parts = line[3:].split()
                    nx, ny, nz = float(parts[0]), float(parts[1]), float(parts[2])
                    normals.append((nx, ny, nz))

                elif line.startswith("vt "):
                    parts = line[3:].split()
                    u, v = float(parts[0]), float(parts[1])
                    uvs.append((u, v))

                elif line.startswith("f "):
                    parts = line[2:].split()
                    # Handle triangulated faces (assume 3 vertices per face)
                    if len(parts) >= 3:
                        face_verts = []
                        face_uvs = []
                        face_normals = []

                        for part in parts[:3]:
                            indices = part.split('/')
                            face_verts.append(int(indices[0]) - 1)

                            if len(indices) > 1 and indices[1]:
                                face_uvs.append(int(indices[1]) - 1)

                            if len(indices) > 2 and indices[2]:
                                face_normals.append(int(indices[2]) - 1)

                        triangles.extend(face_verts)
                        if face_uvs:
                            uv_ind.extend(face_uvs)
                        if face_normals:
                            normal_ind.extend(face_normals)

        return vertices, triangles, uvs, uv_ind, normals, normal_ind

    def get_boundaries(self):
        """Calculate axis-aligned bounding box."""
        if not self._raw_vertices:
            return [0, 0, 0, 0, 0, 0]

        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        for v in self._raw_vertices:
            min_x = min(min_x, v[0])
            min_y = min(min_y, v[1])
            min_z = min(min_z, v[2])
            max_x = max(max_x, v[0])
            max_y = max(max_y, v[1])
            max_z = max(max_z, v[2])

        return [min_x, min_y, min_z, max_x, max_y, max_z]
