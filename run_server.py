#!/usr/bin/env python3.5
import sys
import servers
import handlers

def run_server(server_class, handler_class, port):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print('Servering HTTP on port {0}'.format(port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
        httpd.server_close()
        sys.exit(0)

if __name__ == '__main__':
    from servers import ThreadingHTTPServer, ForkingHTTPServer
    from handlers import FileHTTPRequestHandler, ProxyHTTPRequestHandler
    port = 8000
    handler_class = FileHTTPRequestHandler
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    if len(sys.argv) >= 3:
        handler_class = eval(sys.argv[2])
    run_server(ThreadingHTTPServer, handler_class, port)

