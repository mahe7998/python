import socket
import sys
import _thread
from process_command import process_command

# Function to run Python code passed in text format
# code: the code (supports multtlines, i.e. 
#    "import tensorflow as tf\nprint(tf.__version__)\n"
# shared_globals: necessary to hold all objects that are already defined 
# by previously executed code
# Returns: byte array containing the error (if any) or stdout
# Error format: __error__("the python error")
def run_python_code(code, shared_globals):
    b = bytearray()
    try:
        old_stdout = sys.stdout
        code_object = compile(code, "<string>", 'exec')
        redirected_output = sys.stdout = StringIO()
        exec(code_object, shared_globals)
        sys.stdout = old_stdout
        b.extend(map(ord, redirected_output.getvalue()))
    except Exception:
        e = sys.exc_info()[1]
        sys.stdout = old_stdout
        str = "__error__(\"{}\")\n".format(e)
        b.extend(map(ord, str))
    return b

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
        _thread.start_new_thread(on_connect,(new_socket, address))

finally:
    sock.close()
