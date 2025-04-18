import socket
from process_command import process_command
from Framework.ServerFramework import *

table_x = -1
table_z = -0.5
framework = None
scroll_text_window = None
picture_angle = 0.0
show_alignments = False

class MyServerFramework(ServerFramework):

    def __init__(self):
        super().__init__()

    def update_display_size(self, display_width, display_height):
        global scroll_text_window
        global show_alignments
        super().update_display_size(display_width, display_height)
        if not show_alignments:
            scroll_wnd_bb = scroll_text_window.get_bounding_box()
            self.get_geometry2D("left window border").update_position(
                (scroll_wnd_bb[2], display_height), (scroll_wnd_bb[2], 0.0), display_width, display_height)
        picture_bb = framework.get_geometry2D("Picture Lucas").get_bounding_box()
        self.get_geometry2D("White frame").update_position(
            (picture_bb[0], picture_bb[1]), (picture_bb[2]-picture_bb[0], picture_bb[3]-picture_bb[1]), 
            0.0, display_width, display_height)

def open_window(screen_posX, screen_posY, display_width, display_height, fullscreen=False, display_num=-1):
    global framework
    global scroll_text_window
    global picture_angle
    global show_alignments
    if framework == None:
        framework = MyServerFramework()
        framework.create_window(screen_posX, screen_posY, display_width, display_height, fullscreen, display_num)
        # Note: we can create a maximum of 1 light; adding more would require increasing NUM_LIGHTS
        # in textured_frags.vs shader code.
        framework.add_light("main light", Light(0, (0, 5, 0), (1, 1, 1)))
        framework.add_geometry3D(
            "axis",
            Axis(framework.get_shader('colored'), (0, 0, 0), [-100.0, -100.0, -100.0, 100.0, 100.0, 100.0]),
            False) # Not selectable!
        framework.add_geometry3D(
            "grid",
            XZGrid(framework.get_shader('colored'), (0, 0, 0), 100.0),
            False) # Not selectable!
        framework.add_geometry3D(
            "floor",
            LoadMesh(framework.get_shader('textured'),
                     "models/floor.obj", "images/tiles.png",
                     location=(0, 0, 0),
                     scale=(10, 0, 10),
                     move_rotation=(0, 0, 0)),
            False)
        framework.add_geometry3D(
            "table top",
            LoadMesh(framework.get_shader('textured'),
                     "models/tabletop.obj", "images/timber.png",
                     location=(table_x, 1, table_z),
                     scale=(1.2, 1, 1.2),
                     move_rotation=(0, 0, 0)))
        framework.add_geometry3D(
            "table leg 1",
            LoadMesh(framework.get_shader('textured'),
                     "models/tableleg.obj", "images/timber.png",
                     location=(table_x-0.5, 0.5, table_z-0.5),
                     scale=(1, 1, 1),
                     move_rotation=(0, 0, 0)))
        framework.add_geometry3D(
            "table leg 2",
            LoadMesh(framework.get_shader('textured'),
                     "models/tableleg.obj", "images/timber.png",
                     location=(table_x-0.5, 0.5, table_z+0.5),
                     scale=(1, 1, 1),
                     move_rotation=(0, 0, 0)))
        framework.add_geometry3D(
            "table leg 3",
            LoadMesh(framework.get_shader('textured'),
                     "models/tableleg.obj", "images/timber.png",
                     location=(table_x+0.5, 0.5, table_z-0.5),
                     scale=(1, 1, 1),
                     move_rotation=(0, 0, 0)))
        framework.add_geometry3D(
            "table leg 4",
            LoadMesh(framework.get_shader('textured'),
                     "models/tableleg.obj", "images/timber.png",
                     location=(table_x+0.5, 0.5, table_z+0.5),
                     scale=(1, 1, 1),
                     move_rotation=(0, 0, 0)))
        framework.add_geometry3D(
            "teapot",
            LoadMesh(framework.get_shader('textured'),
                     "models/teapot.obj", "images/gold.png",
                     location=(table_x, 1.07, table_z),
                     scale=(0.1, 0.1, 0.1),
                rotation=(0, 0, 0),
                move_rotation=(0, 0, 0)))
        framework.add_geometry3D("Torus", 
            Torus(framework.get_shader('textured'), "images/gold.png", 
                  1.0, 0.3, location=(table_x+0.5, 1.25, table_z-0.3),
                  rotation=(0.0, 0.0, 0,0), scale=(0.15, 0.15, 0.15), 
                  move_rotation=(0.0, 2.0, 0.0)))

        # Below: we pre-load the 96 first characters of the font (i.e. all
        # displayable characters in the ASCII table) 256 represents the
        # maximum number of characters in the font texture cache. Special characters
        # like accents and other non-ASCII characters are loaded on demand.
        framework.load_font("FreeMono", "fonts/FreeMono.ttf", 
            17, 21, 96, 256, "FreeMono.png")
        framework.load_font("FreeMonoBold", "fonts/FreeMonoBold.ttf", 
            13, 15, 96, 256, "FreeMonoBold.png")
        
        framework.add_geometry2D("center", 
            TextWindow(framework.get_font("FreeMono"), (0, 0), 25, 4, 0.0, 0.4, Alignments.CENTER, 
                       (1.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
        framework.get_geometry2D("center").print_text(2, 1, "_/Jacques is good!/_")
        framework.get_geometry2D("center").print_text(3, 2, "    3rd line ")

        if show_alignments:
            framework.add_geometry2D("top left", 
                TextWindow(framework.get_font("FreeMono"), (1, 1), 8, 1, 0.0, 0.0, Alignments.TOP_LEFT, 
                           (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("top left").print_text(0, 0, "top left")
            framework.add_geometry2D("bottom left",
                TextWindow(framework.get_font("FreeMono"), (1, 1), 11, 1, 0.0,  0.0, Alignments.BOTTOM_LEFT, 
                           (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("bottom left").print_text(0, 0, "bottom left")
            framework.add_geometry2D("center left", 
                TextWindow(framework.get_font("FreeMono"), (1, 0), 11, 1, 0.0,  0.0, Alignments.CENTER_LEFT, 
                           (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("center left").print_text(0, 0, "center left")
        else:
            framework.add_geometry2D("top to bottom left", 
                ScrollTextWindow(framework.get_font("FreeMono"), (1, 1), 15, 1, 0.0,  0.0, Alignments.TOP_TO_BOTTOM_LEFT, 
                                 (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0), display_width, display_height))
            scroll_text_window = framework.get_geometry2D("top to bottom left")
            scroll_text_window.load_text("top to bottom left scroll window")
            scroll_wnd_bb = scroll_text_window.get_bounding_box()
            framework.add_geometry2D("left window border", 
                Line(framework.get_shader('geometry 2D'), 
                    (scroll_wnd_bb[2], display_height), (scroll_wnd_bb[2], 0.0), (1.0, 0.0), (1.0, 1.0, 1.0),
                    display_width, display_height))

        framework.add_geometry2D("top center", 
            TextWindow(framework.get_font("FreeMono"), (0, 1), 12, 1, 0.0,  0.0, Alignments.TOP_CENTER, 
                       (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
        framework.get_geometry2D("top center").print_text(0, 0, " top center ")
        framework.add_geometry2D("bottom center",
            TextWindow(framework.get_font("FreeMono"), (1, 1), 13, 1, 0.0,  0.0, Alignments.BOTTOM_CENTER, 
                       (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
        framework.get_geometry2D("bottom center").print_text(0, 0, "bottom center")

        if show_alignments:
            framework.add_geometry2D("top right", 
                TextWindow(framework.get_font("FreeMono"), (1, 1), 9, 1, 0.0,  0.0, Alignments.TOP_RIGHT, 
                (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("top right").print_text(0, 0, "top right")
            framework.add_geometry2D("center right", 
                TextWindow(framework.get_font("FreeMono"), (1, 0), 12, 1, 0.0,  0.0, Alignments.CENTER_RIGHT, 
                (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("center right").print_text(0, 0, "center right")
            framework.add_geometry2D("bottom right", 
                TextWindow(framework.get_font("FreeMono"), (1, 1), 12, 1, 0.0,  0.0, Alignments.BOTTOM_RIGHT, 
                (1.0, 0.0, 0.0, 0.8), (1.0, 1.0, 1.0, 0.8), display_width, display_height))
            framework.get_geometry2D("bottom right").print_text(0, 0, "bottom right")
        else:
            framework.add_geometry2D("top to bottom right",
                TextWindow(framework.get_font("FreeMonoBold"), (0, 1), 30, 30, 0.0,  0.0, Alignments.TOP_TO_BOTTOM_RIGHT,
                (1.0, 1.0, 1.0, 0.8), (0.0, 0.0, 0.0, 0.8), display_width, display_height))
            framework.get_geometry2D("top to bottom right").print_text(0, 0, "top to bottom right")

        framework.add_geometry2D("Picture Lucas",
            Picture(framework.get_shader('picture'), "images/Lucas Photo 12-22 2x3.jpg", (400, 30), (150, 200),
                    picture_angle, 0.2, display_width, display_height))
        picture_bb = framework.get_geometry2D("Picture Lucas").get_bounding_box()
        framework.add_geometry2D("White frame", 
            Frame(framework.get_shader('geometry 2D'), 
                (picture_bb[0], picture_bb[1]), (picture_bb[2]-picture_bb[0], picture_bb[3]-picture_bb[1]), 
                (1.0, 1.0), (1.0, 1.0, 1.0), picture_angle, 0.0, display_width, display_height))
        framework.add_geometry2D("Lucas", 
            TextWindow(framework.get_font("FreeMonoBold"), (picture_bb[0]+15, picture_bb[3]-20), 
                       15, 1, 0.0, 0.05, Alignments.TOP_LEFT, (0.0, 0.0, 0.0, 0.7), (1.0, 1.0, 1.0, 0.7),
                       display_width, display_height))
        framework.get_geometry2D("Lucas").print_text(2, 0, "Lucas Mahé")

def close_window():
    global framework
    if framework != None:
        framework.terminate()
        framework = None

def on_connect(new_socket, address):
    global framework
    print("Connected from", address)
    full_str = ""
    code = ""
    terminate = False
    running = True
    
    while running:
        try:
            receivedData = new_socket.recv(1024)
            if not receivedData: 
                break
        except socket.error as e:
            if e.errno == socket.errno.EWOULDBLOCK:
                if framework != None:
                    if framework.main_loop(): # returns done
                        framework.terminate()
                        framework = None
            else:
                # Handle other socket errors
                print("Server socket error: " + str(e))
        else:
            try:
                full_str += receivedData.decode()
            except ValueError as ve:
                print("Error: could not decode received data: " + ve.reason)
                full_str = "\n"
            end = full_str.index('\n')
            cr_in_string = '\r' in full_str # Once CR, always CR
            delta = 0
            # Split buffer into single line with no \n
            while end >= 0 and running:
                if cr_in_string:
                    delta = 1
                if end > 0:
                    str = full_str[0:end-delta]
                else:
                    str = ''
                #print("{a}:{b}".format(a=end, b=str))
                terminate, running, code = process_command(new_socket, globals(), str, code)
                full_str = full_str[end+1:len(full_str)]
                try:
                    end = full_str.index('\n')
                except:
                    end = -1

    new_socket.close()
    print("!Disconnected from", address, "!")
    # Enable below if closing window when client disconnects
    #if framework != None:
    #    framework.terminate()
    #    framework = None
    return terminate

# Create a socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# Ensure that you can restart your server quickly when it terminates
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# Set the client socket's TCP "well-known port" number
well_known_port = 5001
sock.bind(('', well_known_port))
# Set the number of clients waiting for connection that can be queued
sock.listen(5)
# Don't block to process window events when waiting for connections
sock.setblocking(False)
terminate = False

# loop waiting for connections (terminate with Ctrl-C)
try:
    
    while not terminate:
        try:
            new_socket, address = sock.accept()
        except socket.error as e:
            if e.errno == socket.errno.EWOULDBLOCK:
                if framework != None:
                    if framework.main_loop(): # returns done
                        framework.terminate()
                        framework = None
            else:
                # Handle other socket errors
                print("Server socket error: " + str(e))
        else:
            new_socket.setblocking(False)
            terminate = on_connect(new_socket, address)

finally:
    sock.close()
