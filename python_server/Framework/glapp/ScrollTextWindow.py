from .TextWindowBase import *
import numpy as np

class ScrollTextWindow(TextWindowBase):

    def __init__(self, font, pos_x, pos_y, alignment, n_cols, m_rows, 
                 text_color, background_color, display_width, display_height):
        super().__init__(font, pos_x, pos_y, alignment, n_cols, m_rows, 
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
            first_line = max(0, nb_history_lines - self.max_display_rows + 1)
            for m in range(0, self.max_display_rows):
                if m+first_line >= nb_history_lines:
                    line = ""
                else:
                    line = self.history[m+first_line]
                for n in range(0, self.n_cols):
                    if n >= len(line):
                        char_index = self.font.char_indexes[' ']
                    else:
                        char_index = self.font.char_indexes[line[n]]
                    tex_l = char_index/self.font.nb_chars
                    tex_r = (char_index+1)/self.font.nb_chars
                    get_rendering_texes(
                        texes, tex_l, tex_r)
            return np.array(texes, dtype=np.float32)

    def update_content(self):
        self.texes = self.load_texes()
        super().update_content()

    def set_max_history(self, max_history):
        self.max_history = max_history
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]

    def load_text(self, text):
        self.history = np.append(self.history, text)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self.content_changed = True