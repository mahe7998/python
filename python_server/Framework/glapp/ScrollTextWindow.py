from .TextWindowBase import *
import numpy as np

class ScrollTextWindow(TextWindowBase):

    def __init__(self, font, position, n_cols, m_rows, angle, z, alignment,
                 text_color, background_color, display_width, display_height):
        super().__init__(font, position, n_cols, m_rows, angle, z, alignment,
                         text_color, background_color, display_width, display_height)
        self.max_history = 1000

    def init_text(self):
        self.history = np.empty((0), dtype=np.string_)
    
    def load_texes(self):
        texes = []
        if self.history is None:
            super().load_texes()
        else:
            nb_history_lines = len(self.history)
            first_line = max(0, nb_history_lines-self.max_display_rows + 1)
            space_char_index = self.font.get_char_index(' ')
            for m in range(0, self.max_display_rows):
                if m+first_line >= nb_history_lines:
                    line = ""
                else:
                    line = self.history[m+first_line]
                for n in range(0, self.n_cols):
                    if n >= len(line):
                        char_index = space_char_index
                    else:
                        char_index = self.font.get_char_index(line[n])
                    tex_l = char_index/self.font.get_nb_chars()
                    tex_r = (char_index+1)/self.font.get_nb_chars()
                    get_rendering_texes(
                        texes, tex_l, tex_r)
            return np.array(texes, dtype=np.float32)

    def update_texes(self):
        self.texes = self.load_texes()

    def set_max_history(self, max_history):
        self.max_history = max_history
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]

    def load_text(self, text):
        self.history = np.append(self.history, text)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self.content_changed = True