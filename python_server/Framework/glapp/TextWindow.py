from .TextWindowBase import *

class TextWindow(TextWindowBase):

    def __init__(self, font, pos_x, pos_y, alignment, n_cols, m_rows, 
                 text_color, background_color, display_width, display_height):
        super().__init__(font, pos_x, pos_y, alignment, n_cols, m_rows, 
            text_color, background_color, display_width, display_height)

    def init_text(self):
        self.text_array = [[' ' for n in range(self.n_cols)] for m in range(self.m_rows)]
    
    def load_texes(self):
        texes = []
        space_char_index = self.font.get_char_index(' ')
        for m in range(0, self.max_display_rows):
            for n in range(0, self.n_cols):
                if m >= self.m_rows:
                    char_index = space_char_index
                else:
                    char_index = self.font.get_char_index(self.text_array[m][n])
                tex_l = char_index/self.font.get_nb_chars()
                tex_r = (char_index+1)/self.font.get_nb_chars()
                get_rendering_texes(
                    texes, tex_l, tex_r)
        return np.array(texes, dtype=np.float32)

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
        self.content_changed = True
