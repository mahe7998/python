"""
Axis - 3-axis coordinate lines for WebGPU.
Renders RGB colored lines for X, Y, Z axes.
"""

import wgpu
import numpy as np
from ..graphics.transformations import identity_mat


class Axis:
    """
    3-axis coordinate lines.

    Renders:
    - X axis: Red
    - Y axis: Green
    - Z axis: Blue

    Uses line primitive topology.
    """

    def __init__(self, device, shader_library,
                 boundaries=(-5, -5, -5, 5, 5, 5),
                 location=(0, 0, 0)):
        """
        Create axis lines.

        Args:
            device: WebGPU device
            shader_library: ShaderLibrary instance
            boundaries: (min_x, min_y, min_z, max_x, max_y, max_z)
            location: Position offset
        """
        self.device = device
        self.shader_library = shader_library
        self.location = list(location)
        self.boundaries = list(boundaries)

        # Selection state
        self.selected = False
        self.selectable = False

        # Create vertices: 6 vertices for 3 lines
        vertices = [
            # X axis (red)
            (boundaries[0], 0.0, 0.0),
            (boundaries[3], 0.0, 0.0),
            # Y axis (green)
            (0.0, boundaries[1], 0.0),
            (0.0, boundaries[4], 0.0),
            # Z axis (blue)
            (0.0, 0.0, boundaries[2]),
            (0.0, 0.0, boundaries[5]),
        ]

        colors = [
            (1.0, 0.0, 0.0), (1.0, 0.0, 0.0),  # X - red
            (0.0, 1.0, 0.0), (0.0, 1.0, 0.0),  # Y - green
            (0.0, 0.0, 1.0), (0.0, 0.0, 1.0),  # Z - blue
        ]

        self._create_vertex_buffer(vertices, colors)
        self._create_model_buffer()
        self._create_bind_group()

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
            size=80,  # model_mat (64) + selection_mask (16)
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
        """Draw the axis lines."""
        pipeline = self.shader_library.get_pipeline("line")

        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, camera_bind_group)
        render_pass.set_bind_group(1, self.bind_group)
        render_pass.set_vertex_buffer(0, self.vertex_buffer)
        render_pass.draw(self.vertex_count)

    def update(self):
        """Update (no-op for static geometry)."""
        pass
