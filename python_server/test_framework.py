import pygame
from Framework.ServerFramework import *

table_x = -1
table_z = -0.5
framework = None

def open_window(screen_posX, screen_posY, screen_width, screen_heigh, fullscreen=False, display_num=0):
    global framework
    if framework == None:
        framework = ServerFramework(screen_posX, screen_posY, screen_width, screen_heigh, fullscreen, display_num)
        framework.initialize(fullscreen)
        framework.add_object(
            LoadMesh("models/floor.obj", "images/tiles.png",
                location=(0, 0, 0),
                scale=(10, 0, 10),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tabletop.obj", "images/timber.png",
                location=(table_x, 1, table_z),
                scale=(1.2, 1, 1.2),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=(table_x-0.5, 0.5, table_z-0.5),
                scale=(1, 1, 1),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=(table_x-0.5, 0.5, table_z+0.5),
                scale=(1, 1, 1),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=(table_x+0.5, 0.5, table_z-0.5),
                scale=(1, 1, 1),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=(table_x+0.5, 0.5, table_z+0.5),
                scale=(1, 1, 1),
                move_rotation=(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/teapot.obj", "images/gold.png",
                location=(table_x, 1.07, table_z),
                scale=(0.1, 0.1, 0.1),
                rotation=(0, 45, 0),
                move_rotation=(0, 0, 0)),
            'textured')
        # Below: first char is ' '(32), last char is '~' (126)
        # Font width is 20, height is 30
        framework.load_font("FreeMono", "fonts/FreeMono.ttf", 
            32, 126, 17, 21, "FreeMono.png")
        # Windows x is 100, y is 150
#        framework.add_text_window("text1", "FreeMono", 0, 10, Alignments.CENTER, 
#            30, 20, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.2))
#        framework.get_text_window("text1").print_text(2, 4, "_/Jacques is good!/_")

        #framework.load_font("FreeMonoBold", "fonts/FreeMonoBold.ttf", 
        #    32, 126, 13, 15, "FreeMonoBold.png")
        #framework.add_text_window("text2", "FreeMonoBold", 0, 10, Alignments.BOTTOM_CENTER, 
        #    30, 20, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.2))
        #framework.get_text_window("text2").print_text(2, 4, "_/Second Window!/_")

        # Required after loading any font as it changes the OpenGL viewport
        framework.update_view_port()
       
def close_window():
    global framework
    if framework != None:
        framework.terminate()
        framework = None

if __name__ == '__main__':
    open_window(200, 200, 800, 600)
    done = False
    while not done:
        done = framework.main_loop()
    close_window()
