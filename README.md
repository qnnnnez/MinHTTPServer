# MinHTTPServer
HTTP servers in python3 based on `http.server`.

## How it works
I just work with `http.server`, a part of python3 standard library.

It's easy to add some new features, as all the basic works are done by `http.server.BaseHTTPRequestHandler`, including creating a socket server, parse HTTP request, etc.

The `http` module provides useful information about the HTTP protocol.

To deal with URLs, `urllib.parse` is just good.

`importlib.machine` makes it possible to dynamically load and unload module from a specific path.
