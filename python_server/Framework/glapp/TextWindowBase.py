from OpenGL.GL import *
from .Font import Font
from .Utils import *
from .GraphicsData import *
from .Uniform import *
from .TextWindowBase import *
from .Geometry2D import *
from .Transformations import *

class TextWindowBase(Geometry2D):

    def __init__(self, font, pos_x, pos_y, alignment, n_cols, m_rows, angle,
                 text_color, background_color, display_width, display_height):

        super().__init__([0.0, 0.0, 0.0, 0.0])
        self.font = font
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.position = [pos_x, pos_y]
        self.size = [0, 0] # Calculated later based on alignment
        self.angle = angle
        self.alignment = alignment
        self.m_rows = m_rows
        self.max_display_rows = m_rows
        if self.alignment == Alignments.TOP_TO_BOTTOM_LEFT or \
           self.alignment == Alignments.TOP_TO_BOTTOM_RIGHT or \
           self.alignment == Alignments.TOP_TO_BOTTOM_CENTER:
            self.max_display_rows = max(1, display_height//font.font_texture_height + 1)
        self.n_cols = n_cols
        self.text_color = text_color
        self.background_color = background_color
        self.graphics_data_vertices = GraphicsData("vec3")
        self.graphics_data_text_coords = GraphicsData("vec2")
        self.init_text()
        self.vao_ref = glGenVertexArrays(1) 
        self.texes = self.load_texes()
        self.vertices = self.update_position(display_width, display_height)
        self.content_changed = True

    def init_text(self):
        pass
    
    def load_texes(self):
        texes = []
        space_char_index = self.font.get_char_index(' ')
        tex_l = space_char_index/self.font.get_nb_chars()
        tex_r = (space_char_index+1)/self.font.get_nb_chars()
        for _ in range(0, self.max_display_rows):
            for _ in range(0, self.n_cols):
                get_rendering_texes(
                    texes, tex_l, tex_r)
        return np.array(texes, dtype=np.float32)

    def update_position(self, display_width, display_height):
        vertices = []
        char_width = self.font.font_width // 64
        char_height = self.font.font_texture_height
        window_width = self.n_cols * char_width
        window_height = self.max_display_rows * char_height

        if self.alignment == Alignments.TOP_RIGHT or self.alignment == Alignments.TOP_TO_BOTTOM_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = display_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = self.pos_y + window_height
        elif self.alignment == Alignments.CENTER_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = display_height//2 + char_height - window_height//2 - self.pos_y
        elif self.alignment == Alignments.TOP_LEFT or self.alignment == Alignments.TOP_TO_BOTTOM_LEFT:
            pos_x = self.pos_x
            pos_y = display_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_LEFT:
            pos_x = self.pos_x
            pos_y = self.pos_y + window_height
        elif self.alignment == Alignments.CENTER_LEFT:
            pos_x = self.pos_x
            pos_y = display_height//2 + window_height//2 - self.pos_y
        elif self.alignment == Alignments.TOP_CENTER or self.alignment == Alignments.TOP_TO_BOTTOM_CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = display_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = self.pos_y + window_height
        elif self.alignment == Alignments.CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = display_height//2 + window_height//2 - self.pos_y
        else:
            raise Exception("Alignment not implemented yet")
        self.position = [pos_x, pos_y]
        self.size = [window_width, window_height]
                              
        for n in range(0, self.max_display_rows):
            for m in range(0, self.n_cols):
                get_rendering_vertices(
                    vertices,   
                    -window_width/2 + m*char_width, 
                    -window_height/2 - n*char_height, 
                    char_width, char_height, char_height)

        self.projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)
        super().update_bouding_box([pos_x, pos_y, pos_x + window_width, pos_y + window_height])
        return np.array(vertices, dtype=np.float32)
    
    def update_display_size(self, display_width, display_height):
        if self.alignment == Alignments.TOP_TO_BOTTOM_LEFT or \
           self.alignment == Alignments.TOP_TO_BOTTOM_RIGHT or \
           self.alignment == Alignments.TOP_TO_BOTTOM_CENTER:
            self.max_display_rows = max(1, display_height//self.font.font_texture_height + 1)
            self.texes = self.load_texes()
        self.vertices = self.update_position(display_width, display_height)
        self.content_changed = True

    def set_texes(self, pos_in_tex, c):
        char_index = self.font.get_char_index(' ')
        if self.font.char_exists(c):
            char_index = self.font.get_char_index(c)
        tex_l = char_index/self.font.get_nb_chars()
        tex_r = (char_index+1)/self.font.get_nb_chars()

        self.texes[pos_in_tex][0] = tex_l  # 0, 0
        pos_in_tex += 1
        self.texes[pos_in_tex][0] = tex_l # 0, 1
        pos_in_tex += 1
        self.texes[pos_in_tex][0] = tex_r # 1, 1
        pos_in_tex += 1
        self.texes[pos_in_tex][0] = tex_l # 0, 0
        pos_in_tex += 1
        self.texes[pos_in_tex][0] = tex_r # 1, 1
        pos_in_tex += 1
        self.texes[pos_in_tex][0] = tex_r # 1, 0

    def update_texes(self):
        pass

    def update_content(self):
        self.graphics_data_vertices.load(self.font.shader_program.program_id, "vertex", self.vertices)
        self.graphics_data_text_coords.load(self.font.shader_program.program_id, "texCoords", self.texes)

    def draw(self, display_width, display_height):

        # Do this before drawing anything else because updating texes may 
        # cause additional OpenGL calls for loading new font texture chars
        if self.content_changed:
            self.update_texes()
            glViewport(0, 0, display_width, display_height)

        glBindVertexArray(self.vao_ref)
        self.font.shader_program.use()
           
        Uniform("vec3").load(self.font.shader_program.program_id, "textColor", self.text_color)
        Uniform("vec4").load(self.font.shader_program.program_id, "backgroundColor", self.background_color)
        Uniform("int").load(self.font.shader_program.program_id, "transparent", 0)
        Uniform("sample2D").load(self.font.shader_program.program_id, "texture_id", [self.font.font_texture, 1])
        Uniform("mat4").load(self.font.shader_program.program_id, "projection", self.projection)
        transformation_mat = identity_mat()
        hw = self.size[0]/2
        hh = self.size[1]/2
        transformation_mat = translate(transformation_mat, self.position[0]+hw, self.position[1]+hh, 0.0)
        transformation_mat = rotateA(transformation_mat, self.angle, (0, 0, 1))
        Uniform("mat4").load(self.font.shader_program.program_id, "transformation", transformation_mat)
        glActiveTexture(GL_TEXTURE0)

        fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if fb_status != GL_FRAMEBUFFER_COMPLETE:
            raise Exception("Frame buffer error, status: " + str(fb_status))

        #render glyph texture over quad
        glBindTexture(GL_TEXTURE_2D, self.font.font_texture)
        
        #texture options
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        #update content of VBO memory
        if self.content_changed:
            self.update_content()
            self.content_changed = False

        #render vertices
        glDisable(GL_CULL_FACE); 
        glDrawArrays(GL_TRIANGLES, 0, len(self.vertices))
        glEnable(GL_CULL_FACE);  

        #glDepthMask(GL_TRUE)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
