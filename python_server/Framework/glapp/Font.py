from OpenGL.GL import *
import freetype
import numpy as np
from PIL import Image
from PIL import ImageOps
from .Uniform import *
from .Utils import *
from .Transformations import *

class Font:

    # Note: for huge fonts, set nb_preloaded_chars to 0
    # and max_cached_chars to a reasonable value (e.g. 50)
    def __init__(self, shader_program, 
            font_file_name, char_width, char_height,
            nb_preloaded_chars, max_cached_chars, save_png_filename=None):

        self.shader_program = shader_program
        self.font_file_name = font_file_name
        self.char_width = char_width * 64 # Internally, all font sizes are in 64ths of a pixel
        self.char_height = char_height * 64
        self.save_png_filename = save_png_filename

        self.face = freetype.Face(font_file_name)
        self.face.set_char_size(self.char_width, self.char_height)
        self.font_width = self.face.size.max_advance
        self.font_height = self.face.height

        # Font offset in font texture
        max_bitmap_top = 0
        min_bitmap_bottom = 0
        self.all_char_indexes = dict()
        self.cached_char_indexes = dict()
        # Note: we always preload the first char (space)
        char, agi_index = self.face.get_first_char()
        self.all_char_indexes[chr(char)] = 0
        self.cached_char_indexes[chr(char)] = 0
        i = 1
        while agi_index != 0:
            char, agi_index = self.face.get_next_char(char, agi_index)
            self.all_char_indexes[chr(char)] = i
            if i < nb_preloaded_chars:
                self.cached_char_indexes[chr(char)] = i
            i += 1
        self.nb_chars_in_cache = len(self.cached_char_indexes)
        self.max_cached_chars = min(len(self.all_char_indexes), max_cached_chars)

        # Get largest char size
        for c, _ in self.all_char_indexes.items(): # TODO: avoid doing this for fixed fonts!
            self.face.load_char(c)
            glyph = self.face.glyph
            #print("char '" + c + "', bitmap top: " + str(glyph.bitmap_top) + ", bitmap rows: " + str(glyph.bitmap.rows))
            if glyph.bitmap_top > max_bitmap_top:
                max_bitmap_top = glyph.bitmap_top
            if glyph.bitmap_top - glyph.bitmap.rows < min_bitmap_bottom:
                min_bitmap_bottom = glyph.bitmap_top - glyph.bitmap.rows
        self.base_line_ypos = max_bitmap_top
        print("Total chars: " + str(len(self.all_char_indexes)) + ", cached chars: " + str(self.nb_chars_in_cache))
        self.font_texture_width = (self.font_width*self.max_cached_chars)//64
        self.font_texture_height = max_bitmap_top-min_bitmap_bottom

        self.vao_ref = glGenVertexArrays(1)
        self.shader_program.use()
        #disable byte-alignment restriction
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        # Configure VBO to load all glyphs into font_texture
        self.font_fbo = glGenFramebuffers(1)
        self.font_texture = glGenTextures(1)
        
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.font_fbo)
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
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)

        # Create 2 buffers that will be used for all 6 vertices and 6 UVs 
        # of each character of the font
        self.single_char_vbo = glGenBuffers(1)
        self.uvs_texture = glGenBuffers(1)


        # set ortho projection matrix in shader
        projection_mat = get_ortho_matrix(0, self.font_texture_width, self.font_texture_height, 0, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection_mat)
        Uniform("vec4").load(self.shader_program.program_id, "textColor", [1.0, 1.0, 1.0, 1.0])
        #Uniform("vec4").load(self.shader_program.program_id, "backgroundColor", [1.0, 1.0, 1.0, 1.0])
        Uniform("int").load(self.shader_program.program_id, "transparent", 1)
        transformation_mat = identity_mat()
        Uniform("mat4").load(self.shader_program.program_id, "transformation", transformation_mat)
        glActiveTexture(GL_TEXTURE0)

        glBindVertexArray(self.vao_ref)
        
        # Generate source texture coordinate for 1 character (source)
        glBindBuffer(GL_ARRAY_BUFFER, self.uvs_texture)
        texes = []
        get_rendering_texes(texes)
        final_texes = np.array(texes, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_texes.nbytes, final_texes, GL_STATIC_DRAW)
        location_id = glGetAttribLocation(self.shader_program.program_id, "texCoords")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        i = 0
        for c, _ in self.cached_char_indexes.items():
            self.load_char_in_cache(i, c)
            i += 1

        # Code below works and is used to verify the font above works correctly
        if self.save_png_filename != None:
            glBindFramebuffer(GL_READ_FRAMEBUFFER, self.font_fbo)
            glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, self.font_texture, 0)
            data = glReadPixels(0, 0, self.font_texture_width, self.font_texture_height, GL_RGBA, GL_UNSIGNED_BYTE)
            image = Image.frombytes("RGBA", (self.font_texture_width, self.font_texture_height), data)
            image = ImageOps.flip(image) # in my case image is flipped top-bottom for some reason
            image.save(self.save_png_filename, 'PNG')

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glBindVertexArray(0)

    def save_font(self):
        if self.save_png_filename != None:
            glBindFramebuffer(GL_READ_FRAMEBUFFER, self.font_fbo)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.font_texture, 0)
            #glBindTexture(GL_TEXTURE_2D, self.font_texture)
            #glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, self.font_texture, 0)
            #glActiveTexture(GL_TEXTURE0)
            #DrawBuffers = [GL_COLOR_ATTACHMENT0]
            #glDrawBuffers(1, DrawBuffers); # "1" is the size of DrawBuffers
            status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
            if status != GL_FRAMEBUFFER_COMPLETE:
                print("Framebuffer is not complete!")
            data = glReadPixels(0, 0, self.font_texture_width, self.font_texture_height, GL_RGBA, GL_UNSIGNED_BYTE)
            image = Image.frombytes("RGBA", (self.font_texture_width, self.font_texture_height), data)
            image = ImageOps.flip(image) # in my case image is flipped top-bottom for some reason
            image.save(self.save_png_filename, 'PNG')
            glBindTexture(GL_TEXTURE_2D, 0)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

    def load_char_in_cache(self, i, c):
        self.face.load_char(c)
        glyph = self.face.glyph

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
        Uniform("sample2D").load(self.shader_program.program_id, "texture_id", [texture, 1])

        # Create 6 vertices (2 triangles) for each character of the font
        glBindBuffer(GL_ARRAY_BUFFER, self.single_char_vbo)
        vertices = []
        pos_x = (i*self.font_width)//64
        get_rendering_vertices(
            vertices,
            pos_x + glyph.bitmap_left, self.base_line_ypos,
            glyph.bitmap.width, glyph.bitmap.rows, glyph.bitmap_top)
        final_vertices = np.array(vertices, dtype=np.float32)
        glBufferData(GL_ARRAY_BUFFER, final_vertices.nbytes, final_vertices, GL_DYNAMIC_DRAW)
        location_id = glGetAttribLocation(self.shader_program.program_id, "vertex")
        glVertexAttribPointer(location_id, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # Render both triangles for top left and bottom right of each character
        glDisable(GL_CULL_FACE); 
        glDrawArrays(GL_TRIANGLES, 0, len(vertices))
        glEnable(GL_CULL_FACE); 

    def complete_load_char_in_cache(self, i, c):
        self.shader_program.use()
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.font_fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.font_texture, 0)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            print("Framebuffer is not complete!")

        glViewport(0, 0, self.font_texture_width, self.font_texture_height)

        #disable byte-alignment restriction
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        # set ortho projection matrix in shader
        projection_mat = get_ortho_matrix(0, self.font_texture_width, self.font_texture_height, 0, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection_mat)
        Uniform("vec4").load(self.shader_program.program_id, "textColor", [1.0, 1.0, 1.0, 1.0])
        Uniform("int").load(self.shader_program.program_id, "transparent", 1)
        glActiveTexture(GL_TEXTURE0)

        glBindVertexArray(self.vao_ref)

        self.load_char_in_cache(i, c)

        glBindTexture(GL_TEXTURE_2D, 0)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glBindVertexArray(0)

    def get_char_index(self, char):
        if char in self.cached_char_indexes.keys():
            return self.cached_char_indexes[char]
        elif len(self.cached_char_indexes) < self.max_cached_chars:
            i = len(self.cached_char_indexes)
            self.cached_char_indexes[char] = i
            self.complete_load_char_in_cache(i, char)
            return i
        else:
            raise Exception("Need to increase max char cached font size!")
    
    def char_exists(self, char):
        return char in self.all_char_indexes.keys()
    
    def get_nb_chars(self):
        return self.max_cached_chars