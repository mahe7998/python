import pygame
from .glapp.PyOGLApp import *
from .glapp.LoadMesh import *
from .glapp.Light import *
from .glapp.Camera import *
from .glapp.Axis import *
from .glapp.XZgrid import *
from .glapp.Shader import *
from .glapp.PickingTexture import *
from .glapp.Utils import *
from .glapp.Font import *

boundaries_offset = 0.2 # % of object size (0.1 = 10%) for selection cubes

class ServerFramework(PyOGLApp):

    def __init__(self, screen_posX, screen_posY, screen_width, screen_height, fullscreen=False, display_num=0):
        super().__init__(screen_posX, screen_posY, screen_width, screen_height,fullscreen, display_num)
        self.camera = None
        self.lights = []
        self.picking_object = None
        self.axis = None
        self.grid = None
        self.objects = []
        self.fonts = dict()
        self.edit_mode = EditMode.NOT_SELECTED
        self.selected_object = Selection(-1, -1)
        self.selection_cubes = []
        self.selection_axis = []
        glEnable(GL_CULL_FACE) # Get rid of back side
        glEnable(GL_BLEND) # Also need to set glBlendFunc below and draw object below first!
        glEnable(GL_DEPTH_TEST)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def create_selection_cubes(self):
        colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1],
                  [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        for cube_index in range(len(colors)):
            cube = LoadMesh(
                "models/cube.obj", None,
                location=pygame.Vector3(0.0, 0.0, 0.0),
                color=colors[cube_index],
                gl_draw_type=GL_TRIANGLES,
                scale=pygame.Vector3(0.05, 0.05, 0.05),
                rotation=pygame.Vector3(0, 0, 0),
                move_rotation=pygame.Vector3(0, 0, 0))
            cube.load(self.materials['colored'])
            self.selection_cubes.append(cube)
                
    def initialize(self, fullscreen):
        self.materials = {
            'textured': Shader("shaders/textured_vertices.vs", "shaders/textured_frags.vs"),
            'colored' : Shader("shaders/color_vertices.vs", "shaders/color_frags.vs") }
        if fullscreen:
            self.camera = Camera(self.desktop_size[0], self.desktop_size[1])
        else:
            self.camera = Camera(self.display_width, self.display_height)
        self.camera.relative_move(5.0, 0.0, 2.0) # Initial camera position to see Axis
        self.lights.append(Light(0, pygame.Vector3(0, 5, 0), pygame.Vector3(1, 1, 1)))
        self.picking_object = PickingObject(Shader("shaders/picking_vertices.vs", "shaders/picking_frags.vs"))
        self.axis = Axis(pygame.Vector3(0, 0, 0), [-100.0, -100.0, -100.0, 100.0, 100.0, 100.0])
        self.axis.load(self.materials['colored'])
        self.grid = XZGrid(pygame.Vector3(0, 0, 0), 100.0)
        self.grid.load(self.materials['colored'])
        self.create_selection_cubes()
        
    def add_object(self, object, material):
        # First load, then append
        object.load(self.materials[material])
        self.objects.append(object)

    def load_font(self, font_name, font_file_name, first_char, last_char, char_width, char_height,
            squeeze_width, squeeze_height, save_png_filename=None):
        font = Font(Shader("shaders/font_vertices.vs", "shaders/font_frags.vs"), 
            font_file_name, first_char, last_char, char_width, char_height,
            squeeze_width, squeeze_height, save_png_filename)
        self.fonts[font_name] = font
        
    def update_display(self, fullscreen, event=None):
        super().update_display(fullscreen, event)
        if event != None and event.type == pygame.VIDEORESIZE and not fullscreen:
            if event.w != self.desktop_size[0] and event.h != self.desktop_size[1]:
                print("camera.update_perspective (resize event): " + str(event.w) + ", " + str(event.h))
                self.camera.update_perspective(event.w, event.h)
            else:
                print("camera.update_perspective (resize event after full screen): " + str(self.display_width) + ", " + str(self.display_height))
                self.camera.update_perspective(self.display_width, self.display_height)
        elif event == None:
            if fullscreen:
                print("camera.update_perspective (full screen): " + str(self.desktop_size[0]) + ", " + str(self.desktop_size[1]))
                self.camera.update_perspective(self.desktop_size[0], self.desktop_size[1])
            else:
                print("camera.update_perspective (resume window display): " + str(self.display_width) + ", " + str(self.display_height))
                self.camera.update_perspective(self.display_width, self.display_height)
        elif event != None and fullscreen:
            print("camera.update_perspective (full screen buttom): " + str(event.w) + ", " + str(event.h))
            self.camera.update_perspective( self.desktop_size[0],  self.desktop_size[1])

    def update(self):
        self.camera.update_mouse_and_keyboard(
            self.track_mouse, self.selected_object)
        if self.selected_object.object_index != -1:
            self.objects[self.selected_object.object_index].update_mouse_and_keyboard(
                self.track_mouse, self.selected_object, self.edit_mode)
            
    def pick_object(self, fullscreen, location):
        if fullscreen:
            selection = self.picking_object.MousePick(
                self.desktop_size[0], self.desktop_size[1],
                location[0], location[1],
                self.objects, self.selection_cubes,
                self.camera, self.selected_object)
        else:
            selection = self.picking_object.MousePick(
                self.display_width, self.display_height,
                location[0], location[1],
                self.objects, self.selection_cubes,
                self.camera, self.selected_object)
        #print("selection: object is " + str(selection.object_index) +
        #      ", fragment is " + str(selection.primitive_index) +
        #      ", cube is " + str(selection.cube_index))
        if selection.cube_index == -1: # i.e. when none of the "editing" objects are selected
            if self.selected_object.object_index != -1:
                self.objects[self.selected_object.object_index].selected = False
            if selection.object_index != -1 and selection.object_index != self.selected_object.object_index:
                object = self.objects[selection.object_index]
                object.selected = True
                self.edit_mode = EditMode.POSITION
                self.selection_axis = Axis(
                    location=object.location,
                    boundaries=offset_object_boundaries(object.boundaries, boundaries_offset),
                    scale=object.scale)
                self.selection_axis.load(self.materials['colored'])
                self.selected_object = selection
            elif selection.object_index != -1 and self.edit_mode == EditMode.POSITION:
                object = self.objects[selection.object_index]
                self.selection_axis = Axis(
                    location=object.location,
                    boundaries=offset_object_boundaries(object.boundaries, boundaries_offset),
                    scale=object.scale,
                    rotation=object.rotation)
                self.selection_axis.load(self.materials['colored'])
                self.edit_mode = EditMode.SCALE
            else:
                self.edit_mode = EditMode.NOT_SELECTED
                self.selected_object = Selection(-1, -1, -1)
        else:
            self.selected_object = selection

    def update_event(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self.camera.zoom(event.y, event.flipped)
        return super().update_event(event)

    def display_selection_cubes(self, cube, object, axis, negative):
        cube.location = copy.deepcopy(object.location)
        boundaries = offset_object_boundaries(object.boundaries, boundaries_offset)
        scale = object.scale
        cube.rotation = object.rotation
        delta_location = np.array([0.0, 0.0, 0.0, 1.0])
        if axis == "x" and negative:
            delta_location[0] = boundaries[0] * scale[0]
        elif axis == "x":
            delta_location[0] = boundaries[3] * scale[0]
        elif axis == "y" and negative:
            delta_location[1] = boundaries[1] * scale[1]
        elif axis == "y":
            delta_location[1] = boundaries[4] * scale[1]
        elif axis == "z" and negative:
            delta_location[2] = boundaries[2] * scale[2]
        elif axis == "z":
            delta_location[2] = boundaries[5] * scale[2]
        else:
            raise Exception("Invalid axis " + axis)
        if self.edit_mode == EditMode.SCALE:
            rot = identity_mat()
            rot = rotateA(rot, -cube.rotation[0], pygame.Vector3(1, 0, 0), False)
            rot = rotateA(rot, -cube.rotation[1], pygame.Vector3(0, 1, 0), False)
            rot = rotateA(rot, -cube.rotation[2], pygame.Vector3(0, 0, 1), False)
            delta_location = delta_location.dot(rot)
        cube.location += pygame.Vector3(delta_location[0], delta_location[1], delta_location[2])
        cube.draw(self.camera, self.lights)

    def display(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.axis.draw(self.camera, self.lights)
        self.grid.draw(self.camera, self.lights)
        for object in self.objects:
            object.draw(self.camera, self.lights)
        if self.selected_object.object_index != -1:
            object = self.objects[self.selected_object.object_index] # Shallow copy
            self.display_selection_cubes(self.selection_cubes[0], object, "x", True)
            self.display_selection_cubes(self.selection_cubes[1], object, "y", True)
            self.display_selection_cubes(self.selection_cubes[2], object, "z", True)
            self.display_selection_cubes(self.selection_cubes[3], object, "x", False)
            self.display_selection_cubes(self.selection_cubes[4], object, "y", False)
            self.display_selection_cubes(self.selection_cubes[5], object, "z", False)
            if self.selection_axis != None:
                self.selection_axis.draw(self.camera, self.lights)
