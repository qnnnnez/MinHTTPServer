from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from http import HTTPStatus
import urllib.parse
import urllib.request
import random
import math
import os
import shutil
import socket
import time
import copy
from rangedfile import RangedFile
from chunkedfile import ChunkedWriter

__version__ = '0.1'

class RangedHTTPRequestHandler(SimpleHTTPRequestHandler):
    '''Extended SimpleHTTPRequestHandler with HTTP request header Range supported.'''

    server_version = 'RangedHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def send_head(self):
        '''Same as super().send_header, but sending status code 206 and HTTP response header Content-Length.'''
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                             parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header('Location', new_url)
                self.end_headers()
                return None
            for index in 'index.html', 'index.htm':
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, 'File not found')
            return None
        try:
            if 'Range' not in self.headers:
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-type', ctype)
                fs = os.fstat(f.fileno())
                self.send_header('Content-Length', str(fs[6]))
                self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
                self.end_headers()
                return f
            else:
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header('Content-type', ctype)
                fs = os.fstat(f.fileno())
                self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
                rstart, rend = self.headers['Range'].split('=')[-1].split('-')
                rstart = 0 if rstart == '' else int(rstart)
                rend = fs[6] if rend == '' else int(rend)
                self.send_header('Content-Range', '{0}-{1}/{2}'.format(rstart, rend, fs[6]))
                self.send_header('Content-Length', str(rend - rstart + 1))
                self.end_headers()
                return f
        except:
            f.close()
            raise

    def copyfile(self, source, output_file):
        '''Same as super().copyfile, but send partial file if Range is in request headers.'''
        if 'Range' in self.headers:
            rstart, rend = self.headers['Range'].split('=')[-1].split('-')
            rstart = 0 if rstart == '' else int(rstart)
            rend = float('inf') if rend == '' else int(rend)
            input_file = RangedFile(source, rstart, rend)
        else:
            input_file = source
        super().copyfile(input_file, output_file)

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    '''A HTTP proxy request handler.'''

    server_version = 'ProxyHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def do_HEAD(self):
        '''Serve a HEAD request.'''
        self.authorize()
        request = urllib.request.Request(self.path, headers=self.headers, method='HEAD')
        request.headers['Connection'] = 'close'
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
            return
        try:
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
        finally:
            response.close()

    def do_GET(self):
        '''Serve a GET request.'''
        self.authorize()
        request = urllib.request.Request(self.path, headers=self.headers, method='GET')
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
            return
        try:
            self.transfer(response)
        finally:
            response.close()

    def do_POST(self):
        '''Serve a POST request.'''
        self.authorize()
        request = urllib.request.Request(self.path, headers=self.headers, method='POST', data=self.rfile.read())
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
            return
        try:
            self.transfer(response)
        finally:
            response.close()

    def do_CONNECT(self):
        '''Serve a CONNECT request.'''
        self.authorize()
        host, port = self.path.split(':')
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        self.send_response(200, 'Connection Established')
        self.end_headers()
        self.rfile.flush()
        self.wfile.flush()
        self.connection.setblocking(0)
        sock.setblocking(0)
        while True:
            try:
                buf = sock.recv(1024)
                if not buf: break
                self.connection.send(buf)
            except BlockingIOError:
                time.sleep(0.01)
            try:
                buf = self.connection.recv(1024)
                if not buf: break
                sock.send(buf)
            except BlockingIOError:
                time.sleep(0.01)
        sock.close()
        self.close_connection = True
        
    def authorize(self):
        pass

    def transfer(self, response):
        '''Send data to client.'''
        self.send_response(response.status)
        headers = copy.deepcopy(response.headers)
        del headers['Transfer-Encoding']
        del headers['Connection']
        for key, value in headers.items():
            self.send_header(key, value)
        if 'Content-Length' not in response.headers and self.headers.get('Connection').lower() == 'keep-alive':
            outfile = ChunkedWriter(self.wfile, -1)
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            shutil.copyfileobj(response, outfile)
            outfile.end_file()
        else:
            outfile = self.wfile
            self.end_headers()
            shutil.copyfileobj(response, self.wfile)
        
