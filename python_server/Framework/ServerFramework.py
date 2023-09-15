import glfw
from .glapp.PyOGLApp import *
from .glapp.LoadMesh import *
from .glapp.Light import *
from .glapp.Camera import *
from .glapp.Axis import *
from .glapp.XZgrid import *
from .glapp.Shader import *
from .glapp.PickingObject import *
from .glapp.Utils import *
from .glapp.Font import *
from .glapp.TextWindow import *
from .glapp.ScrollTextWindow import *
from .glapp.Picture import *

boundaries_offset = 0.2 # % of object size (0.1 = 10%) for selection cubes

class ServerFramework(PyOGLApp):

    def __init__(self):
        super().__init__()
        self.lights = []
        self.picking_object = None  
        self.axis = None
        self.grid = None
        self.objects = []
        self.edit_mode = EditMode.NOT_SELECTED
        self.selected_object = Selection(-1, -1)
        self.selection_cubes = []
        self.selection_axis = None
        self.fonts = dict()
        self.text_windows = dict()
        self.pictures = dict()

    def initialize_3D_space(self):
        self.shaders = {
            'textured': Shader("shaders/textured_vertices.vs", "shaders/textured_frags.vs"),
            'colored' : Shader("shaders/color_vertices.vs", "shaders/color_frags.vs"),
            'font'    : Shader("shaders/font_vertices.vs", "shaders/font_frags.vs"),
            'picture' : Shader("shaders/picture_vertices.vs", "shaders/picture_frags.vs") }
        self.lights.append(Light(0, (0, 5, 0), (1, 1, 1)))
        self.picking_object = PickingObject(Shader("shaders/picking_vertices.vs", "shaders/picking_frags.vs"))
        self.axis = Axis((0, 0, 0), [-100.0, -100.0, -100.0, 100.0, 100.0, 100.0])
        self.axis.load(self.shaders['colored'])
        self.grid = XZGrid((0, 0, 0), 100.0)
        self.grid.load(self.shaders['colored'])
        self.create_selection_cubes()

    def create_selection_cubes(self):
        colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1],
                  [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        for cube_index in range(len(colors)):
            cube = LoadMesh(
                "models/cube.obj", None,
                location=(0.0, 0.0, 0.0),
                color=colors[cube_index],
                gl_draw_type=GL_TRIANGLES,
                scale=(0.05, 0.05, 0.05),
                rotation=(0, 0, 0),
                move_rotation=(0, 0, 0))
            cube.load(self.shaders['colored'])
            self.selection_cubes.append(cube)
        
    def add_object(self, object, material):
        # First load, then append
        object.load(self.shaders[material])
        self.objects.append(object)

    def load_font(self, font_name, font_file_name, char_width, char_height,
            nb_preloaded_chars, max_cached_chars, save_png_filename=None):
        font = Font(self.shaders['font'], 
            font_file_name, char_width, char_height, nb_preloaded_chars, max_cached_chars, save_png_filename)
        self.fonts[font_name] = font

    def add_text_window(self, window_name, font_name, pos_x, pos_y, alignment, m_cols, n_rows, text_color, background_color, type=None):
        display_width = self.display_width
        display_height = self.display_height
        if self.fullscreen:
            display_width = self.max_resolution[0]
            display_height = self.max_resolution[1]
        if type == "scroll":
            self.text_windows[window_name] = ScrollTextWindow(self.fonts[font_name], pos_x, pos_y, alignment, 
                m_cols, n_rows, text_color, background_color, display_width, display_height)
        else:
            self.text_windows[window_name] = TextWindow(self.fonts[font_name], pos_x, pos_y, alignment, 
                m_cols, n_rows, text_color, background_color, display_width, display_height)
            
    def add_picture(self, picture_name, picture_file_name, pos_x, pos_y, width=-1, height=-1):
        if self.fullscreen:
            self.pictures[picture_name] = Picture(self.shaders['picture'], picture_file_name, pos_x, pos_y, 
                width, height, self.max_resolution[0], self.max_resolution[1])
        else:
            self.pictures[picture_name] = Picture(self.shaders['picture'], picture_file_name, pos_x, pos_y, 
                width, height, self.display_width, self.display_height)

    def get_text_window(self, window_name):
        return self.text_windows[window_name]
    
    def update_display_size(self, display_width, display_height):
        self.camera.update_perspective(display_width, display_height)
        for _, text_window in self.text_windows.items():
            text_window.update_display_size(display_width, display_height)
        for _, picture in self.pictures.items():
            picture.update_display_size(display_width, display_height)

    def mouse_pos_callback(self, window, xpos, ypos):
        if self.track_mouse:
            if self.selected_object.object_index == -1:
                super().mouse_pos_callback(window, xpos, ypos)
            else:
                self.objects[self.selected_object.object_index].update_mouse_pos(
                    self.selected_object, self.edit_mode, 
                    xpos-self.last_mouse_pos[0], ypos-self.last_mouse_pos[1])
                if self.selection_axis != None:
                    self.selection_axis.location = self.objects[self.selected_object.object_index].location
                    self.selection_axis.scale = self.objects[self.selected_object.object_index].scale
        self.last_mouse_pos = (xpos, ypos)

    def key_callback(self, window, key, scancode, action, mods):
        super().key_callback(window, key, scancode, action, mods)
            
    def pick_object(self, location):
        if self.fullscreen:
            selection = self.picking_object.MousePick(
                self.max_resolution[0], self.max_resolution[1],
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
                self.selection_axis.load(self.shaders['colored'])
                self.selected_object = selection
            elif selection.object_index != -1 and self.edit_mode == EditMode.POSITION:
                object = self.objects[selection.object_index]
                self.selection_axis = Axis(
                    location=object.location,
                    boundaries=offset_object_boundaries(object.boundaries, boundaries_offset),
                    scale=object.scale,
                    rotation=object.rotation)
                self.selection_axis.load(self.shaders['colored'])
                self.edit_mode = EditMode.SCALE
            else:
                self.edit_mode = EditMode.NOT_SELECTED
                self.selected_object = Selection(-1, -1, -1)
                self.selection_axis = None
        else:
            self.selected_object = selection

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
            rot = rotateA(rot, -cube.rotation[0], (1, 0, 0), False)
            rot = rotateA(rot, -cube.rotation[1], (0, 1, 0), False)
            rot = rotateA(rot, -cube.rotation[2], (0, 0, 1), False)
            delta_location = delta_location.dot(rot)
        cube.location = (cube.location[0]+delta_location[0],
                         cube.location[1]+delta_location[1],
                         cube.location[2]+delta_location[2])
        cube.draw(self.camera, self.lights)

    def draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        display_width, display_height = glfw.get_framebuffer_size(self.window)
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
        for _, picture in self.pictures.items():
            picture.draw()
        for _, text_window in self.text_windows.items():
            text_window.draw(display_width, display_height)


