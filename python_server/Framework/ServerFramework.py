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
from .glapp.Line import *
from .glapp.Frame import *
from .glapp.Torus import *

boundaries_offset = 0.2 # % of object size (0.1 = 10%) for selection cubes

class ServerFramework(PyOGLApp):

    def __init__(self):
        super().__init__()
        self.picking_object = None  
        self.edit_mode = EditMode.NOT_SELECTED
        self.selected_geometry = Selection(None, -1)
        self.selection_geometry = []
        self.selection_axis = None
        self.fonts = dict()
        self.geometry3D = dict()
        self.geometry2D = dict()
        self.mouse_scale_sensitivity = 0.01
        self.mouse_move_sensitivity = 0.01
        self.mouse_rotation_sensitivity = 0.1

    def initialize_3D_space(self):
        self.shaders = {
            'textured': Shader("shaders/textured_vertices.vs", "shaders/textured_frags.vs"),
            'colored' : Shader("shaders/color_vertices.vs", "shaders/color_frags.vs"),
            'font'    : Shader("shaders/font_vertices.vs", "shaders/font_frags.vs"),
            'picture' : Shader("shaders/picture_vertices.vs", "shaders/picture_frags.vs"),
            'selection' : Shader("shaders/picking_vertices.vs", "shaders/picking_frags.vs"),
            'geometry 2D' : Shader("shaders/geometry2D_vertices.vs", "shaders/geometry2D_frags.vs") }
        self.picking_object = PickingObject(self.get_shader('selection'))
        self.create_format_selection_geometry()

    def create_format_selection_geometry(self):
        cubes_colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1],
                       [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        for cube_index in range(len(cubes_colors)):
            self.selection_geometry.append(
                LoadMesh(self.get_shader('colored'),
                        "models/cube.obj", None,
                        location=(0.0, 0.0, 0.0),
                        color=cubes_colors[cube_index],
                        gl_draw_type=GL_TRIANGLES,
                        scale=(0.05, 0.05, 0.05),
                        rotation=(0, 0, 0),
                        move_rotation=(0, 0, 0)))
        tori_colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        tori_rotation = np.array([[0.0, 90.0, 0.0], [90.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        for torus_index in range(len(tori_colors)):
            self.selection_geometry.append(
                Torus(self.get_shader('colored'), None, 
                    1.0, 0.02, color=tori_colors[torus_index],
                    initial_rotation=tori_rotation[torus_index],
                    move_rotation=(0.0, 0.0, 0.0)))
        
    def add_geometry3D(self, name, geometry, selectable=True):
        # First load, then append
        self.geometry3D[name] = geometry
        geometry.set_selectable(selectable)

    def get_geometry3D(self, name):
        return self.geometry3D[name]

    def load_font(self, font_name, font_file_name, char_width, char_height,
            nb_preloaded_chars, max_cached_chars, save_png_filename=None):
        font = Font(self.get_shader('font'), font_file_name, char_width, char_height, 
                    nb_preloaded_chars, max_cached_chars, save_png_filename)
        self.fonts[font_name] = font

    def get_font(self, font_name):
        return self.fonts[font_name]
    
    def get_shader(self, sharder_name):
        return self.shaders[sharder_name]
                
    def add_geometry2D(self, geometry_name, geometry, selectable=True):
        self.geometry2D[geometry_name] = geometry
        geometry.set_selectable(selectable)

    def get_geometry2D(self, geometry_name):
        return self.geometry2D[geometry_name]

    def update_display_size(self, display_width, display_height):
        self.camera.update_perspective(display_width, display_height)
        for _, geometry in self.geometry2D.items():
            geometry.update_display_size(display_width, display_height)

    def update_mouse_pos(self, selected_object, edit_mode, delta_x, delta_y):
        if self.selected_geometry.geometry_index != -1:
            geometry_index = self.selected_geometry.geometry_index
            value_to_modify = None
            if edit_mode == EditMode.POSITION:
                value_to_modify = selected_object.location
                mouse_sensitivity = self.mouse_move_sensitivity
            elif edit_mode == EditMode.SCALE:
                value_to_modify = selected_object.scale
                mouse_sensitivity = self.mouse_scale_sensitivity
            elif edit_mode == EditMode.ROTATION:
                value_to_modify = selected_object.rotation
                mouse_sensitivity = self.mouse_rotation_sensitivity
            else:
                raise Exception("Not a valid editing mode!")
            delta_pos = (delta_x - delta_y) * mouse_sensitivity
            if geometry_index == 0 or geometry_index == 3 or geometry_index == 6:
                value_to_modify = (value_to_modify[0] + delta_pos, value_to_modify[1], value_to_modify[2])
            elif geometry_index == 1 or geometry_index == 4 or geometry_index == 7:
                value_to_modify = (value_to_modify[0], value_to_modify[1] + delta_pos, value_to_modify[2])
            elif geometry_index == 2 or geometry_index == 5 or geometry_index == 8:
                value_to_modify = (value_to_modify[0], value_to_modify[1], value_to_modify[2] + delta_pos)
            if edit_mode == EditMode.POSITION:
                selected_object.location = value_to_modify
            elif edit_mode == EditMode.SCALE:
                selected_object.scale = value_to_modify
            elif edit_mode == EditMode.ROTATION:
                selected_object.rotation = value_to_modify

    def mouse_pos_callback(self, window, xpos, ypos):
        if self.track_mouse:
            if self.selected_geometry.name == None:
                super().mouse_pos_callback(window, xpos, ypos)
            else:
                self.update_mouse_pos(
                    self.get_geometry3D(self.selected_geometry.name),
                    self.edit_mode, xpos-self.last_mouse_pos[0], ypos-self.last_mouse_pos[1])
                if self.selection_axis != None:
                    self.selection_axis.location = self.get_geometry3D(self.selected_geometry.name).location
                    self.selection_axis.scale = self.get_geometry3D(self.selected_geometry.name).scale
        self.last_mouse_pos = (xpos, ypos)

    def key_callback(self, window, key, scancode, action, mods):
        super().key_callback(window, key, scancode, action, mods)
            
    def pick_object(self, location):
        if self.fullscreen:
            selection = self.picking_object.MousePick(
                self.max_resolution[0], self.max_resolution[1],
                location[0], location[1],
                self.geometry3D, self.selection_geometry,
                self.camera, self.selected_geometry)
        else:
            selection = self.picking_object.MousePick(
                self.display_width, self.display_height,
                location[0], location[1],
                self.geometry3D, self.selection_geometry,
                self.camera, self.selected_geometry)
        #print("selection: object is " + str(selection.object_index) +
        #      ", fragment is " + str(selection.primitive_index) +
        #      ", cube is " + str(selection.cube_index))
        if selection.geometry_index == -1: # i.e. when none of the "editing" objects are selected
            if self.selected_geometry.name != None:
                self.get_geometry3D(self.selected_geometry.name).selected = False
            if selection.name != None and selection.name != self.selected_geometry.name:
                object = self.get_geometry3D(selection.name)
                object.selected = True
                self.edit_mode = EditMode.POSITION
                self.selection_axis = Axis(
                    self.get_shader('colored'),
                    location=object.location,
                    boundaries=offset_object_boundaries(object.get_boundaries(), boundaries_offset),
                    scale=object.scale)
                self.selected_geometry = selection
            elif selection.name != None and self.edit_mode == EditMode.POSITION:
                object = self.get_geometry3D(selection.name)
                object.selected = True
                self.edit_mode = EditMode.SCALE
                self.selection_axis = Axis(
                    self.get_shader('colored'),
                    location=object.location,
                    boundaries=offset_object_boundaries(object.get_boundaries(), boundaries_offset),
                    scale=object.scale,
                    rotation=object.rotation)
            elif selection.name != None and self.edit_mode == EditMode.SCALE:
                object = self.get_geometry3D(selection.name)
                object.selected = True
                self.edit_mode = EditMode.ROTATION
                self.update_rotation_torus(self.selection_geometry[6], object, "x")
                self.update_rotation_torus(self.selection_geometry[7], object, "y")
                self.update_rotation_torus(self.selection_geometry[8], object, "z")
                self.selection_axis = None
            else:
                self.edit_mode = EditMode.NOT_SELECTED
                self.selected_geometry = Selection(None, -1, -1)
                self.selection_axis = None
        else:
            self.selected_geometry = selection

    def display_selection_cubes(self, cube, object, axis, negative):
        cube.location = copy.deepcopy(object.location)
        boundaries = offset_object_boundaries(object.get_boundaries(), boundaries_offset)
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

    def update_rotation_torus(self, torus, object, axis):
        boundaries = offset_object_boundaries(object.get_boundaries(), boundaries_offset)
        max_object_diameter = (boundaries[3] - boundaries[0]) * object.scale[0]
        if (boundaries[4] - boundaries[1]) * object.scale[1] > max_object_diameter:
            max_object_diameter = (boundaries[4] - boundaries[1]) * object.scale[1]
        if (boundaries[5] - boundaries[2]) * object.scale[2] > max_object_diameter:
            max_object_diameter = (boundaries[5] - boundaries[2]) * object.scale[2]
        torus.resize(max_object_diameter / 2)

    def display_tori(self, torus, object, axis):
        torus.location = object.location
        torus.rotation = object.rotation
        torus.draw(self.camera, self.lights)

    def draw(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        display_width, display_height = glfw.get_framebuffer_size(self.window)
        for _, geometry in self.geometry3D.items():
            geometry.draw(self.camera, self.lights)
        if self.selected_geometry.name != None:
            object = self.get_geometry3D(self.selected_geometry.name) # Shallow copy
            if self.edit_mode == EditMode.POSITION or self.edit_mode == EditMode.SCALE:
                self.display_selection_cubes(self.selection_geometry[0], object, "x", True)
                self.display_selection_cubes(self.selection_geometry[1], object, "y", True)
                self.display_selection_cubes(self.selection_geometry[2], object, "z", True)
                self.display_selection_cubes(self.selection_geometry[3], object, "x", False)
                self.display_selection_cubes(self.selection_geometry[4], object, "y", False)
                self.display_selection_cubes(self.selection_geometry[5], object, "z", False)
            elif self.edit_mode == EditMode.ROTATION:
                self.display_tori(self.selection_geometry[6], object, "x")
                self.display_tori(self.selection_geometry[7], object, "y")
                self.display_tori(self.selection_geometry[8], object, "z")
            if self.selection_axis != None:
                self.selection_axis.draw(self.camera, self.lights)
        for _, geometry in self.geometry2D.items():
            geometry.draw(display_width, display_height)
