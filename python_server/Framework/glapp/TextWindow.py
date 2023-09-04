from OpenGL.GL import *
from .Font import Font
from .Utils import *

class TextWindow:

    def __init__(self, font, pos_x, pos_y, alignment, n_cols, m_rows, display_width, display_height):
        self.font = font
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.m_rows = m_rows
        self.n_cols = n_cols
        self.alignment = alignment

        self.vao_ref = glGenVertexArrays(1) 
        self.text_array = [['X' for n in range(n_cols)] for m in range(m_rows)]
        self.projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)

        self.vertices = self.update_vertices(display_width, display_height)
        first_char = font.first_char
        last_char = font.last_char
        texes = []
        for n in range(0, m_rows):
            for m in range(0, n_cols):
                get_rendering_texes(
                    texes,
                    ((ord('X')-first_char))/(last_char-first_char), # texture left
                    ((ord('X')-first_char+1))/(last_char-first_char)) # texture right
        self.texes = np.array(texes, dtype=np.float32)
        
    def update_vertices(self, display_width, display_height):
        vertices = []
        char_width = self.font.font_width // 64
        char_height = self.font.font_texture_height
        window_width = self.n_cols * char_width
        window_height = self.m_rows * char_height

        if self.alignment == Alignments.TOP_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = display_height  + char_height - window_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = self.pos_y + char_height
        if self.alignment == Alignments.CENTER_RIGHT:
            pos_x = display_width - window_width - self.pos_x
            pos_y = display_height//2 + char_height - window_height//2 - self.pos_y
        elif self.alignment == Alignments.TOP_LEFT:
            pos_x = self.pos_x
            pos_y = display_height + char_height - window_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_LEFT:
            pos_x = self.pos_x
            pos_y = self.pos_y + char_height
        elif self.alignment == Alignments.CENTER_LEFT:
            pos_x = self.pos_x
            pos_y = display_height//2 + char_height - window_height//2 - self.pos_y
        elif self.alignment == Alignments.TOP_CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = display_height + char_height - window_height - self.pos_y
        elif self.alignment == Alignments.BOTTOM_CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = self.pos_y + char_height
        elif self.alignment == Alignments.CENTER:
            pos_x = display_width//2 - window_width//2 - self.pos_x
            pos_y = display_height//2 + char_height - window_height//2 - self.pos_y
        else:
            raise Exception("Alignment not implemented yet")
        
        for n in range(0, self.m_rows):
            for m in range(0, self.n_cols):
                get_rendering_vertices(
                    vertices,   
                    pos_x + m * char_width, 
                    pos_y + n * char_height, 
                    char_width, char_height, char_height)
        return np.array(vertices, dtype=np.float32)
    
    def update_display_size(self, display_width, display_height):
        self.vertices = self.update_vertices(display_width, display_height)
        self.projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)

    def set_texes(self, pos_in_tex, c):
        first_char = self.font.first_char
        last_char = self.font.last_char

        tex_l = ((ord(c)-first_char+0))/(last_char-first_char)
        tex_r = ((ord(c)-first_char+1))/(last_char-first_char)

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

    def print_text(self, x, y, text):
        pos_in_tex = (y * self.n_cols + x) * 6
        if y < self.m_rows and x < self.n_cols:
            for c in text:
                self.text_array[y][x] = c
                self.set_texes(pos_in_tex, c)
                pos_in_tex += 6
                x += 1
                if x >= self.n_cols:
                    x = 0
                    y += 1
                    if y >= self.m_rows:
                        break

    def draw(self, color):

        glBindVertexArray(self.vao_ref)
        self.font.shader_program.use()

        glUniform3f(glGetUniformLocation(
            self.font.shader_program.program_id , "textColor"),
            color[0]/255,color[1]/255,color[2]/255)             
        glActiveTexture(GL_TEXTURE0)

        shader_projection = glGetUniformLocation(self.font.shader_program.program_id, "projection")
        glUniformMatrix4fv(shader_projection, 1, GL_TRUE, self.projection)

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
        VBO = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_DYNAMIC_DRAW) # or GL_STATIC_DRAW?
        location_id = glGetAttribLocation(self.font.shader_program.program_id, "vertex")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        TEX = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, TEX)
        glBufferData(GL_ARRAY_BUFFER, self.texes.nbytes, self.texes, GL_DYNAMIC_DRAW) # or GL_STATIC_DRAW?
        location_id = glGetAttribLocation(self.font.shader_program.program_id, "texCoords")
        glVertexAttribPointer(location_id, 2, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(location_id)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        #render vertices
        glDisable(GL_CULL_FACE);  
        glDrawArrays(GL_TRIANGLES, 0, len(self.vertices))
        glEnable(GL_CULL_FACE);  

        glDepthMask(GL_TRUE)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
