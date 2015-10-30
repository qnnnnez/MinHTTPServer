#!/usr/bin/env python3.5
import sys
import servers
import handlers

def run_server(server_class, handler_class, port):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print('Servering HTTP on port {0}'.format(port))
    httpd.serve_forever()

if __name__ == '__main__':
    from servers import ThreadingHTTPServer, ForkingHTTPServer
    from handlers import RangedHTTPRequestHandler, ProxyHTTPRequestHandler
    if len(sys.argv) == 2:
        port = int(sys.argv[1])
    else:
        port  = 8000
    # run_server(ThreadingHTTPServer, RangedHTTPRequestHandler, port)
    run_server(ThreadingHTTPServer, ProxyHTTPRequestHandler, port)

