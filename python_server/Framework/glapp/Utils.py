import numpy as np
from OpenGL.GL import *
import copy
from enum import *

class EditMode(Enum):
    NOT_SELECTED, POSITION, SCALE, ROTATION = range(0, 4)

    # See https://bugs.python.org/issue30545 for explanations
    def __eq__(self, other):
        return self.value == other.value

def format_vertices(vertices, triangles):
    all_triangles = []
    for t in range(0, len(triangles), 3):
        all_triangles.append(vertices[triangles[t]])
        all_triangles.append(vertices[triangles[t+1]])
        all_triangles.append(vertices[triangles[t+2]])
    return np.array(all_triangles, np.float32)

def compile_shader(shader_type, shader_source):
    shader_id = glCreateShader(shader_type)
    glShaderSource(shader_id, shader_source)
    glCompileShader(shader_id)
    compile_success = glGetShaderiv(shader_id, GL_COMPILE_STATUS)
    if not compile_success:
        error_message = glGetShaderInfoLog(shader_id)
        glDeleteShader(shader_id)
        error_message = "\n" + error_message.decode("utf-8")
        raise Exception(error_message)
    return shader_id

def create_program(vertex_shader_code, fragment_shader_code):
    vertex_shader_id = compile_shader(GL_VERTEX_SHADER, vertex_shader_code)
    fragment_shader_id = compile_shader(GL_FRAGMENT_SHADER, fragment_shader_code)
    program_id = glCreateProgram()
    glAttachShader(program_id, vertex_shader_id)
    glAttachShader(program_id, fragment_shader_id)
    glLinkProgram(program_id)
    link_success = glGetProgramiv(program_id, GL_LINK_STATUS)
    if not link_success:
        info = glGetProgramInfoLog(program_id)
        raise RuntimeError(info)
    glDeleteShader(vertex_shader_id)
    glDeleteShader(fragment_shader_id)
    return program_id

def offset_object_boundaries(boundaries, offset):
    new_boundaries = copy.deepcopy(boundaries)
    size_x = boundaries[3] - boundaries[0]
    new_boundaries[0] -= size_x * offset
    new_boundaries[3] += size_x * offset
    size_y = boundaries[4] - boundaries[1]
    new_boundaries[1] -= size_y * offset
    new_boundaries[4] += size_y * offset
    size_z = boundaries[5] - boundaries[2]
    new_boundaries[2] -= size_z * offset
    new_boundaries[5] += size_z * offset
    return new_boundaries
