import socket
import sys
from process_command import process_command

def on_connect(new_socket, address):
    print("Connected from", address)
    # loop serving the new client
    shared_globals = dict()
    full_str = ""
    code = ""
    running = True
    # Loop exists when client disconnects
    while running:
        receivedData = new_socket.recv(1024)
        if not receivedData: 
            break
        full_str += receivedData.decode()
        end = full_str.index('\n')
        # Split buffer into single line with no \n
        while end >= 0:
            if end > 0:
                str = full_str[0:end-1]
            else:
                str = ''
            #print("{a}:{b}".format(a=end, b=str))
            running, code = process_command(new_socket, shared_globals, str, code)
            full_str = full_str[end+1:len(full_str)]
            try:
                end = full_str.index('\n')
            except:
                end = -1
    new_socket.close()
    print("Disconnected from", address)

# Create a socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# Ensure that you can restart your server quickly when it terminates
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# Set the client socket's TCP "well-known port" number
well_known_port = 5001
sock.bind(('', well_known_port))
# Set the number of clients waiting for connection that can be queued
sock.listen(5)

# loop waiting for connections (terminate with Ctrl-C)
try:
    while True:
        new_socket, address = sock.accept()
        on_connect(new_socket, address)

finally:
    sock.close()
