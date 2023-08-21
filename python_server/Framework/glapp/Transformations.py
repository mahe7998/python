import numpy as np
from math import *

def identity_mat():
    return np.array([[1, 0, 0, 0],
                     [0, 1, 0, 0],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]], np.float32)

def translate_mat(x, y, z):
    return np.array([[1, 0, 0, x],
                     [0, 1, 0, y],
                     [0, 0, 1, z],
                     [0, 0, 0, 1]], np.float32)

def scale_mat(s):
    return np.array([[s, 0, 0, 0],
                     [0, s, 0, 0],
                     [0, 0, s, 0],
                     [0, 0, 0, 1]], np.float32)
def scale_mat3(sx, sy, sz):
    return np.array([[sx, 0, 0, 0],
                     [0, sy, 0, 0],
                     [0, 0, sz, 0],
                     [0, 0, 0, 1]], np.float32)

def rotate_x_mat(angle):
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[1, 0, 0, 0],
                     [0, c, -s, 0],
                     [0, s, c, 0],
                     [0, 0, 0, 1]], np.float32)

def rotate_y_mat(angle):
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[c, 0, s, 0],
                     [0, 1, 0, 0],
                     [-s, 0, c, 0],
                     [0, 0, 0, 1]], np.float32)

def rotate_z_mat(angle):
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    return np.array([[c, -s, 0, 0],
                     [s, c, 0, 0],
                     [0, 0, 1, 0],
                     [0, 0, 0, 1]], np.float32)

def translate(matrix, x, y, z):
    trans = translate_mat(x, y, z)
    return matrix @ trans

def scale(matrix, s):
    sc = scale_mat(s)
    return matrix @ sc

def scale3(matrix, x, y, z):
    sc3 = scale_mat3(x, y, z)
    return matrix @ sc3

def rotate(matrix, angle, axis, local=True):
    rot = identity_mat()
    if axis.lower() == "x":
        rot = rotate_x_mat(angle)
    elif axis.lower() == "y":
        rot = rotate_y_mat(angle)
    elif axis.lower() == "z":
        rot = rotate_z_mat(angle)
    else:
        raise Exception("Unknown AXIS " + axis + "!")
    if local:
        return matrix @ rot
    else:
        return rot @ matrix

def rotate_axis(angle, axis):
    theta = radians(angle)
    c = cos(theta)
    s = sin(theta)
    x = axis[0]
    y = axis[1]
    z = axis[2]
    x2 = x * x
    y2 = y * y
    z2 = z * z
    return np.array(
        [[x2*(1-c)+c, x*y*(1-c)-z*s, x*z*(1-c)+y*s, 0],
         [y*x*(1-c)+z*s, y2*(1-c)+c, y*z*(1-c)-x*s, 0],
         [x*z*(1-c)-y*s, y*z*(1-c)+x*s, z2*(1-c)+c, 0],
         [0, 0, 0, 1]], np.float32)

def rotateA(matrix, angle, axis, local=True):
    rot = rotate_axis(angle, axis)
    if local:
        return matrix @ rot
    else:
        return rot @ matrix