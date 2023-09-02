from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GL import shaders

import glfw
import freetype
#import glm

import numpy as np
from math import *

from PIL import Image
import time


fontfile = "FreeMono.ttf"
#fontfile = r'C:\source\resource\fonts\gnu-freefont_freesans\freesans.ttf'

def _get_rendering_vertices(vertices, xpos, ypos, w, h, top, tex_l=0.0, tex_r=1.0, tex_t=1.0, tex_b=0.0):
    vertices.append((xpos,     ypos + (h-top) - h, tex_l, tex_b)) # 0, 0
    vertices.append((xpos,     ypos + (h-top),     tex_l, tex_t)) # 0, 1
    vertices.append((xpos + w, ypos + (h-top),     tex_r, tex_t)) # 1, 1
    vertices.append((xpos,     ypos + (h-top) - h, tex_l, tex_b)) # 0, 0
    vertices.append((xpos + w, ypos + (h-top),     tex_r, tex_t)) # 1, 1
    vertices.append((xpos + w, ypos + (h-top) - h, tex_r, tex_b)) # 1, 0

VERTEX_SHADER = """
        #version 330 core
        layout (location = 0) in vec4 vertex; // <vec2 pos, vec2 tex>
        out vec2 TexCoords;

        uniform mat4 projection;

        void main()
        {
            gl_Position = projection * vec4(vertex.xy, 0.0, 1.0);
            TexCoords = vertex.zw;
        }
       """

FRAGMENT_SHADER = """
        #version 330 core
        in vec2 TexCoords;
        out vec4 color;

        uniform sampler2D tex;
        uniform vec3 textColor;

        void main()
        {    
            vec4 sampled = vec4(1.0, 1.0, 1.0, texture(tex, TexCoords).r);
            color = vec4(textColor, 1.0) * sampled;
        }
        """

shaderProgram = None
font_texture = None
VBO = None
VAO = None

CHAR_SIZE_W = 12*64
CHAR_SIZE_H = 15*64

def ortho_matrix(left, right, bottom, top, near, far):
    """
    Returns an orthographic projection matrix.
    """
    tx = -(right + left) / (right - left)
    ty = -(top + bottom) / (top - bottom)
    tz = -(far + near) / (far - near)

    return np.array([
        [2 / (right - left), 0, 0, tx],
        [0, 2 / (top - bottom), 0, ty],
        [0, 0, -2 / (far - near), tz],
        [0, 0, 0, 1]
    ], dtype=np.float32)

def initialize():
    global VERTEXT_SHADER
    global FRAGMENT_SHADER
    global shaderProgram
    global font_texture
    global VBO
    global VAO
    global CHAR_SIZE_W
    global CHAR_SIZE_H

    VAO = glGenVertexArrays(1)
    glBindVertexArray(VAO)
    glEnable(GL_MULTISAMPLE)

    #compiling shaders
    vertexshader = shaders.compileShader(VERTEX_SHADER, GL_VERTEX_SHADER)
    fragmentshader = shaders.compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER)

    #creating shaderProgram
    shaderProgram = shaders.compileProgram(vertexshader, fragmentshader)
    glUseProgram(shaderProgram)

    #get projection
    #problem
    
    shader_projection = glGetUniformLocation(shaderProgram, "projection")
    projection = ortho_matrix(0, 640, 640, 0, 1 , -1)
    #projection = glm.ortho(0, 640, 640, 0)
    glUniformMatrix4fv(shader_projection, 1, GL_TRUE, projection)
    
    #disable byte-alignment restriction
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

    face = freetype.Face(fontfile)
    face.set_char_size(CHAR_SIZE_W, CHAR_SIZE_H)

    # Configure VAO/VBO to load all glyphs into font_texture
    fbo = glGenFramebuffers(1)
    font_texture = glGenTextures(1)
    
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, fbo)
    glBindTexture(GL_TEXTURE_2D, font_texture)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, (CHAR_SIZE_W*(128-30+1))//64, 2*(CHAR_SIZE_H//64), 0, GL_RGB, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, font_texture, 0)
    # Set the list of draw buffers.
    DrawBuffers = [GL_COLOR_ATTACHMENT0];
    glDrawBuffers(1, DrawBuffers); # "1" is the size of DrawBuffers
    fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if fb_status != GL_FRAMEBUFFER_COMPLETE:
        raise Exception("Frame buffer error, status: " + str(fb_status))
    glViewport(0,0,(CHAR_SIZE_W*(128-30+1))//64, 2*(CHAR_SIZE_H//64))
 
    #configure VAO/VBO for texture quads    
    VBO = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, 6 * 4 * 4, None, GL_DYNAMIC_DRAW)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 0, None)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindVertexArray(0)

    glUniform3f(glGetUniformLocation(
        shaderProgram, "textColor"),
        1.0, 1.0, 1.0)        
    glActiveTexture(GL_TEXTURE0)

    glBindVertexArray(VAO)
    for i in range(30, 128):
        face.load_char(chr(i))
        glyph = face.glyph
        if chr(i) > ' ':
            print ("Loading character '%c': width: %d, height: %d, left: %d, top: %d" % (chr(i), glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_left, glyph.bitmap_top))

        #generate texture
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RED, 
            glyph.bitmap.width, glyph.bitmap.rows, 0,
            GL_RED, GL_UNSIGNED_BYTE, glyph.bitmap.buffer)

        #texture options
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        #draw vertices
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        vertices = []
        _get_rendering_vertices(
            vertices,
            ((i-30)*CHAR_SIZE_W)//64, 
            CHAR_SIZE_H//64, 
            glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_top)
        final_vertices = np.array(vertices, dtype=np.float32)
        glBufferSubData(GL_ARRAY_BUFFER, 0, final_vertices.nbytes, final_vertices)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        #render quad
        glDrawArrays(GL_TRIANGLES, 0, len(vertices))

    glBindTexture(GL_TEXTURE_2D, 0)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
 
    
def render_text(window, text, n_rows, m_cols, x, y, scale, color):
    global shaderProgram
    global font_texture
    global VBO
    global VAO
    global CHAR_SIZE_W
    global CHAR_SIZE_H
    
    face = freetype.Face(fontfile)
    face.set_char_size(CHAR_SIZE_W, CHAR_SIZE_H)
    glUniform3f(glGetUniformLocation(
        shaderProgram, "textColor"),
        color[0]/255,color[1]/255,color[2]/255)             
    glActiveTexture(GL_TEXTURE0)
    
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glBindVertexArray(VAO)
    vertices = []
    for n in range(0, n_rows-1):
        for m in range(0, m_cols-1):
            _get_rendering_vertices(
                vertices,
                (n*CHAR_SIZE_W)//64, 
                ((m+1)*CHAR_SIZE_H)//64, 
                CHAR_SIZE_W//64, CHAR_SIZE_H//64,
                CHAR_SIZE_H//64, # all characters have the same height
                ((ord(text[n][m])-30))/(128-30+1), # texture left
                ((ord(text[n][m])-29))/(128-30+1)) # texture right

    final_vertices = np.array(vertices, dtype=np.float32)

    #render glyph texture over quad
    glBindTexture(GL_TEXTURE_2D, font_texture)
    #texture options
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    #update content of VBO memory
    VBO2 = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, VBO2)
    glBufferData(GL_ARRAY_BUFFER, final_vertices.size, final_vertices, GL_DYNAMIC_DRAW) # or GL_STATIC_DRAW?
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 0, None) # or GL_TRUE?
    glBindVertexArray(0)
    glBindBuffer(GL_ARRAY_BUFFER, 0)

    #render quad
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    glViewport(0, 0, m_cols * CHAR_SIZE_W // 64, n_rows * CHAR_SIZE_H // 64)
    glDrawArrays(GL_TRIANGLES, 0, len(vertices))

    glBindVertexArray(0)
    glBindTexture(GL_TEXTURE_2D, 0)

    glfw.swap_buffers(window)
    glfw.poll_events()

def print_text(x, y, text, text_array):
    for c in text:
        text_array[y][x] = c
        x += 1
    
def main():
    glfw.init()

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL_TRUE)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, 4)

    n_char_cols = 20
    m_char_rows = 10
    text = [[' ' for i in range(n_char_cols)] for j in range(m_char_rows)]
    window = glfw.create_window(
        n_char_cols*CHAR_SIZE_W // 64, 
        m_char_rows*CHAR_SIZE_H // 64,"EXAMPLE PROGRAM",None,None)    
    glfw.make_context_current(window)
    
    initialize()
    while not glfw.window_should_close(window):
        glfw.poll_events()
        glClearColor(0,0,0,1)
        glClear(GL_COLOR_BUFFER_BIT)
        print_text(0, 0, "Hello World!", text)
        render_text(window, text, m_char_rows, n_char_cols, 20, 40, 1, (255, 255, 255))

    glfw.terminate()

if __name__ == '__main__':
    main()
