from OpenGL.GL import *
import numpy as np

class GraphicsData():

    def __init__(self, data_type):
        self.variable_id = -1 # Skip if variable_id == -1 (i.e. variable not found)
        self.data_type = data_type
        self.buffer_ref = glGenBuffers(1)

    def __del__(self):
        if "glDeleteBuffers" in dir(OpenGL.GL):
            glDeleteBuffers(1, [self.buffer_ref])

    def load(self, program_id, variable_name, data):
        load_data = np.array(data, np.float32)
        glBindBuffer(GL_ARRAY_BUFFER, self.buffer_ref)
        glBufferData(GL_ARRAY_BUFFER, load_data.ravel(), GL_STATIC_DRAW)
        self.variable_id = glGetAttribLocation(program_id, variable_name)
        if self.variable_id > -1:
            glBindBuffer(GL_ARRAY_BUFFER, self.buffer_ref)
            if self.data_type == "vec3":
                glVertexAttribPointer(self.variable_id, 3, GL_FLOAT, False, 0, None)
            elif self.data_type == "vec2":
                glVertexAttribPointer(self.variable_id, 2, GL_FLOAT, False, 0, None)
            elif self.data_type == "uvec2":
                glVertexAttribPointer(self.variable_id, 2, GL_UNSIGNED_INT, False, 0, None)
            else:
                raise Exception("Unknown data type " + self.data_type)
            glEnableVertexAttribArray(self.variable_id)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
