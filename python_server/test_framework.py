from Framework.ServerFramework import *

table_x = -1
table_z = -0.5
framework = None
scroll_text_window = None

def open_window(screen_posX, screen_posY, screen_width, screen_heigh, fullscreen=False, display_num=-1):
    global framework
    global scroll_text_window
    if framework == None:
        framework = ServerFramework()
        framework.create_window(screen_posX, screen_posY, screen_width, screen_heigh, fullscreen, display_num)
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
            17, 21, 96, 256, "FreeMono.png")
        framework.load_font("FreeMonoBold", "fonts/FreeMonoBold.ttf", 
            13, 15, 96, 256, "FreeMonoBold.png")
        
        # Windows x is 100, y is 150
        framework.add_text_window("center", "FreeMono", 0, 0, Alignments.CENTER, 
            25, 4, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
        framework.get_text_window("center").print_text(2, 1, "_/Jacques is good!/_")
        framework.get_text_window("center").print_text(3, 2, "    3rd line ")

        if False:
            framework.add_text_window("top left", "FreeMono", 1, 1, Alignments.TOP_LEFT, 
                8, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("top left").print_text(0, 0, "top left")
            framework.add_text_window("bottom left", "FreeMono", 1, 1, Alignments.BOTTOM_LEFT, 
                11, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("bottom left").print_text(0, 0, "bottom left")
            framework.add_text_window("center left", "FreeMono", 1, 0, Alignments.CENTER_LEFT, 
                11, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("center left").print_text(0, 0, "center left")
        else:
            framework.add_text_window("top to bottom left", "FreeMono", 1, 1, Alignments.TOP_TO_BOTTOM_LEFT, 
                40, 30, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 0.9), 'scroll')
            scroll_text_window = framework.get_text_window("top to bottom left")
            scroll_text_window.load_text("top to bottom left scroll window")

        framework.add_text_window("top center", "FreeMono", 0, 1, Alignments.TOP_CENTER, 
            12, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
        framework.get_text_window("top center").print_text(0, 0, " top center ")
        framework.add_text_window("bottom center", "FreeMono", 1, 1, Alignments.BOTTOM_CENTER, 
            13, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
        framework.get_text_window("bottom center").print_text(0, 0, "bottom center")

        if False:
            framework.add_text_window("top right", "FreeMono", 1, 1, Alignments.TOP_RIGHT, 
                9, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("top right").print_text(0, 0, "top right")
            framework.add_text_window("center right", "FreeMono", 1, 0, Alignments.CENTER_RIGHT, 
                12, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("center right").print_text(0, 0, "center right")
            framework.add_text_window("bottom right", "FreeMono", 1, 1, Alignments.BOTTOM_RIGHT, 
                12, 1, (1.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.8))
            framework.get_text_window("bottom right").print_text(0, 0, "bottom right")
        else:
            framework.add_text_window("top to bottom right", "FreeMonoBold", 0, 1, Alignments.TOP_TO_BOTTOM_RIGHT, 
                30, 30, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 0.9))
            framework.get_text_window("top to bottom right").print_text(0, 0, "top to bottom right")

        framework.add_text_window("Lucas", "FreeMonoBold", 415, 210, Alignments.TOP_LEFT, 
            15, 1, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.5))
        framework.get_text_window("Lucas").print_text(2, 0, "Lucas Mahé")
        framework.add_picture("Picture Lucas", "images/Lucas Photo 12-22 2x3.jpg", 400, 30, 150, 200)

        # Required after loading any font as it changes the OpenGL viewport
        #framework.update_view_port()
       
def close_window():
    global framework
    if framework != None:
        framework.terminate()
        framework = None

if __name__ == '__main__':
    open_window(200, 200, 800, 600, False, -1)
    done = False
    line_mum = 2
    while not done:
        done = framework.main_loop()
        if scroll_text_window != None:
            scroll_text_window.load_text("Line " + str(line_mum))
            line_mum += 1
    close_window()
