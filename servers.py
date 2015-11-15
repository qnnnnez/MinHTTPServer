import socketserver
from http.server import HTTPServer
import contextlib

class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    pass

class ForkingHTTPServer(socketserver.ForkingMixIn, HTTPServer):
    pass

@contextlib.contextmanager
def run_server(address, server_class, handler_class):
    httpd = server_class(address, handler_class)
    print('Serving HTTP on address ({}:{})'.format(*address))
    yield httpd
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('Keyboard interrupt received, exiting.')
        httpd.shutdown()

