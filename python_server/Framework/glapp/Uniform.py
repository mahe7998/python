from OpenGL.GL import *

class Uniform():

    def __init__(self, data_type):
        self.data_type = data_type
        self.variable_id = None
        self.data = None

    def load(self, program_id, variable_name, data):
        self.data = data
        self.variable_id = glGetUniformLocation(program_id, variable_name)
        if self.data_type == "vec3":
            glUniform3f(self.variable_id, self.data[0], self.data[1], self.data[2])
        elif self.data_type == "vec4":
            glUniform4f(self.variable_id, self.data[0], self.data[1], self.data[2], self.data[3])
        elif self.data_type == "mat4":
            glUniformMatrix4fv(self.variable_id, 1, GL_TRUE, self.data)
        elif self.data_type == "uint":
            glUniform1ui(self.variable_id, self.data)
        elif self.data_type == "int":
            glUniform1i(self.variable_id, self.data)
        elif self.data_type == "sample2D":
            texture_obj, texture_unit = self.data
            glActiveTexture(GL_TEXTURE0 + texture_unit)
            glBindTexture(GL_TEXTURE_2D, texture_obj)
            glUniform1i(self.variable_id, texture_unit)
        else:
            raise Exception("Unknown Uniform type" + self.data_type)
