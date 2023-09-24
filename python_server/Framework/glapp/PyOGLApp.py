import glfw
import glfw.GLFW as GLFW_CONSTANTS
from .PickingObject import *
from OpenGL.GL import *
from OpenGL.GLU import *
from .Camera import *
from .Monitor import *
from sys import platform
import time

class PyOGLApp():

    def __init__(self):
        self.max_field_depth = 30.0
        self.axis_size = 100
        self.track_mouse = False
        self.last_mouse_pos = (0, 0)
        self.last_mouse_click = 0
        self.camera = None
        self.lights = dict()
        glfw.init()
        monitors = glfw.get_monitors()
        self.monitors = []
        print("Monitors:")
        for monitor in monitors:
            self.monitors.append(Monitor(monitor))
        #if platform == "darwin":
        glfw.window_hint(GLFW_CONSTANTS.GLFW_OPENGL_PROFILE, GLFW_CONSTANTS.GLFW_OPENGL_CORE_PROFILE)
        glfw.window_hint(GLFW_CONSTANTS.GLFW_CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(GLFW_CONSTANTS.GLFW_CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(GLFW_CONSTANTS.GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE)
        glfw.window_hint(GLFW_CONSTANTS.GLFW_SAMPLES, 8)
        # Use below to remove window decorations
        #glfw.window_hint(GLFW_CONSTANTS.GLFW_DECORATED, GL_FALSE)

    def init_callbacks(self):
        glfw.set_mouse_button_callback(self.window, self.mouse_button_callback)
        glfw.set_cursor_pos_callback(self.window, self.mouse_pos_callback)
        glfw.set_scroll_callback(self.window, self.mouse_scroll_callback)
        glfw.set_key_callback(self.window, self.key_callback)
        glfw.set_framebuffer_size_callback(self.window, self.framebuffer_size_callback)

    def initialize_3D_space(self):
        pass

    def create_window(self, screen_posX, screen_posY, screen_width, screen_height, fullscreen=False, display_num=-1):
        self.display_width = screen_width
        self.display_height = screen_height
        if display_num >= len(self.monitors):
            raise Exception("Invalid display number")
        elif display_num == -1:
            print("Using default monitor:")
            default_monitor = glfw.get_primary_monitor()
            self.monitor = Monitor(default_monitor)
        else:
            print("Using monitor index %d:" % display_num)
            self.monitor = self.monitors[display_num]
        self.max_resolution, self.max_resolution_refresh_rate = self.monitor.get_max_resolution()
        if fullscreen:
            self.window = glfw.create_window(
                self.max_resolution[0], self.max_resolution[1], 
                "OpenGL in Python", self.monitor.internal_monitor, None)
            window_pos = glfw.get_window_pos(self.window)
            self.keep_display_size = (window_pos[0], window_pos[1], self.display_width, self.display_height)
            self.fullscreen = True
        else:
            self.window = glfw.create_window(
                self.display_width, self.display_height, 
                "OpenGL in Python", None, None)
            if display_num != -1 or screen_posX != -1 or screen_posY != -1:
                if screen_posX == -1:
                    screen_posX = 200
                if screen_posY == -1:
                    screen_posY = 200
                glfw.set_window_pos(
                    self.window, 
                    self.monitor.position[0]+screen_posX, 
                    self.monitor.position[1]+screen_posY)
            self.fullscreen = False
        glfw.make_context_current(self.window)
        self.init_callbacks()
        glEnable(GL_CULL_FACE) # Get rid of back side       
        glEnable(GL_BLEND) # Also need to set glBlendFunc below and draw object below first!
        glEnable(GL_DEPTH_TEST)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.frame_start = glfw.get_time()
        self.first_draw = True
        if fullscreen:
            self.camera = Camera(self.max_resolution[0], self.max_resolution[1])
        else:
            self.camera = Camera(self.display_width, self.display_height)
        self.camera.relative_move(5.0, 0.0, 2.0) # Initial camera position to see Axis
        self.initialize_3D_space()

    def add_light(self, name, light):
        self.lights[name] = light

    def terminate(self):
        glfw.terminate()

    def draw(self):
        pass

    def pick_object(self, location):
        return Selection(-1, -1, -1)

    def set_mouse_grab(self, grab):
        self.track_mouse = grab
        self.last_mouse_pos = glfw.get_cursor_pos(self.window)

    def set_fullscreen(self, fullscreen):
        if fullscreen == self.fullscreen:
            return
        if fullscreen:
            #print("Entering fullscreen")
            window_pos = glfw.get_window_pos(self.window)
            self.keep_display_size = (window_pos[0], window_pos[1], self.display_width, self.display_height)
            glfw.set_window_monitor(
                self.window, self.monitor.internal_monitor, 
                0, 0, self.max_resolution[0], self.max_resolution[1], self.max_resolution_refresh_rate)
            self.fullscreen = True
        else:
            #print("Leaving fullscreen")
            self.fullscreen = False
            glfw.set_window_monitor(
                self.window, None, 
                self.keep_display_size[0], self.keep_display_size[1], 
                self.keep_display_size[2], self.keep_display_size[3], 
                self.max_resolution_refresh_rate)

    def mouse_button_callback(self, window, button, action, mods):
        if button == glfw.MOUSE_BUTTON_LEFT and action == glfw.PRESS:
            if glfw.get_time() - self.last_mouse_click < 0.2:
                #print("double click!!")
                self.set_fullscreen(not self.fullscreen)
            else:
                self.pick_object(glfw.get_cursor_pos(self.window))
                self.set_mouse_grab(True)
                self.last_mouse_click = glfw.get_time()
        elif button == glfw.MOUSE_BUTTON_LEFT and action == glfw.RELEASE:
            self.set_mouse_grab(False)

    def mouse_pos_callback(self, window, xpos, ypos):
        if self.track_mouse:
            delta_x = xpos - self.last_mouse_pos[0]
            delta_y = ypos - self.last_mouse_pos[1]
            #print("Mouse moved: (%f, %f)" % (delta_x, delta_y))
            if self.camera != None:
                self.camera.update_mouse(delta_x, delta_y)
        self.last_mouse_pos = (xpos, ypos)

    def mouse_scroll_callback(self, window, xoffset, yoffset):
        if self.camera != None:
            self.camera.zoom(yoffset, False)

    def key_callback(self, window, key, scancode, action, mods):
        #print("key :" + str(key))
        if action == glfw.PRESS:
            #print("key down")
            return
        elif action == glfw.RELEASE:
            #print("key up")
            return
        elif action == glfw.REPEAT:
            #print("key repeat")
            return
    
    def update_display_size(self, display_width, display_height):
        pass

    def framebuffer_size_callback(self, window, width, height):
        #print("Resize event (%d, %d)" % (width, height))
        glViewport(0, 0, width, height)
        self.display_width = width
        self.display_height = height
        self.update_display_size(width, height)
        self.draw()
        glfw.swap_buffers(self.window)

    def update_events(self):
        done = False
        if glfw.window_should_close(self.window):
            done = True
        if self.camera != None:
            self.camera.update_keyboard(self.window)
        return done
    
    def update_view_port(self):
        if self.fullscreen:
            glViewport(0, 0, self.max_resolution[0], self.max_resolution[1])
        else:
            glViewport(0, 0, self.display_width, self.display_height)

    def main_loop(self):
        done = self.update_events()
        self.update_view_port() 
        self.draw()
        glfw.swap_buffers(self.window)
        glfw.poll_events()
        while (glfw.get_time()-self.frame_start) < 1/60:
            time.sleep(0.001)
        self.frame_start = glfw.get_time()
        return done