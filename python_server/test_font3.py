from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GL import shaders


import glfw
import freetype

import numpy as np
from math import *

from PIL import Image
from PIL import ImageOps
import time

fontfile = "FreeMono.ttf"
CHAR_SIZE_W = 30*64
CHAR_SIZE_H = 45*64
squeeze_x = 10*64
squeeze_y = 14*64
first_char = 32 # space
last_char = 127

VERTEX_SHADER = """
        #version 330 core
        in vec2 vertex;
        in vec2 texCoords;
        out vec2 TexCoords;

        uniform mat4 projection;

        void main()
        {
            gl_Position = projection * vec4(vertex, 0.0, 1.0);
            TexCoords = texCoords;
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
    global squeeze_x
    global squeeze_y
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

    #font texture size
    font_texture_width = ((CHAR_SIZE_W-squeeze_x)*(last_char-first_char))//64    
    font_texture_height = int(((CHAR_SIZE_H-squeeze_y)//64) * 1.5)

    #get projection
    shader_projection = glGetUniformLocation(shaderProgram, "projection")
    projection = ortho_matrix(0, font_texture_width, font_texture_height, 0, 1 , -1)
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
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, font_texture_width, font_texture_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glBindTexture(GL_TEXTURE_2D, 0)
    glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, font_texture, 0)
    
    DrawBuffers = [GL_COLOR_ATTACHMENT0]
    glDrawBuffers(1, DrawBuffers); # "1" is the size of DrawBuffers
    fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if fb_status != GL_FRAMEBUFFER_COMPLETE:
        raise Exception("Frame buffer error, status: " + str(fb_status))

    glViewport(0, 0, font_texture_width, font_texture_height)
    glClearColor(0.0,0.0,0.0,1)
    glClear(GL_COLOR_BUFFER_BIT)

    #configure VAO/VBO for texture quads    
    VBO = glGenBuffers(1)
    TEX = glGenBuffers(1)
    glBindVertexArray(0)

    glUniform3f(glGetUniformLocation(
        shaderProgram, "textColor"),
        1.0, 1.0, 1.0)        
    glActiveTexture(GL_TEXTURE0)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glBindVertexArray(VAO)
    for i in range(first_char, last_char):
        face.load_char(chr(i))
        glyph = face.glyph
        #if chr(i) > ' ':
        #    print ("Loading character '%c': width: %d, height: %d, left: %d, top: %d" % (chr(i), glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_left, glyph.bitmap_top))

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
        pos_x = ((i-first_char)*(CHAR_SIZE_W-squeeze_x))//64
        pos_y = (CHAR_SIZE_H-int(squeeze_y/1.5))//64
        _get_rendering_vertices(
            vertices,
            pos_x, pos_y,
            glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_top)
        final_vertices = np.array(vertices, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_vertices.nbytes, final_vertices, GL_DYNAMIC_DRAW)
        location_id = glGetAttribLocation(shaderProgram, "vertex")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        glBindBuffer(GL_ARRAY_BUFFER, TEX)
        texes = []
        _get_rendering_texes(texes)
        final_texes = np.array(texes, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_texes.nbytes, final_texes, GL_STATIC_DRAW)
        location_id = glGetAttribLocation(shaderProgram, "texCoords")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        #render quad
        glDrawArrays(GL_TRIANGLES, 0, len(vertices))

    # Code below works and is used to verify the font above works correctly
    glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo)
    data = glReadPixels(0, 0, font_texture_width, font_texture_height, GL_RGBA, GL_UNSIGNED_BYTE)
    image = Image.frombytes("RGBA", (font_texture_width, font_texture_height), data)
    image = ImageOps.flip(image) # in my case image is flipped top-bottom for some reason
    image.save('font.png', 'PNG')

    glBindTexture(GL_TEXTURE_2D, 0)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)

def get_texes(texes, pos_in_tex, c):
    global first_char
    global last_char
    tex_l = ((ord(c)-first_char+0))/(last_char-first_char)
    tex_r =((ord(c)-first_char+1))/(last_char-first_char)

    texes[pos_in_tex][0] = tex_l  # 0, 0
    pos_in_tex += 1
    texes[pos_in_tex][0] = tex_l # 0, 1
    pos_in_tex += 1
    texes[pos_in_tex][0] = tex_r # 1, 1
    pos_in_tex += 1
    texes[pos_in_tex][0] = tex_l # 0, 0
    pos_in_tex += 1
    texes[pos_in_tex][0] = tex_r # 1, 1
    pos_in_tex += 1
    texes[pos_in_tex][0] = tex_r # 1, 0

def print_text(text_array, texes, x, y, text, n_rows, m_cols):
    pos_in_tex = (y * m_cols + x) * 6
    if y < n_rows and x < m_cols:
        for c in text:
            text_array[y][x] = c
            get_texes(texes, pos_in_tex, text_array[y][x])
            pos_in_tex += 6
            x += 1
            if x >= m_cols:
                x = 0
                y += 1
                if y >= n_rows:
                    break

def print_text_into_array(text_array, x, y, text, n_rows, m_cols):
    if y < n_rows and x < m_cols:
        for c in text:
            text_array[y][x] = c
            x += 1
            if x >= m_cols:
                x = 0
                y += 1
                if y >= n_rows:
                    break

# Call after changing text_array directly
def update_complete_text(text_array, texes, n_rows, m_cols):
    pos_in_tex = 0
    for n in range(0, n_rows):
        for m in range(0, m_cols):
            get_texes(texes, pos_in_tex, text_array[n][m])
            pos_in_tex += 6

def _get_rendering_vertices(vertices, xpos, ypos, w, h, top):
    vertices.append((xpos,     ypos + (h-top) - h)) # 0, 0
    vertices.append((xpos,     ypos + (h-top)    )) # 0, 1
    vertices.append((xpos + w, ypos + (h-top),   )) # 1, 1
    vertices.append((xpos,     ypos + (h-top) - h)) # 0, 0
    vertices.append((xpos + w, ypos + (h-top),   )) # 1, 1
    vertices.append((xpos + w, ypos + (h-top) - h)) # 1, 0

def _get_rendering_texes(texes, tex_l=0.0, tex_r=1.0, tex_t=1.0, tex_b=0.0):
    texes.append((tex_l, tex_b)) # 0, 0
    texes.append((tex_l, tex_t)) # 0, 1
    texes.append((tex_r, tex_t)) # 1, 1
    texes.append((tex_l, tex_b)) # 0, 0
    texes.append((tex_r, tex_t)) # 1, 1
    texes.append((tex_r, tex_b)) # 1, 0

def init_text(n_rows, m_cols, x, y):
    global CHAR_SIZE_W
    global CHAR_SIZE_H
    global squeeze_x
    global squeeze_y
   
    vertices = []
    texes = []
    window_height = (n_rows*(CHAR_SIZE_H-squeeze_y)) // 64
    for n in range(0, n_rows):
        for m in range(0, m_cols):
            _get_rendering_vertices(
                vertices,
                (squeeze_x//2+(m*(CHAR_SIZE_W-squeeze_x)))//64, 
                window_height - (n*(CHAR_SIZE_H-squeeze_y))//64, 
                (CHAR_SIZE_W-squeeze_x)//64, (CHAR_SIZE_H-squeeze_y)//64,
                (CHAR_SIZE_H-squeeze_y)//64) # all characters have the same height
            _get_rendering_texes(
                texes,
                ((ord(' ')-first_char+0))/(last_char-first_char), # texture left
                ((ord(' ')-first_char+1))/(last_char-first_char)) # texture right
    return np.array(vertices, dtype=np.float32), np.array(texes, dtype=np.float32),
    
def render_text(vertices, texes, n_rows, m_cols, color):
    global shaderProgram
    global font_texture
    global VAO
    global CHAR_SIZE_W
    global CHAR_SIZE_H
    global squeeze_x
    global squeeze_y
    
    glUniform3f(glGetUniformLocation(
        shaderProgram, "textColor"),
        color[0]/255,color[1]/255,color[2]/255)             
    glActiveTexture(GL_TEXTURE0)

    # Window size
    window_width = (m_cols*(CHAR_SIZE_W-squeeze_x)) // 64
    window_height = (n_rows*(CHAR_SIZE_H-squeeze_y)) // 64

    glUseProgram(shaderProgram)
    shader_projection = glGetUniformLocation(shaderProgram, "projection")
    projection = ortho_matrix(0, window_width, 0, window_height, 1 , -1)
    glUniformMatrix4fv(shader_projection, 1, GL_TRUE, projection)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glBindVertexArray(VAO)
    glViewport(0, 0, window_width, window_height)

    fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    if fb_status != GL_FRAMEBUFFER_COMPLETE:
        raise Exception("Frame buffer error, status: " + str(fb_status))

    #render glyph texture over quad
    glBindTexture(GL_TEXTURE_2D, font_texture)
    
    #texture options
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    #update content of VBO memory
    VBO = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_DYNAMIC_DRAW) # or GL_STATIC_DRAW?
    location_id = glGetAttribLocation(shaderProgram, "vertex")
    glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
    glEnableVertexAttribArray(location_id)
    glBindBuffer(GL_ARRAY_BUFFER, 0)

    TEX = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, TEX)
    glBufferData(GL_ARRAY_BUFFER, texes.nbytes, texes, GL_DYNAMIC_DRAW) # or GL_STATIC_DRAW?
    location_id = glGetAttribLocation(shaderProgram, "texCoords")
    glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
    glEnableVertexAttribArray(location_id)
    glBindBuffer(GL_ARRAY_BUFFER, 0)

    #render vertices
    glDrawArrays(GL_TRIANGLES, 0, len(vertices))

    glBindVertexArray(0)
    glBindTexture(GL_TEXTURE_2D, 0)

def main():
    glfw.init()

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL_TRUE)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, 4)

    n_char_cols = 30
    m_char_rows = 10
    text_array = [[' ' for i in range(n_char_cols)] for j in range(m_char_rows)]

    window_width = (n_char_cols*(CHAR_SIZE_W-squeeze_x)) // 64   
    window_height = (m_char_rows*(CHAR_SIZE_H-squeeze_y)) // 64

    window = glfw.create_window(
        window_width//2, 
        window_height//2,
        "Font Test", None, None)    
    glfw.make_context_current(window)

    vertices, texes = init_text(m_char_rows, n_char_cols, 0, 0)

    print_text(text_array, texes, 4, 4, "This is a nice test!", m_char_rows, n_char_cols)
    
    #You can also do this (slower):
    #print_text_into_array(text_array, 4, 4, "This is a nice test!", m_char_rows, n_char_cols)
    #update_complete_text(text_array, texes, m_char_rows, n_char_cols)

    initialize()
    while not glfw.window_should_close(window):
        glfw.poll_events()
        glClearColor(0, 0, 0, 1)
        glClear(GL_COLOR_BUFFER_BIT)     
        render_text(vertices, texes, m_char_rows, n_char_cols, (255, 0, 0))
        glfw.swap_buffers(window)
        glfw.poll_events()

    glfw.terminate()

if __name__ == '__main__':
    main()
