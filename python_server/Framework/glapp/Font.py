from OpenGL.GL import *
import freetype
import numpy as np
from PIL import Image
from PIL import ImageOps
from .Uniform import *

class Font:

    def __init__(self, shader_program, 
            font_file_name, first_char, last_char, char_width, char_height,
            squeeze_width, squeeze_height, save_png_filename=None):
 
        self.shader_program = shader_program
        self.vao_ref = glGenVertexArrays(1)
        self.font_file_name = font_file_name
        self.first_char = first_char
        self.last_char = last_char
        self.char_width = char_width
        self.char_height = char_height

        glBindVertexArray(self.vao_ref)
        self.shader_program.use()

        font_texture_width = ((char_width-squeeze_width)*(last_char-first_char))//64    
        font_texture_height = int(((char_height-squeeze_height)//64) * 1.5)

        # set ortho projection matrix in shader
        projection_mat = self.get_ortho_matrix(0, font_texture_width, font_texture_height, 0, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection_mat)
   
        #disable byte-alignment restriction
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        face = freetype.Face(font_file_name)
        face.set_char_size(char_width, char_height)

        # Configure VBO to load all glyphs into font_texture
        FBO = glGenFramebuffers(1)
        font_texture = glGenTextures(1)
        
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, FBO)
        glBindTexture(GL_TEXTURE_2D, font_texture)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, font_texture_width, font_texture_height, 
            0, GL_RGBA, GL_UNSIGNED_BYTE, None)
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
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        # Create 2 buffers that will be used for all 6 vertices and 6 UVs 
        # of each character of the font
        VBO = glGenBuffers(1)
        TEX = glGenBuffers(1)
        glBindVertexArray(0)

        Uniform("vec3").load(self.shader_program.program_id, "textColor", [1.0, 1.0, 1.0])
        glActiveTexture(GL_TEXTURE0)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glBindVertexArray(self.vao_ref)

        # Font offset in font texture
        pos_y = (char_height-int(squeeze_height/1.5))//64
        
        # Generate source texture coordinates (same for all characters)
        glBindBuffer(GL_ARRAY_BUFFER, TEX)
        texes = []
        self.get_rendering_texes(texes)
        final_texes = np.array(texes, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_texes.nbytes, final_texes, GL_STATIC_DRAW)
        location_id = glGetAttribLocation(self.shader_program.program_id, "texCoords")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)    

        for i in range(first_char, last_char):
            face.load_char(chr(i))
            glyph = face.glyph

            # Create texture for each character of the font
            texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, texture)
            glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RED, 
                glyph.bitmap.width, glyph.bitmap.rows, 0,
                GL_RED, GL_UNSIGNED_BYTE, glyph.bitmap.buffer)

            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

            # Create 6 vertices (2 triangles) for each character of the font
            glBindBuffer(GL_ARRAY_BUFFER, VBO)
            vertices = []
            pos_x = ((i-first_char)*(char_width-squeeze_width))//64
            self.get_rendering_vertices(
                vertices,
                pos_x, pos_y,
                glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_top)
            final_vertices = np.array(vertices, dtype=np.float32)
            glBufferData(GL_ARRAY_BUFFER, final_vertices.nbytes, final_vertices, GL_DYNAMIC_DRAW)
            location_id = glGetAttribLocation(self.shader_program.program_id, "vertex")
            glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(location_id)
            glBindBuffer(GL_ARRAY_BUFFER, 0)

            # Render both triangles for top left and bottom right of each character
            glDrawArrays(GL_TRIANGLES, 0, len(vertices))

        # Code below works and is used to verify the font above works correctly
        if save_png_filename != None:
            glBindFramebuffer(GL_READ_FRAMEBUFFER, FBO)
            data = glReadPixels(0, 0, font_texture_width, font_texture_height, GL_RGBA, GL_UNSIGNED_BYTE)
            image = Image.frombytes("RGBA", (font_texture_width, font_texture_height), data)
            image = ImageOps.flip(image) # in my case image is flipped top-bottom for some reason
            image.save(save_png_filename, 'PNG')

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glBindVertexArray(0)

    def get_ortho_matrix(self, left, right, bottom, top, near, far):
        """
        Returns an orthographic projection matrix.
        """
        tx = -(right + left) / (right - left)
        ty = -(top + bottom) / (top - bottom)
        tz = -(far + near) / (far - near)

        return np.array([[2/(right-left), 0,              0,             tx],
                         [0,              2/(top-bottom), 0,             ty],
                         [0,              0,              -2/(far-near), tz],
                         [0,              0,              0,              1]], dtype=np.float32)

    def get_rendering_vertices(self, vertices, xpos, ypos, w, h, top):
        vertices.append((xpos,     ypos + (h-top) - h)) # 0, 0
        vertices.append((xpos,     ypos + (h-top)    )) # 0, 1
        vertices.append((xpos + w, ypos + (h-top),   )) # 1, 1
        vertices.append((xpos,     ypos + (h-top) - h)) # 0, 0
        vertices.append((xpos + w, ypos + (h-top),   )) # 1, 1
        vertices.append((xpos + w, ypos + (h-top) - h)) # 1, 0

    def get_rendering_texes(self, texes, tex_l=0.0, tex_r=1.0, tex_t=1.0, tex_b=0.0):
        texes.append((tex_l, tex_b)) # 0, 0
        texes.append((tex_l, tex_t)) # 0, 1
        texes.append((tex_r, tex_t)) # 1, 1
        texes.append((tex_l, tex_b)) # 0, 0
        texes.append((tex_r, tex_t)) # 1, 1
        texes.append((tex_r, tex_b)) # 1, 0
