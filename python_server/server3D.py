import socket
import sys
import pygame

from process_command import process_command
from Framework.ServerFramework import *

table_x = -1
table_z = -0.5
framework = None

def open_window(screen_posX, screen_posY, screen_width, screen_heigh):
    global framework
    if framework == None:
        framework = ServerFramework(screen_posX, screen_posY, screen_width, screen_heigh)
        framework.initialize()
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
            full_str += receivedData.decode()
            end = full_str.index('\n')
            # Split buffer into single line with no \n
            while end >= 0 and running:
                if end > 0:
                    str = full_str[0:end-1]
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
