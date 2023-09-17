from OpenGL.GL import *
from .Geometry2D import *
from .Uniform import *
from .Utils import *
from .Transformations import *
import numpy as np

class Frame(Geometry2D):

    def __init__(self, shader_program, position, size, line_width, color, angle, display_width, display_height):
        super().__init__([0.0, 0.0, 0.0, 0.0]) # we update position later...
        # Create a vertex buffer object for the rectangle
        self.shader_program = shader_program
        self.line_width = line_width
        self.color = color
        self.angle = angle
        self.update_position(position, size, angle, display_width, display_height)
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        
        # Create a vertex array object for the rectangle
        self.vao = glGenVertexArrays(1)

    def update_position(self, position, size, angle, display_width, display_height):
        self.position = position
        self.size = size
        self.angle = angle
        ofx = self.line_width[0]/2
        ofy = self.line_width[1]/2
        hw = size[0]/2
        hh = size[1]/2
        self.vertices = np.array([
            [-hw-ofx, hh+ofy, -1.0],
            [-hw+ofx, hh-ofy, -1.0],
            [hw+ofx, hh+ofy, -1.0],
            [hw-ofx, hh-ofy, -1.0],
            [hw+ofx, -hh-ofy, -1.0],
            [hw-ofx, -hh+ofy, -1.0],
            [-hw-ofx, -hh-ofy, -1.0],
            [-hw+ofx, -hh+ofy, -1.0],
            [-hw-ofx, hh+ofy, -1.0],
            [-hw+ofx, hh-ofy, -1.0]
        ], dtype=np.float32)
        super().update_bouding_box(
            [position[0]-ofx, display_height-position[1]+ofy, 
             position[0]+size[0]+ofx, display_height-position[1]-size[1]-ofy])

    def draw(self, display_width, display_height):
        self.shader_program.use()
        glBindVertexArray(self.vao)
        glEnableVertexAttribArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)
        # Set the vertex attribute pointers
        location_id = glGetAttribLocation(self.shader_program.program_id, "vertex")
        glVertexAttribPointer(location_id, 3, GL_FLOAT, GL_FALSE, 0, None)
        # set ortho projection matrix in shader
        projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)
        Uniform("mat4").load(self.shader_program.program_id, "projection", projection)
        transformation_mat = identity_mat()
        hw = self.size[0]/2
        hh = self.size[1]/2
        transformation_mat = translate(transformation_mat, self.position[0]+hw, display_height-self.position[1]-hh, 0.0)
        transformation_mat = rotateA(transformation_mat, self.angle, (0, 0, 1))
        Uniform("mat4").load(self.shader_program.program_id, "transformation", transformation_mat)
        Uniform("vec3").load(self.shader_program.program_id, "color", 
            [self.color[0], self.color[1], self.color[2]])
        
        # Draw the rectangle
        glViewport(0, 0, display_width,display_height)
        glDisable(GL_CULL_FACE); 
        glDrawArrays(GL_TRIANGLE_STRIP, 0, len(self.vertices))
        glEnable(GL_CULL_FACE); 
        
        # Cleanup
        glDisableVertexAttribArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
