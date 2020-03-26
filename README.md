# distasks
## Distribute tasks across workers through the internet
### Basic Structure
Distasks has client and server components. The server provides a ZIP file with a python file or shell script to be run on clients, and a function that takes in a sequential number for a task and returns parameters the client should run the code with. The client downloads the zip file, requests parameters, runs the task, and reports back to the server. The server can do whatever it wants with this result, and even indicate the task should be repeated. 
### An example
Yeah I'm too lazy to write documentation, so I just wrote a heavily commented example
Server: 
```py
from distasks import server
import logging

# Show all messages (logs assignments and completions)
logging.basicConfig(level=logging.DEBUG)

# You can zip a physical file or directory as well,
#  this just generates a simple zip file from a string
server.zip.zip_str("task.py", """import time, os
from distasks.client import persistant

# This is the main entrypoint called by the client. It can also be an async function.
#  The entrypoint can also be called main.sh which would be passed the paramaters on
#  the command line and have its output sent back to the server
def main(msg):
    print("Server says:", msg)

    # If you want to store values in memory across task runs,
    #  use the distasks.client.persistant module
    if not hasattr(persistant, "num") or type(persistant.num) != int:
        persistant.num = 0
    persistant.num += 1
    print("num:", persistant.num)
    time.sleep(1)
    # This result should be JSON serializeable. It will be sent back
    #  to the server
    return msg[1:]
""", "assets.zip") # saves it to assets.zip


# This function called for every job.
#  the number goes up sequentially, starting at 0
#  (or the start_at kwarg of the server)
#  It's output should be JSON serializeable (if not, try using pickle)
def get_job_func(num):
    return f"Hello {num}"

# This function is called when a result is submitted by a client
#  it is passed a task instance that has a "data" attribute with
#  the parameters passed, and a "runs" attribute with the amount
#  of times it was run, and the result the client sent (again, 
#  must be JSON serializeable)
#  If the function return value is truthy, the task is repeated
def on_complete_func(task, res):
    print(f"Result of {task.data}: {res}")
    if task.runs < 2:
        print("Repeat it!")
        return True # repeat the task!
    else:
        print("Repeat successful!")

# This function creates and instanstiates a distasks Server
#  You can always subclass yourself, this just makes it easier
# The server will run the server on port 8080 
s = server.simple_server(get_job_func, # the job function
    "assets.zip", # The zip file clients will download
    # This requires clients to provide a password ("hi")
    #  in order to be assigned tasks. This helps prevent
    #  someone from feeding the server false results.
    # This can be a custom function if you want. It is passed
    #  the value of the client's identify_payload kwarg
    verify_client_func=server.pwd_checker("hi"),
    # This is highly recommended: saves the server's progress
    #  to a file after each task, and is read from whenever it
    #  starts up again. Will only save completed tasks.
    save_filename="prog.txt",
    on_complete_func=on_complete_func,
    # The number to start at, defaults to 0
    start_at=1,
    # Whether to enable the status API. This is required for the
    #  dashboard to work. (defaults to true)
    api=True)

if __name__ == "__main__":
    # Runs the server forever. This function is blocking but the
    #  server is completely asynchronous
    s.run()
```
And a corresponding client:
```py
from distasks import client
import logging

# Prints all messages describing what the client is doing
logging.basicConfig(level=logging.DEBUG)

# The first argument is a hostname to connect to
#  (this is because it is used for bot http:// and ws:// URIs)
c = client.DistasksClient("distasks.scoder12.repl.co", 
    # The name to identify this client to the server
    "client", 
    # if False will use https, if True will use http
    use_http=False,
    identify_payload={
        # If your server is password protected, you put the password
        #  here. You can also have a custom function on the server,
        #  which will be passed the (JSON serializeable) data here
        "pwd": "hi"
    },
    # If your zip isn't too big, this is a good option to enable
    #  because then you don't have to worry about bumping the version 
    #  number on the server
    always_update=True,
    # Start a simple web server on port 8080
    web=True)

if __name__ == "__main__":
    # Runs the client forever. This function is blocking but the
    #  server is completely asynchronous
    c.run()
```

If you need help configuring, want to request a feature, or found a bug feel free to open an issue. Pull requests are welcome.

Made by [Scoder12](https://scoder12.ml)
