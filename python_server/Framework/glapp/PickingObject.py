from OpenGL.GL import *
from .Camera import *
from .Mesh import *
from .GraphicsData import *
from .Axis import *
from .XZgrid import *

class Selection:

    def __init__(self, name, primitive_index, geometry_index=-1):
        if name == -1:
            raise Exception("Internal error: object name cannot be -1 (Use None instead)!")
        self.name = name
        self.primitive_index = primitive_index
        self.geometry_index = geometry_index

class PickingObject:

    def __init__(self, picking_shader):
        self.picking_shader = picking_shader
        self.fbo = glGenFramebuffers(1)
        self.pick_texture_id = glGenTextures(1)
        self.depth_texture_id = glGenTextures(1)
        self.graphics_data_position = GraphicsData("vec3")
        self.graphics_data_vertex_indices = GraphicsData("vec2")

    def SetObjectIndex(self, program_id, index):
        Uniform("uint").load(program_id, "gObjectIndex", index)

    def draw_object(self, object, object_index):
        vao_ref = glGenVertexArrays(1)
        glBindVertexArray(vao_ref)
        # Send vertices and indices
        self.graphics_data_position.load(self.picking_shader.program_id, "position", object.vertices)
        self.graphics_data_vertex_indices.load(self.picking_shader.program_id, "vertex_index", object.vertex_indices)

        # Set transformation matrix for each object
        transformation_mat = object.get_transformation_matrix()
        Uniform("mat4").load(self.picking_shader.program_id, "model_mat", transformation_mat)

        # Set object index in fragment shader
        self.SetObjectIndex(self.picking_shader.program_id, object_index)

        # Draw vertices (always use triangles)
        glDrawArrays(GL_TRIANGLES, 0, object.length)

    def MousePick(self, screen_width, screen_height,
            mouse_x, mouse_y, objects, selection_cubes,
            camera, current_selection):

        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.fbo)
        glBindTexture(GL_TEXTURE_2D, self.pick_texture_id)

        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB32UI, screen_width, screen_height, 
                     0, GL_RGB_INTEGER, GL_UNSIGNED_INT, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glFramebufferTexture(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, self.pick_texture_id, 0)

        # Create texture object for the depth buffer
        glBindTexture(GL_TEXTURE_2D, self.depth_texture_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, screen_width, screen_height, 
                     0, GL_DEPTH_COMPONENT, GL_FLOAT, None)
        glFramebufferTexture2D(
            GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, 
            self.depth_texture_id, 0)

        fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if fb_status != GL_FRAMEBUFFER_COMPLETE:
            raise Exception("Frame buffer error, status: " + str(fb_status))

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self.picking_shader.program_id)

        camera.update_projection(self.picking_shader.program_id)
        camera.update_view(self.picking_shader.program_id)

        object_index = 1
        names = []
        for name, object in objects.items():
            if object.get_selectable():
                self.draw_object(object, object_index)
                names.append(name)
                object_index += 1

        if current_selection.name != None:

            for cube in selection_cubes:
                self.draw_object(cube, object_index)
                object_index += 1

        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)

        glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        glReadBuffer(GL_COLOR_ATTACHMENT0)
        pixel = glReadPixels(mouse_x, screen_height - mouse_y, 1, 1, GL_RGB_INTEGER, GL_UNSIGNED_INT)
        glReadBuffer(GL_NONE)
        glBindFramebuffer(GL_READ_FRAMEBUFFER, 0)

        if pixel[0][0][0] == 0:
            return Selection(None, -1, -1)
        else:
            index = pixel[0][0][0]
            if index-1 >= len(names): # i.e. when a cube is selected
                if current_selection.name == None:
                    raise Exception("Internal error: cube access while no object selected!")
                return Selection(
                    current_selection.name,
                    pixel[0][0][1],
                    pixel[0][0][0]-1-len(names))
            else:
                return Selection(
                    names[index-1], pixel[0][0][1], -1)
