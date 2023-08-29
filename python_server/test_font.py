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


fontfile = "Vera.ttf"
#fontfile = r'C:\source\resource\fonts\gnu-freefont_freesans\freesans.ttf'

class CharacterSlot:
    def __init__(self, texture, glyph):
        self.texture = texture
        self.textureSize = (glyph.bitmap.width, glyph.bitmap.rows)

        if isinstance(glyph, freetype.GlyphSlot):
            self.bearing = (glyph.bitmap_left, glyph.bitmap_top)
            self.advance = glyph.advance.x
        elif isinstance(glyph, freetype.BitmapGlyph):
            self.bearing = (glyph.left, glyph.top)
            self.advance = None
        else:
            raise RuntimeError('unknown glyph type')

def _get_rendering_buffer(xpos, ypos, w, h, zfix=0.0):
    return np.asarray([
        xpos,     ypos - h, 0, 0,
        xpos,     ypos,     0, 1,
        xpos + w, ypos,     1, 1,
        xpos,     ypos - h, 0, 0,
        xpos + w, ypos,     1, 1,
        xpos + w, ypos - h, 1, 0
    ], np.float32)


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

        uniform sampler2D text;
        uniform vec3 textColor;

        void main()
        {    
            vec4 sampled = vec4(1.0, 1.0, 1.0, texture(text, TexCoords).r);
            color = vec4(textColor, 1.0) * sampled;
        }
        """

shaderProgram = None
Characters = dict()
VBO = None
VAO = None

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
    global Characters
    global VBO
    global VAO

    VAO = glGenVertexArrays(1)
    glBindVertexArray(VAO)

    #compiling shaders
    vertexshader = shaders.compileShader(VERTEX_SHADER, GL_VERTEX_SHADER)
    fragmentshader = shaders.compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER)

    #creating shaderProgram
    shaderProgram = shaders.compileProgram(vertexshader, fragmentshader)
    glUseProgram(shaderProgram)

    #get projection
    #problem
    
    shader_projection = glGetUniformLocation(shaderProgram, "projection")
    projection = ortho_matrix(0, 300, 300, 0, 1 , -1)
    #projection = glm.ortho(0, 640, 640, 0)
    glUniformMatrix4fv(shader_projection, 1, GL_TRUE, projection)
    
    #disable byte-alignment restriction
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

    face = freetype.Face(fontfile)
    face.set_char_size( 48*64 )

    #load first 128 characters of ASCII set
    for i in range(0,128):
        face.load_char(chr(i))
        glyph = face.glyph
        
        #generate texture
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RED, glyph.bitmap.width, glyph.bitmap.rows, 0,
                     GL_RED, GL_UNSIGNED_BYTE, glyph.bitmap.buffer)

        #texture options
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        #now store character for later use
        Characters[chr(i)] = CharacterSlot(texture,glyph)
        
    glBindTexture(GL_TEXTURE_2D, 0)

    #configure VAO/VBO for texture quads
    
    VBO = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, VBO)
    glBufferData(GL_ARRAY_BUFFER, 6 * 4 * 4, None, GL_DYNAMIC_DRAW)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 0, None)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindVertexArray(0)
    
def render_text(window,text,x,y,scale,color):
    global shaderProgram
    global Characters
    global VBO
    global VAO
    
    face = freetype.Face(fontfile)
    face.set_char_size(48*64)
    glUniform3f(glGetUniformLocation(shaderProgram, "textColor"),
                color[0]/255,color[1]/255,color[2]/255)
               
    glActiveTexture(GL_TEXTURE0)
    
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    glBindVertexArray(VAO)
    for c in text:
        ch = Characters[c]
        w, h = ch.textureSize
        w = w*scale
        h = h*scale
        vertices = _get_rendering_buffer(x,y,w,h)

        #render glyph texture over quad
        glBindTexture(GL_TEXTURE_2D, ch.texture)
        #update content of VBO memory
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferSubData(GL_ARRAY_BUFFER, 0, vertices.nbytes, vertices)

        glBindBuffer(GL_ARRAY_BUFFER, 0)
        #render quad
        glDrawArrays(GL_TRIANGLES, 0, 6)
        #now advance cursors for next glyph (note that advance is number of 1/64 pixels)
        x += (ch.advance>>6)*scale

    glBindVertexArray(0)
    glBindTexture(GL_TEXTURE_2D, 0)

    glfw.swap_buffers(window)
    glfw.poll_events()
    
def main():
    glfw.init()
    #glfwWindowHint(GLFW_SAMPLES, 4)

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL_TRUE)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    window = glfw.create_window(640, 640,"EXAMPLE PROGRAM",None,None)    
    glfw.make_context_current(window)
    
    initialize()
    while not glfw.window_should_close(window):
        glfw.poll_events()
        glClearColor(0,0,0,1)
        glClear(GL_COLOR_BUFFER_BIT)
        render_text(window, 'Hello World', 20, 40, 1, (255, 0, 0))

    glfw.terminate()

if __name__ == '__main__':
    main()
