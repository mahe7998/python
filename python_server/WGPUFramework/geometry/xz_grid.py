"""
XZGrid - Ground plane grid for WebGPU.
Renders a grid of lines on the XZ plane.
"""

import wgpu
import numpy as np
from ..graphics.transformations import identity_mat


class XZGrid:
    """
    Ground plane grid on the XZ plane.

    Renders a grid of gray lines useful for spatial reference.
    """

    def __init__(self, device, shader_library,
                 size=10, spacing=1.0,
                 location=(0, 0, 0),
                 color=(0.3, 0.3, 0.3)):
        """
        Create XZ plane grid.

        Args:
            device: WebGPU device
            shader_library: ShaderLibrary instance
            size: Grid extends from -size to +size
            spacing: Distance between grid lines
            location: Position offset
            color: Line color (r, g, b)
        """
        self.device = device
        self.shader_library = shader_library
        self.location = list(location)
        self.size = size
        self.spacing = spacing
        self.color = list(color)

        # Selection state
        self.selected = False
        self.selectable = False

        self._create_grid_geometry()
        self._create_model_buffer()
        self._create_bind_group()

    def _create_grid_geometry(self):
        """Generate grid vertices."""
        vertices = []
        colors = []

        size = self.size
        step = int(size / self.spacing) if self.spacing > 0 else int(size)

        for s in range(-step, step + 1):
            pos = s * self.spacing

            # Line parallel to X axis
            vertices.append((-size, 0.0, pos))
            vertices.append((size, 0.0, pos))

            # Line parallel to Z axis
            vertices.append((pos, 0.0, -size))
            vertices.append((pos, 0.0, size))

            # Colors for all 4 vertices
            for _ in range(4):
                colors.append(self.color)

        self._create_vertex_buffer(vertices, colors)

    def _create_vertex_buffer(self, vertices, colors):
        """Create interleaved vertex buffer."""
        vertex_data = []
        for i, pos in enumerate(vertices):
            color = colors[i]
            vertex_data.extend([pos[0], pos[1], pos[2], color[0], color[1], color[2]])

        self.vertex_count = len(vertices)
        vertex_array = np.array(vertex_data, dtype=np.float32)

        self.vertex_buffer = self.device.create_buffer(
            size=vertex_array.nbytes,
            usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST
        )
        self.device.queue.write_buffer(self.vertex_buffer, 0, vertex_array.tobytes())

    def _create_model_buffer(self):
        """Create uniform buffer for model matrix."""
        self.model_buffer = self.device.create_buffer(
            size=80,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._update_model_buffer()

    def _create_bind_group(self):
        """Create bind group for model uniforms."""
        self.bind_group = self.shader_library.create_model_bind_group(self.model_buffer)

    def _update_model_buffer(self):
        """Update model uniform buffer."""
        model_mat = identity_mat()
        # Apply location offset
        model_mat[0, 3] = self.location[0]
        model_mat[1, 3] = self.location[1]
        model_mat[2, 3] = self.location[2]

        mask = [1.0, 1.0, 1.0, 1.0]

        data = np.zeros(20, dtype=np.float32)
        data[0:16] = model_mat.T.flatten()  # Transpose for WGSL
        data[16:20] = mask

        self.device.queue.write_buffer(self.model_buffer, 0, data.tobytes())

    def draw(self, render_pass, camera_bind_group):
        """Draw the grid."""
        pipeline = self.shader_library.get_pipeline("line")

        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, camera_bind_group)
        render_pass.set_bind_group(1, self.bind_group)
        render_pass.set_vertex_buffer(0, self.vertex_buffer)
        render_pass.draw(self.vertex_count)

    def update(self):
        """Update (no-op for static geometry)."""
        pass

    def get_transformation_matrix(self):
        """Return identity (grid is always at origin)."""
        return identity_mat()
