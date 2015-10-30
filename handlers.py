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

__version__ = '0.1'

class RangedHTTPRequestHandler(SimpleHTTPRequestHandler):
    '''Extended SimpleHTTPRequestHandler with HTTP request header Range supported.'''

    server_version = 'RangedHTTP/' + __version__

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

    def copyfile(self, source, outputfile):
        '''Same as super().copyfile, but send partial file if Range is in request headers.
        '''
        if 'Range' not in self.headers:
            super().copyfile(source, outputfile)
            return
        rstart, rend = self.headers['Range'].split('=')[-1].split('-')
        rstart = 0 if rstart == '' else int(rstart)
        source.seek(rstart)
        if rend == '':
            super().copyfile(source, outputfile)
            return
        rend = int(rend)
        while source.tell() < rend:
            data = source.read(min(1024, rend - source.tell()))
            outputfile.write(data)

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    '''A HTTP proxy request handler.'''

    server_version = 'ProxyHTTP/' + __version__

    def do_HEAD(self):
        '''Serve a HEAD request.'''
        self.authorize()
        request = urllib.request.Request(self.path, headers=self.headers, method='HEAD')
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
            return
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
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
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        shutil.copyfileobj(response, self.wfile)
        response.close()

    def do_POST(self):
        '''Serve a POST request.'''
        self.authorize()
        try:
           request = urllib.request.Request(self.path, headers=self.headers, method='POST', data=self.rfile.read())
        except urllib.error.HTTPError as error:
            self.send_error(error.code, error.reason)
            return
        response = urllib.request.urlopen(request)
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        shutil.copyfileobj(response, self.wfile)
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
        

    def authorize(self):
        pass
        
