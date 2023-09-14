from OpenGL.GL import *
import freetype
import numpy as np
from PIL import Image
from PIL import ImageOps
from .Uniform import *
from .Utils import *

class Font:

    def __init__(self, shader_program, 
            font_file_name, char_width, char_height,
            max_chars, save_png_filename=None):

        self.shader_program = shader_program
        self.vao_ref = glGenVertexArrays(1)
        self.font_file_name = font_file_name
        self.char_width = char_width * 64 # Internally, all font sizes are in 64ths of a pixel
        self.char_height = char_height * 64

        glBindVertexArray(self.vao_ref)
        self.shader_program.use()

        face = freetype.Face(font_file_name)
        face.set_char_size(self.char_width, self.char_height)
        self.font_width = face.size.max_advance
        self.font_height = face.height

        # Font offset in font texture
        max_bitmap_top = 0
        min_bitmap_bottom = 0
        all_chars = []
        self.char_indexes = dict()
        char, agi_index = face.get_first_char()
        all_chars.append(chr(char))
        self.char_indexes[chr(char)] = 0
        i = 1
        while agi_index != 0 and i < max_chars:
            char, agi_index = face.get_next_char(char, agi_index)
            all_chars.append(chr(char))
            self.char_indexes[chr(char)] = i
            i += 1
        self.nb_chars = len(all_chars)
        for c in all_chars:
            face.load_char(c)
            glyph = face.glyph
            #print("char '" + c + "', bitmap top: " + str(glyph.bitmap_top) + ", bitmap rows: " + str(glyph.bitmap.rows))
            if glyph.bitmap_top > max_bitmap_top:
                max_bitmap_top = glyph.bitmap_top
            if glyph.bitmap_top - glyph.bitmap.rows < min_bitmap_bottom:
                min_bitmap_bottom = glyph.bitmap_top - glyph.bitmap.rows
        pos_y = max_bitmap_top
        #print("Total chars: " + str(len(all_chars)))
        self.font_texture_width = (self.font_width*len(all_chars))//64
        self.font_texture_height = max_bitmap_top - min_bitmap_bottom

        # set ortho projection matrix in shader
        projection_mat = get_ortho_matrix(0, self.font_texture_width, self.font_texture_height, 0, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection_mat)
   
        #disable byte-alignment restriction
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        # Configure VBO to load all glyphs into font_texture
        FBO = glGenFramebuffers(1)
        self.font_texture = glGenTextures(1)
        
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, FBO)
        glBindTexture(GL_TEXTURE_2D, self.font_texture)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, self.font_texture_width, self.font_texture_height, 
            0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glBindTexture(GL_TEXTURE_2D, 0)
        glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, self.font_texture, 0)
        
        DrawBuffers = [GL_COLOR_ATTACHMENT0]
        glDrawBuffers(1, DrawBuffers); # "1" is the size of DrawBuffers
        fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if fb_status != GL_FRAMEBUFFER_COMPLETE:
            raise Exception("Frame buffer error, status: " + str(fb_status))

        glViewport(0, 0, self.font_texture_width, self.font_texture_height)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        # Create 2 buffers that will be used for all 6 vertices and 6 UVs 
        # of each character of the font
        VBO = glGenBuffers(1)
        TEX = glGenBuffers(1)
        glBindVertexArray(0)

        Uniform("vec3").load(self.shader_program.program_id, "textColor", [1.0, 1.0, 1.0])
        #Uniform("vec4").load(self.shader_program.program_id, "backgroundColor", [1.0, 1.0, 1.0, 1.0])
        Uniform("int").load(self.shader_program.program_id, "transparent", 1)
        glActiveTexture(GL_TEXTURE0)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glBindVertexArray(self.vao_ref)
        
        # Generate source texture coordinates (same for all characters)
        glBindBuffer(GL_ARRAY_BUFFER, TEX)
        texes = []
        get_rendering_texes(texes)
        final_texes = np.array(texes, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_texes.nbytes, final_texes, GL_STATIC_DRAW)
        location_id = glGetAttribLocation(self.shader_program.program_id, "texCoords")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        i = 0
        for c in all_chars:
            face.load_char(c)
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
            pos_x = (i*self.font_width)//64
            get_rendering_vertices(
                vertices,
                pos_x + glyph.bitmap_left, pos_y,
                glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_top)
            final_vertices = np.array(vertices, dtype=np.float32)
            glBufferData(GL_ARRAY_BUFFER, final_vertices.nbytes, final_vertices, GL_DYNAMIC_DRAW)
            location_id = glGetAttribLocation(self.shader_program.program_id, "vertex")
            glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(location_id)
            glBindBuffer(GL_ARRAY_BUFFER, 0)

            # Render both triangles for top left and bottom right of each character
            glDrawArrays(GL_TRIANGLES, 0, len(vertices))
            i += 1

        # Code below works and is used to verify the font above works correctly
        if save_png_filename != None:
            glBindFramebuffer(GL_READ_FRAMEBUFFER, FBO)
            data = glReadPixels(0, 0, self.font_texture_width, self.font_texture_height, GL_RGBA, GL_UNSIGNED_BYTE)
            image = Image.frombytes("RGBA", (self.font_texture_width, self.font_texture_height), data)
            image = ImageOps.flip(image) # in my case image is flipped top-bottom for some reason
            image.save(save_png_filename, 'PNG')

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glBindVertexArray(0)

