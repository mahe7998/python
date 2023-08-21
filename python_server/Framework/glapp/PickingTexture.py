from OpenGL.GL import *
from .Camera import *
from .Mesh import *
from .GraphicsData import *
from .Axis import *
from .XZgrid import *

class Selection:

    def __init__(self, object_index, primitive_index, cube_index=-1):
        self.object_index = object_index
        self.primitive_index = primitive_index
        self.cube_index = cube_index

class PickingObject:

    def __init__(self, picking_mat):
        self.picking_mat = picking_mat
        self.fbo = glGenFramebuffers(1)
        self.pick_texture_id = glGenTextures(1)
        self.depth_texture_id = glGenTextures(1)

    def SetObjectIndex(self, program_id, index):
        Uniform("uint").load(program_id, "gObjectIndex", index)

    def draw_object(self, object, object_index):
        vao_ref = glGenVertexArrays(1)
        glBindVertexArray(vao_ref)
        # Send vertices and indices
        GraphicsData("vec3").load(self.picking_mat.program_id, "position", object.vertices)
        GraphicsData("vec2").load(self.picking_mat.program_id, "vertex_index", object.vertex_indices)

        # Set transformation matrix for each object
        transformation_mat = object.get_transformation_matrix()
        Uniform("mat4").load(self.picking_mat.program_id, "model_mat", transformation_mat)

        # Set object index in fragment shader
        self.SetObjectIndex(self.picking_mat.program_id, object_index)

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
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, 
                               self.depth_texture_id, 0)

        fb_status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if fb_status != GL_FRAMEBUFFER_COMPLETE:
            raise Exception("Frame buffer error, status: " + str(fb_status))

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glUseProgram(self.picking_mat.program_id)

        camera.update_projection(self.picking_mat.program_id)
        camera.update_view(self.picking_mat.program_id)

        object_index = 1
        for object in objects:

            self.draw_object(object, object_index)
            object_index += 1

        if current_selection.object_index != -1:

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
            return Selection(-1, -1, -1)
        elif pixel[0][0][0]-1 >= len(objects):
            if current_selection.object_index == -1:
                raise Exception("Internal error: cube access while object not selected!")
            return Selection(
                current_selection.object_index,
                pixel[0][0][1],
                pixel[0][0][0]-1-len(objects))
        else:
            return Selection(
                pixel[0][0][0]-1, pixel[0][0][1], -1)
