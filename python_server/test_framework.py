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
                location=pygame.Vector3(0, 0, 0),
                scale=pygame.Vector3(10, 0, 10),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tabletop.obj", "images/timber.png",
                location=pygame.Vector3(table_x, 1, table_z),
                scale=pygame.Vector3(1.2, 1, 1.2),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=pygame.Vector3(table_x-0.5, 0.5, table_z-0.5),
                scale=pygame.Vector3(1, 1, 1),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=pygame.Vector3(table_x-0.5, 0.5, table_z+0.5),
                scale=pygame.Vector3(1, 1, 1),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=pygame.Vector3(table_x+0.5, 0.5, table_z-0.5),
                scale=pygame.Vector3(1, 1, 1),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/tableleg.obj", "images/timber.png",
                location=pygame.Vector3(table_x+0.5, 0.5, table_z+0.5),
                scale=pygame.Vector3(1, 1, 1),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        framework.add_object(
            LoadMesh("models/teapot.obj", "images/gold.png",
                location=pygame.Vector3(table_x, 1.07, table_z),
                scale=pygame.Vector3(0.1, 0.1, 0.1),
                rotation=pygame.Vector3(0, 45, 0),
                move_rotation=pygame.Vector3(0, 0, 0)),
            'textured')
        
def close_window():
    global framework
    if framework != None:
        framework.terminate()
        framework = None


open_window(200, 200, 800, 600)
done = False
while not done:
    done = framework.main_loop()
close_window()
