"""
Mesh3D - Base class for 3D geometry in WebGPU.
Manages vertex buffers, uniform buffers, and bind groups.
"""

import wgpu
import numpy as np
from .transformations import identity_mat, translate, scale3, rotateA


class Mesh3D:
    """
    Base class for 3D renderable geometry.

    Provides:
    - Vertex buffer management
    - Model transformation (position, rotation, scale)
    - Uniform buffer for model matrix
    - Bind group for shader access
    - Animation support (move_rotation, move_location)
    """

    def __init__(self, device, shader_library, vertices, colors,
                 location=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1),
                 move_rotation=(0, 0, 0), move_location=(0, 0, 0)):
        """
        Initialize mesh with vertex data.

        Args:
            device: WebGPU device
            shader_library: ShaderLibrary instance
            vertices: List of vertex positions [(x,y,z), ...]
            colors: List of vertex colors [(r,g,b), ...]
            location: Initial position (x, y, z)
            rotation: Initial rotation in degrees (rx, ry, rz)
            scale: Scale factors (sx, sy, sz)
            move_rotation: Rotation per frame (rx, ry, rz)
            move_location: Translation per frame (x, y, z)
        """
        self.device = device
        self.shader_library = shader_library

        # Transform properties
        self.location = list(location)
        self.rotation = list(rotation)
        self.scale = list(scale)
        self.move_rotation = list(move_rotation)
        self.move_location = list(move_location)

        # Selection state
        self.selected = False
        self.selectable = True
        self.selection_color_mask = [1.0, 1.0, 1.0, 1.0]

        # Create vertex buffer
        self._create_vertex_buffer(vertices, colors)

        # Create model uniform buffer
        self._create_model_buffer()

        # Create bind group
        self._create_bind_group()

    def _create_vertex_buffer(self, vertices, colors):
        """Create interleaved vertex buffer (position + color)."""
        # Interleave position and color: [x,y,z,r,g,b, x,y,z,r,g,b, ...]
        vertex_data = []
        for i, pos in enumerate(vertices):
            color = colors[i] if i < len(colors) else (1, 1, 1)
            vertex_data.extend([pos[0], pos[1], pos[2], color[0], color[1], color[2]])

        self.vertex_count = len(vertices)
        vertex_array = np.array(vertex_data, dtype=np.float32)

        self.vertex_buffer = self.device.create_buffer(
            size=vertex_array.nbytes,
            usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST
        )
        self.device.queue.write_buffer(self.vertex_buffer, 0, vertex_array.tobytes())

    def _create_model_buffer(self):
        """Create uniform buffer for model matrix and selection mask."""
        # Model uniform: model_mat (64 bytes) + selection_color_mask (16 bytes) = 80 bytes
        self.model_buffer = self.device.create_buffer(
            size=80,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self._update_model_buffer()

    def _create_bind_group(self):
        """Create bind group for model uniforms."""
        self.bind_group = self.shader_library.create_model_bind_group(self.model_buffer)

    def _update_model_buffer(self):
        """Update model uniform buffer with current transform and selection."""
        model_mat = self.get_transformation_matrix()

        # Update selection color mask
        if self.selected:
            mask = [0.5, 0.5, 1.0, 1.0]  # Blue tint
        else:
            mask = [1.0, 1.0, 1.0, 1.0]  # No tint

        # Pack data: model_mat (64) + selection_mask (16) = 80 bytes
        # Transpose for WGSL column-major format
        data = np.zeros(20, dtype=np.float32)
        data[0:16] = model_mat.T.flatten()
        data[16:20] = mask

        self.device.queue.write_buffer(self.model_buffer, 0, data.tobytes())

    def get_transformation_matrix(self):
        """Calculate transformation matrix from position, rotation, scale."""
        mat = identity_mat()
        mat = translate(mat, self.location[0], self.location[1], self.location[2])
        mat = rotateA(mat, self.rotation[0], (1, 0, 0))
        mat = rotateA(mat, self.rotation[1], (0, 1, 0))
        mat = rotateA(mat, self.rotation[2], (0, 0, 1))
        mat = scale3(mat, self.scale[0], self.scale[1], self.scale[2])
        return mat

    def update(self):
        """Update mesh state (animation)."""
        if not self.selected:
            # Apply animation
            self.rotation[0] += self.move_rotation[0]
            self.rotation[1] += self.move_rotation[1]
            self.rotation[2] += self.move_rotation[2]
            self.location[0] += self.move_location[0]
            self.location[1] += self.move_location[1]
            self.location[2] += self.move_location[2]

        # Update uniform buffer
        self._update_model_buffer()

    def draw(self, render_pass, camera_bind_group):
        """
        Draw the mesh.

        Args:
            render_pass: Active render pass encoder
            camera_bind_group: Bind group for camera uniforms
        """
        # Update model buffer
        self.update()

        # Get pipeline
        pipeline = self.shader_library.get_pipeline("color")

        # Set pipeline and bind groups
        render_pass.set_pipeline(pipeline)
        render_pass.set_bind_group(0, camera_bind_group)
        render_pass.set_bind_group(1, self.bind_group)
        render_pass.set_vertex_buffer(0, self.vertex_buffer)

        # Draw
        render_pass.draw(self.vertex_count)

    def set_selected(self, selected):
        """Set selection state."""
        self.selected = selected

    def set_location(self, x, y, z):
        """Set mesh position."""
        self.location = [x, y, z]

    def set_rotation(self, rx, ry, rz):
        """Set mesh rotation (degrees)."""
        self.rotation = [rx, ry, rz]

    def set_scale(self, sx, sy, sz):
        """Set mesh scale."""
        self.scale = [sx, sy, sz]


def create_cube(device, shader_library, size=1.0, **kwargs):
    """
    Create a colored cube mesh.

    Args:
        device: WebGPU device
        shader_library: ShaderLibrary instance
        size: Cube size (default 1.0)
        **kwargs: Additional Mesh3D arguments (location, rotation, etc.)

    Returns:
        Mesh3D instance
    """
    s = size / 2

    # Cube vertices (36 vertices for 12 triangles)
    vertices = [
        # Front face (red)
        (-s, -s,  s), ( s, -s,  s), ( s,  s,  s),
        (-s, -s,  s), ( s,  s,  s), (-s,  s,  s),
        # Back face (green)
        ( s, -s, -s), (-s, -s, -s), (-s,  s, -s),
        ( s, -s, -s), (-s,  s, -s), ( s,  s, -s),
        # Top face (blue)
        (-s,  s,  s), ( s,  s,  s), ( s,  s, -s),
        (-s,  s,  s), ( s,  s, -s), (-s,  s, -s),
        # Bottom face (yellow)
        (-s, -s, -s), ( s, -s, -s), ( s, -s,  s),
        (-s, -s, -s), ( s, -s,  s), (-s, -s,  s),
        # Right face (magenta)
        ( s, -s,  s), ( s, -s, -s), ( s,  s, -s),
        ( s, -s,  s), ( s,  s, -s), ( s,  s,  s),
        # Left face (cyan)
        (-s, -s, -s), (-s, -s,  s), (-s,  s,  s),
        (-s, -s, -s), (-s,  s,  s), (-s,  s, -s),
    ]

    # Colors for each face (6 vertices per face)
    colors = (
        [(1, 0, 0)] * 6 +  # Front - red
        [(0, 1, 0)] * 6 +  # Back - green
        [(0, 0, 1)] * 6 +  # Top - blue
        [(1, 1, 0)] * 6 +  # Bottom - yellow
        [(1, 0, 1)] * 6 +  # Right - magenta
        [(0, 1, 1)] * 6    # Left - cyan
    )

    return Mesh3D(device, shader_library, vertices, colors, **kwargs)
