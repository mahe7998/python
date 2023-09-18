from OpenGL.GL import *
from PIL import Image
import numpy as np
from .Mesh import *
from .Geometry2D import *

class Picture(Geometry2D):

    def __init__(self, shader_program, filename, position, size, angle, display_width, display_height, keep_aspect_ratio=True):

        super().__init__([position[0], position[1], position[0]+size[0], position[1]+size[1]])
        self.shader_program = shader_program
        self.position = [position[0], position[1]]
        self.size = [size[0], size[1]]
        self.angle = angle
        self.keep_aspect_ratio = keep_aspect_ratio
        self.surface = None
        self.texture_id = glGenTextures(1)
        image = Image.open(filename)
        #image.thumbnail((width, height))
        # By default, display original image size
        if size[0] == -1:
            self.size[0] = image.width
        if size[1] == -1:
            self.size[1] = image.height
        self.image_width = image.width
        self.image_height = image.height
        self.graphics_data_vertices = GraphicsData("vec2")
        self.graphics_data_uvs = GraphicsData("vec2")
        self.load(image)
        image.close()
        self.vao_ref = glGenVertexArrays(1)
        uvs = []
        uvs.append((0.0, 0.0)) # 0, 0
        uvs.append((0.0, 1.0)) # 0, 1
        uvs.append((1.0, 1.0)) # 1, 1
        uvs.append((0.0, 0.0)) # 0, 0
        uvs.append((1.0, 1.0)) # 1, 1
        uvs.append((1.0, 0.0)) # 1, 0
        self.uvs = np.array(uvs, np.float32)
        self.load_vertices(display_width, display_height)

    def load(self, image):
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        pixel_data = np.array(list(image.getdata()), np.uint8)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, image.width, image.height, 0, GL_RGB, GL_UNSIGNED_BYTE, pixel_data)
        glGenerateMipmap(GL_TEXTURE_2D) # Used for fuziness in the distance
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR) # What to do when magnifying pixel values
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR) # What to do in the distance
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT) # GL_CLAMP_TO_EDGE
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glBindTexture(GL_TEXTURE_2D, 0)

    def load_vertices(self, dislpay_width, display_height):
        x = -self.size[0]/2
        y = -self.size[1]/2
        width = self.size[0]
        height = self.size[1]
        if self.keep_aspect_ratio:
            image_ratio = self.image_width/self.image_height
            display_ratio = self.size[0]/self.size[1]
            if display_ratio > image_ratio:
                width = self.size[1] * image_ratio
                x = -width/2
            else:
                height = self.size[0]/image_ratio
                y = -height/2
        vertices = []
        vertices.append((x,       y))        # 0, 0
        vertices.append((x,       y+height)) # 0, 1
        vertices.append((x+width, y+height)) # 1, 1
        vertices.append((x,       y))        # 0, 0
        vertices.append((x+width, y+height)) # 1, 1
        vertices.append((x+width, y))        # 1, 0
        self.vertices = np.array(vertices, np.float32)

        glBindVertexArray(self.vao_ref)
        self.shader_program.use()
        self.graphics_data_vertices.load(self.shader_program.program_id, "vertex", self.vertices)
        self.graphics_data_uvs.load(self.shader_program.program_id, "vertex_uv", self.uvs)

    def update_display_size(self, display_width, display_height):
        self.load_vertices(display_width, display_height)        

    def draw(self, display_width, display_height):
        glBindVertexArray(self.vao_ref)
        self.shader_program.use()
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        Uniform("sample2D").load(self.shader_program.program_id, "texture_id", [self.texture_id, 1])
        self.projection = get_ortho_matrix(0, display_width, 0, display_height, 1 , -1)
        transformation_mat = identity_mat()
        hw = self.size[0]/2
        hh = self.size[1]/2
        transformation_mat = translate(transformation_mat, self.position[0]+hw, display_height-self.position[1]-hh, 0.0)
        transformation_mat = rotateA(transformation_mat, self.angle+180, (0, 0, 1))
        Uniform("mat4").load(self.shader_program.program_id, "transformation", transformation_mat)
        Uniform("mat4").load(self.shader_program.program_id, "projection", self.projection)

        #texture options
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        glDisable(GL_CULL_FACE);  
        glDrawArrays(GL_TRIANGLES, 0, len(self.vertices))
        glEnable(GL_CULL_FACE);  
        
        glBindTexture(GL_TEXTURE_2D, 0)
        glBindVertexArray(0)
