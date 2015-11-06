from http import HTTPStatus
import urllib.request
import sys
import io
import random
import math
import os
import shutil
import socket
import time
import copy
import gzip
import html
from http.server import BaseHTTPRequestHandler
from chunkedfile import ChunkedWriter

__version__ = '0.1'

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    '''A HTTP proxy request handler.'''

    server_version = 'ProxyHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def do_HEAD(self):
        '''Serve a HEAD request.'''
        if not self.authorize(): return
        request = urllib.request.Request(self.path,
                                         headers=self.headers,
                                         method='HEAD')
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
        if not self.authorize(): return
        request = urllib.request.Request(self.path,
                                         headers=self.headers,
                                         method='GET')
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
        if not self.authorize(): return
        request = urllib.request.Request(self.path,
                                         headers=self.headers,
                                         method='POST',
                                         data=self.rfile.read())
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
        if not self.authorize(): return
        host, port = self.path.split(':')
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        self.send_response(HTTPStatus.OK, 'Connection Established')
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
        return True

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
        
