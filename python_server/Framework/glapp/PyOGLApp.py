import pygame.display
from pygame.locals import *
from .PickingTexture import *
import os
from OpenGL.GL import *
from OpenGL.GLU import *
from sys import platform

# See https://stackoverflow.com/questions/64543449/update-during-resize-in-pygame
# on how to update display while resizing

class PyOGLApp():

    def __init__(self, screen_posX, screen_posY, screen_width, screen_height):
        os.environ['SDL_VIDEO_WINDOWS_POS'] = "%d,%d" % (screen_posX, screen_posY)
        self.display_width = screen_width
        self.display_height = screen_height
        self.max_field_depth = 30.0
        self.axis_size = 100
        self.track_mouse = False
        self.double_click_clock = pygame.time.Clock()
        self.screen_mode = DOUBLEBUF | OPENGL
        pygame.init()
        self.desktop_size = pygame.display.Info()
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        if platform == "darwin":
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
            #pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 32)
        self.screen = pygame.display.set_mode((screen_width, screen_height), self.screen_mode | RESIZABLE)
        pygame.display.set_caption('OpenGL in Python')
        self.clock = pygame.time.Clock()
        self.restore_mouse_position = pygame.mouse.get_pos()

    def initialize(self):
        pass

    def update_display(self, fullscreen, event=None):
        print("Update display fullscreen is %s" % ("True" if fullscreen else "False"))
        if event != None and event.type == pygame.VIDEORESIZE:
            if not fullscreen:
                # When coming back from full screen, the event size is the size of the screen and we want 
                # to restore the previous resolution
                if event.size[0] != self.desktop_size.current_w and event.size[1] != self.desktop_size.current_h:
                    print("Update display size to (%d, %d)" % (event.size[0], event.size[1]))
                    self.display_width = event.size[0]
                    self.display_height = event.size[1]
        if fullscreen:
            print("Update display to full screen  (%d, %d)" % (self.desktop_size.current_w, self.desktop_size.current_h))
            self.screen = pygame.display.set_mode(
                (self.desktop_size.current_w, self.desktop_size.current_h),
                self.screen_mode | pygame.FULLSCREEN)
            # Resize the OpenGL viewport
            glViewport(0, 0, self.desktop_size.current_w, self.desktop_size.current_h)
            
        else:
            print("Update display to windowed (%d, %d)" % (self.display_width, self.display_height))
            if platform != "linux" or self.screen.get_flags() & pygame.FULLSCREEN:
                self.screen = pygame.display.set_mode(
                    (self.display_width, self.display_height), self.screen_mode | RESIZABLE)

    def update(self):
        pass

    def display(self):
        pass

    def pick_object(self, fullscreen, location):
        return Selection(-1, -1, -1)

    def set_mouse_grab(self, grab):
        self.track_mouse = grab
        if platform != "linux" and platform != "win32":
            pygame.event.set_grab(grab)
            pygame.mouse.set_visible(not grab)
        if grab: # Avoid mouse jumping when grabbing
            pygame.mouse.get_rel()

    def update_event(self, event):
        done = False
        if event.type == pygame.QUIT:
            done = True
        elif event.type == pygame.VIDEORESIZE:
            print("Resize event (%d, %d), full screen is %d" % (event.size[0], event.size[1], self.screen.get_flags() & pygame.FULLSCREEN != 0))
            if self.screen.get_flags() & pygame.FULLSCREEN and (event.size[0] != self.desktop_size.current_w or event.size[1] != self.desktop_size.current_h):
                self.update_display(False, event)
            else:
                self.update_display(self.screen.get_flags() & pygame.FULLSCREEN or (event.size[0] == self.desktop_size.current_w and event.size[1] == self.desktop_size.current_h), event)
        elif event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                if self.screen.get_flags() & pygame.FULLSCREEN:
                    self.update_display(False)
                elif self.track_mouse:
                    self.set_mouse_grab(False)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.double_click_clock.tick() < 500:
                self.update_display(self.screen.get_flags() & pygame.FULLSCREEN == 0)
            else:
                self.pick_object(self.screen.get_flags() & pygame.FULLSCREEN, pygame.mouse.get_pos())
                self.set_mouse_grab(True)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.set_mouse_grab(False)
        return done

    def main_loop(self):
        done = False
        for event in pygame.event.get():
            done = self.update_event(event)
        self.update()
        self.display()
        pygame.display.flip()
        self.clock.tick(60)
        return done