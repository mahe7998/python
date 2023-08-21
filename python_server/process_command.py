import sys
from io import StringIO
# Use pip install parse to install following package
from parse import *

# Function to run Python code passed in text format
# code: the code (supports multilines, i.e. 
#    "import tensorflow as tf\nprint(tf.__version__)\n"
# shared_globals: necessary to hold all objects that are already defined 
# by previously executed code
# Returns: byte array containing the error (if any) or stdout
# Error format: __error__("the python error")
def run_python_code(code, shared_globals, id):
    b = bytearray()
    try:
        old_stdout = sys.stdout
        code_object = compile(code, "<string>", 'exec')
        redirected_output = sys.stdout = StringIO()
        exec(code_object, shared_globals)
        sys.stdout = old_stdout
        str = redirected_output.getvalue()
        str += "\n__done__({:d})\n".format(id)
        print("!exec done id {:d}!\n".format(id)) # Display debug output
        b.extend(map(ord, str))
    except Exception:
        e = sys.exc_info()[1]
        sys.stdout = old_stdout
        str = "__error__({},\"{}\")\n".format(id,e)
        b.extend(map(ord, str))
        print("!error for code ID {}: \"{}\"!\n<<<".format(id,e))
    return b

def process_command(socket, shared_globals, cmd, code):
    if cmd[0:7] == '__run__':
        if cmd.find('(') > -1 and cmd.find(')') > -1: 
            id = parse("__run__({:d})", cmd)[0]
        else:
            id = 0
        print("!running code ID {}\n>>>\n{}!".format(id,code))
        socket.send(run_python_code(code, shared_globals, id))
        code = ""
    elif cmd == 'reset':
        shared_globals.clear()
        print("!environment resetted!\n")
    elif cmd == 'exit' or cmd == 'quit':
        print("!closing python server connection!\n")
        return False, False, ""
    elif cmd == 'terminate':
        print("!exiting python server!\n")
        return True, False, ""
    else:
        # Echo single line locally
        print(cmd)
        code += cmd + '\n'
    return False, True, code