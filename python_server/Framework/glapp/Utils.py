import numpy as np
from OpenGL.GL import *
import copy
from enum import *

class EditMode(Enum):
    NOT_SELECTED, POSITION, SCALE, ROTATION = range(0, 4)

    # See https://bugs.python.org/issue30545 for explanations
    def __eq__(self, other):
        return self.value == other.value
    
class Alignments(Enum):
    TOP_LEFT, TOP_CENTER, TOP_RIGHT, CENTER_LEFT, CENTER, CENTER_RIGHT, BOTTOM_LEFT, BOTTOM_CENTER, \
        BOTTOM_RIGHT, TOP_TO_BOTTOM_LEFT, TOP_TO_BOTTOM_CENTER, TOP_TO_BOTTOM_RIGHT = range(0, 12)

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

def get_rendering_vertices(vertices, xpos, ypos, w, h, top):
    vertices.append((xpos,     ypos + (h-top) - h, -1.0)) # 0, 0
    vertices.append((xpos,     ypos + (h-top)    , -1.0)) # 0, 1
    vertices.append((xpos + w, ypos + (h-top)    , -1.0)) # 1, 1
    vertices.append((xpos,     ypos + (h-top) - h, -1.0)) # 0, 0
    vertices.append((xpos + w, ypos + (h-top)    , -1.0)) # 1, 1
    vertices.append((xpos + w, ypos + (h-top) - h, -1.0)) # 1, 0

def get_rendering_texes(texes, tex_l=0.0, tex_r=1.0, tex_t=1.0, tex_b=0.0):
    texes.append((tex_l, tex_b)) # 0, 0
    texes.append((tex_l, tex_t)) # 0, 1
    texes.append((tex_r, tex_t)) # 1, 1
    texes.append((tex_l, tex_b)) # 0, 0
    texes.append((tex_r, tex_t)) # 1, 1
    texes.append((tex_r, tex_b)) # 1, 0

def get_ortho_matrix(left, right, bottom, top, near, far):
    """
    Returns an orthographic projection matrix.
    """
    tx = -(right + left) / (right - left)
    ty = -(top + bottom) / (top - bottom)
    tz = -(far + near) / (far - near)
    return np.array([[2/(right-left), 0, 0, tx],
                     [0, 2/(top-bottom), 0, ty],
                     [0, 0, -2/(far-near), tz],
                     [0, 0, 0, 1]], dtype=np.float32)

def unit_vector(vector):
    """ Returns the unit vector of the vector.  """
    return vector / np.linalg.norm(vector)

def angle_to(v1, v2):
    """ Returns the angle in radians between vectors 'v1' and 'v2'::

            >>> angle_between((1, 0, 0), (0, 1, 0))
            1.5707963267948966
            >>> angle_between((1, 0, 0), (1, 0, 0))
            0.0
            >>> angle_between((1, 0, 0), (-1, 0, 0))
            3.141592653589793
    """
    v1_u = unit_vector(v1)
    v2_u = unit_vector(v2)
    return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))
