from OpenGL.GL import *
from .Geometry2D import *
from .Uniform import *
from .Utils import *
from .Transformations import *
import numpy as np

class Line(Geometry2D):

    def __init__(self, shader_program, start_point, end_point, line_width, color, display_width, display_height):
        super().__init__([0.0, 0.0, 0.0, 0.0]) # we update position later...
        # Create a vertex buffer object for the line
        self.shader_program = shader_program
        self.line_width = line_width
        self.start_point = start_point
        self.end_point = end_point
        self.update_position(start_point, end_point, display_width, display_height)
        self.color = color
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        
        # Create a vertex array object for the line
        self.vao = glGenVertexArrays(1)

    def update_position(self, start_point, end_point, display_width, display_height):
        spx = start_point[0]
        spy = display_height - start_point[1]
        epx = end_point[0]
        epy = display_height - end_point[1]
        ofx = self.line_width[0]/2
        ofy = self.line_width[1]/2
        self.vertices = np.array([
            [spx-ofx, spy-ofy, -1.0],
            [spx+ofx, spy+ofy, -1.0],
            [epx-ofx, epy-ofy, -1.0],
            [epx+ofx, epy+ofy, -1.0]
        ], dtype=np.float32)
        super().update_bouding_box(
            [start_point[0]-ofx, start_point[1]-ofy, end_point[0]+ofx, end_point[1]+ofy])

    def draw(self, display_width, display_height):
        self.shader_program.use()
        glBindVertexArray(self.vao)
        glEnableVertexAttribArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)
        location_id = glGetAttribLocation(self.shader_program.program_id, "vertex")
        glVertexAttribPointer(location_id, 3, GL_FLOAT, GL_FALSE, 0, None)

        # set ortho projection matrix in shader
        projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection)
        transformation_mat = identity_mat()
        Uniform("mat4").load(self.shader_program.program_id, "transformation", transformation_mat)
        Uniform("vec3").load(self.shader_program.program_id, "color", 
            [self.color[0], self.color[1], self.color[2]])
        
        #glColor3f(self.color[0], self.color[1], self.color[2])
        glViewport(0, 0, display_width,display_height)
        glDisable(GL_CULL_FACE); 
        glDrawArrays(GL_TRIANGLE_STRIP, 0, len(self.vertices))
        glEnable(GL_CULL_FACE); 
        
        glDisableVertexAttribArray(0)
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        
