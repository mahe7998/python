"""
Camera class for 3D rendering in WebGPU.
Handles view and projection matrices with mouse/keyboard controls.
"""

import numpy as np
from math import radians, tan, degrees, acos, sqrt
from .transformations import identity_mat, translate, rotate, perspective_mat


def angle_to(v1, v2):
    """Calculate angle between two vectors."""
    dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
    len1 = sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
    len2 = sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
    if len1 * len2 == 0:
        return 0
    cos_angle = max(-1, min(1, dot / (len1 * len2)))
    return acos(cos_angle)


class Camera:
    """
    Camera for 3D scene navigation.

    Provides:
    - Perspective projection matrix
    - View matrix via transformations
    - Mouse rotation (yaw/pitch)
    - Keyboard movement (WASD-style with arrows)
    - Scroll zoom
    """

    def __init__(self, width, height):
        """Initialize camera with viewport dimensions."""
        self.transformation = identity_mat()
        self.last_mouse_pos = (0, 0)
        self.mouse_sensitivity = 0.1
        self.key_sensitivity = 0.05
        self.projection_mat = None
        self.update_perspective(width, height)

    def update_perspective(self, width, height):
        """Update projection matrix for new viewport size."""
        if height == 0:
            height = 1
        self.projection_mat = perspective_mat(60, width / height, 0.1, 500)

    def rotate(self, yaw, pitch):
        """
        Rotate camera by yaw (around Y) and pitch (around X).
        Pitch is constrained to prevent gimbal lock.
        """
        forward = (
            self.transformation[0, 2],
            self.transformation[1, 2],
            self.transformation[2, 2]
        )
        up = (0, 1, 0)
        angle = degrees(angle_to(forward, up))

        # Apply yaw (world Y axis)
        self.transformation = rotate(self.transformation, yaw, "Y", local=False)

        # Apply pitch (local X axis) with constraints
        if (angle < 170 and pitch > 0) or (angle > 30.0 and pitch < 0):
            self.transformation = rotate(self.transformation, pitch, "X", local=True)

    def relative_move(self, forward=0.0, right=0.0, up=0.0):
        """Move camera relative to its current orientation."""
        self.transformation = translate(self.transformation, right, up, forward)

    def update_mouse(self, delta_x, delta_y):
        """Handle mouse movement for camera rotation."""
        self.rotate(
            delta_x * self.mouse_sensitivity,
            -delta_y * self.mouse_sensitivity
        )

    def zoom(self, amount):
        """Zoom camera (move forward/backward)."""
        self.transformation = translate(
            self.transformation,
            0, 0, -amount * self.mouse_sensitivity * 2
        )

    def handle_key(self, key):
        """Handle keyboard input for camera movement."""
        move_speed = self.key_sensitivity * 5

        if key in ("ArrowUp", "w", "W"):
            self.relative_move(forward=-move_speed)
        elif key in ("ArrowDown", "s", "S"):
            self.relative_move(forward=move_speed)
        elif key in ("ArrowLeft", "a", "A"):
            self.relative_move(right=-move_speed)
        elif key in ("ArrowRight", "d", "D"):
            self.relative_move(right=move_speed)
        elif key in ("q", "Q", "PageUp"):
            self.relative_move(up=move_speed)
        elif key in ("e", "E", "PageDown"):
            self.relative_move(up=-move_speed)

    def get_view_matrix(self):
        """Get the view matrix (inverse of camera transformation)."""
        return np.linalg.inv(self.transformation).astype(np.float32)

    def get_projection_matrix(self):
        """Get the projection matrix."""
        return self.projection_mat

    def get_position(self):
        """Get camera world position."""
        return (
            self.transformation[0, 3],
            self.transformation[1, 3],
            self.transformation[2, 3]
        )

    def get_uniform_data(self):
        """
        Get camera data packed for uniform buffer.
        Returns bytes containing: projection (64 bytes) + view (64 bytes) = 128 bytes

        Note: WGSL uses column-major matrices, so we transpose before sending.
        """
        # Transpose matrices for WGSL (column-major)
        proj = self.projection_mat.T.flatten()
        view = self.get_view_matrix().T.flatten()

        # Pack data: projection (64) + view (64) = 128 bytes
        data = np.zeros(32, dtype=np.float32)  # 32 floats = 128 bytes
        data[0:16] = proj
        data[16:32] = view

        return data.tobytes()
