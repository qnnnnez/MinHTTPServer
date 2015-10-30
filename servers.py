import socketserver
from http.server import HTTPServer

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    pass

class ForkingHTTPServer(socketserver.ForkingMixIn, HTTPServer):
    pass

