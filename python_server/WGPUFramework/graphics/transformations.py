"""
Transformation matrix utilities for 3D graphics.
Provides matrices for translation, rotation, scaling, and projection.

Note: WebGPU uses a different clip space than OpenGL:
- WebGPU: Z range [0, 1], Y-up
- OpenGL: Z range [-1, 1], Y-up
"""

import numpy as np
from math import cos, sin, tan, radians


def identity_mat():
    """Return 4x4 identity matrix."""
    return np.array([[1, 0, 0, 0],
                     [0, 1, 0, 0],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]], np.float32)


def translate_mat(x, y, z):
    """Return translation matrix."""
    return np.array([[1, 0, 0, x],
                     [0, 1, 0, y],
                     [0, 0, 1, z],
                     [0, 0, 0, 1]], np.float32)


def scale_mat(s):
    """Return uniform scale matrix."""
    return np.array([[s, 0, 0, 0],
                     [0, s, 0, 0],
                     [0, 0, s, 0],
                     [0, 0, 0, 1]], np.float32)


def scale_mat3(sx, sy, sz):
    """Return non-uniform scale matrix."""
    return np.array([[sx, 0, 0, 0],
                     [0, sy, 0, 0],
                     [0, 0, sz, 0],
                     [0, 0, 0, 1]], np.float32)


def rotate_x_mat(angle):
    """Return rotation matrix around X axis (angle in degrees)."""
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[1, 0, 0, 0],
                     [0, c, -s, 0],
                     [0, s, c, 0],
                     [0, 0, 0, 1]], np.float32)


def rotate_y_mat(angle):
    """Return rotation matrix around Y axis (angle in degrees)."""
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[c, 0, s, 0],
                     [0, 1, 0, 0],
                     [-s, 0, c, 0],
                     [0, 0, 0, 1]], np.float32)


def rotate_z_mat(angle):
    """Return rotation matrix around Z axis (angle in degrees)."""
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[c, -s, 0, 0],
                     [s, c, 0, 0],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]], np.float32)


def rotate_axis(angle, axis):
    """
    Return rotation matrix around arbitrary axis (Rodrigues' rotation formula).
    Angle in degrees, axis is (x, y, z) tuple.
    """
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    x, y, z = axis
    x2 = x * x
    y2 = y * y
    z2 = z * z
    return np.array(
        [[x2*(1-c)+c, x*y*(1-c)-z*s, x*z*(1-c)+y*s, 0],
         [y*x*(1-c)+z*s, y2*(1-c)+c, y*z*(1-c)-x*s, 0],
         [x*z*(1-c)-y*s, y*z*(1-c)+x*s, z2*(1-c)+c, 0],
         [0, 0, 0, 1]], np.float32)


def translate(matrix, x, y, z):
    """Apply translation to matrix."""
    return matrix @ translate_mat(x, y, z)


def scale(matrix, s):
    """Apply uniform scale to matrix."""
    return matrix @ scale_mat(s)


def scale3(matrix, x, y, z):
    """Apply non-uniform scale to matrix."""
    return matrix @ scale_mat3(x, y, z)


def rotate(matrix, angle, axis, local=True):
    """Apply rotation around named axis ('x', 'y', or 'z')."""
    if axis.lower() == "x":
        rot = rotate_x_mat(angle)
    elif axis.lower() == "y":
        rot = rotate_y_mat(angle)
    elif axis.lower() == "z":
        rot = rotate_z_mat(angle)
    else:
        raise Exception(f"Unknown axis '{axis}'!")

    if local:
        return matrix @ rot
    else:
        return rot @ matrix


def rotateA(matrix, angle, axis, local=True):
    """Apply rotation around arbitrary axis."""
    rot = rotate_axis(angle, axis)
    if local:
        return matrix @ rot
    else:
        return rot @ matrix


def perspective_mat(fov_degrees, aspect_ratio, near, far):
    """
    Create perspective projection matrix for WebGPU.

    WebGPU uses Z range [0, 1] (unlike OpenGL's [-1, 1]).

    Args:
        fov_degrees: Vertical field of view in degrees
        aspect_ratio: Width / height
        near: Near clipping plane
        far: Far clipping plane

    Returns:
        4x4 projection matrix (row-major)
    """
    fov_rad = radians(fov_degrees)
    f = 1.0 / tan(fov_rad / 2.0)

    # WebGPU-style perspective (Z maps to [0, 1])
    return np.array([
        [f / aspect_ratio, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, far / (near - far), (near * far) / (near - far)],
        [0, 0, -1, 0]
    ], np.float32)


def orthographic_mat(left, right, bottom, top, near, far):
    """
    Create orthographic projection matrix for WebGPU.

    Args:
        left, right: Left and right clipping planes
        bottom, top: Bottom and top clipping planes
        near, far: Near and far clipping planes

    Returns:
        4x4 projection matrix (row-major)
    """
    return np.array([
        [2.0 / (right - left), 0, 0, -(right + left) / (right - left)],
        [0, 2.0 / (top - bottom), 0, -(top + bottom) / (top - bottom)],
        [0, 0, 1.0 / (near - far), near / (near - far)],
        [0, 0, 0, 1]
    ], np.float32)


def look_at(eye, target, up):
    """
    Create view matrix using look-at parameters.

    Args:
        eye: Camera position (x, y, z)
        target: Point to look at (x, y, z)
        up: Up vector (x, y, z)

    Returns:
        4x4 view matrix (row-major)
    """
    eye = np.array(eye, np.float32)
    target = np.array(target, np.float32)
    up = np.array(up, np.float32)

    # Forward vector (from eye to target)
    f = target - eye
    f = f / np.linalg.norm(f)

    # Right vector
    r = np.cross(f, up)
    r = r / np.linalg.norm(r)

    # Corrected up vector
    u = np.cross(r, f)

    # View matrix
    return np.array([
        [r[0], r[1], r[2], -np.dot(r, eye)],
        [u[0], u[1], u[2], -np.dot(u, eye)],
        [-f[0], -f[1], -f[2], np.dot(f, eye)],
        [0, 0, 0, 1]
    ], np.float32)


def inverse_mat(matrix):
    """Return inverse of 4x4 matrix."""
    return np.linalg.inv(matrix).astype(np.float32)


def transpose_mat(matrix):
    """Return transpose of matrix."""
    return matrix.T.astype(np.float32)
