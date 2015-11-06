from http import HTTPStatus
import urllib.parse
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
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler
from rangedfile import RangedFile
from chunkedfile import ChunkedWriter

__version__ = '0.1'


class MinHTTPRequestHandler(BaseHTTPRequestHandler):
    '''Extend BaseHTTPRequestHandler to support:
    * long HTTP connection
    * Content-Encoding
    self.outfile instead of self.wfile should be used.
    '''

    server_version = 'MinHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def send_header(self, keyword, value):
        '''Find Content-Length and catch it if possible.'''
        if not hasattr(self, '_content_length'):
            self._content_length = None
        if keyword == 'Content-Length':
            self._content_length = value
        else:
            super().send_header(keyword, value)

    def end_headers(self):
        '''Send extra HTTP headers.
        If you want to send response body as well, you are supposed to use self.start_body() and self.end_body().
        '''
        self.using_gzip = False
        self.using_chunked = False
        self.outfile = self.wfile

        if 'Accept-Encoding' in self.headers:
            encodings = self.headers['Accept-Encoding'].split(',')
            encodings = [encoding.strip() for encoding in encodings]
            if 'gzip' in encodings:
                self.send_header('Content-Encoding', 'gzip')
                self.using_gzip = True
            elif 'deflate' in encodings:
                # unusual
                pass

        if self.close_connection:
            self.send_header('Connection', 'close')
        else:
            self.send_header('Connection', 'keep-alive')

        # when using gzip, we cannot determine transfer length even if content length is known.
        if self._content_length and not self.using_gzip:
            # Content-Length will be catch by self.send_header
            super().send_header('Content-Length', self._content_length)

        if self.using_gzip or not self._content_length:
            # transfer length unknown.
            self.send_header('Transfer-Encoding', 'chunked')
            self.using_chunked = True

        super().end_headers()
        delattr(self, '_content_length')

    def just_end_headers(self):
        '''Just end headers, doing nothing else.'''
        if self._content_length:
            super().send_header('Content-Length', self._content_length)
        super().end_headers()
        delattr(self, '_content_length')

    def start_body(self):
        '''Create self.outfile, which replaces self.wfile'''
        if self.using_chunked:
            self.outfile = self.chunked_file = ChunkedWriter(
                    self.outfile, -1)
        else:
            self.chunked_file = None
        if self.using_gzip:
            self.outfile = self.gzip_file = gzip.GzipFile(
                    fileobj=self.outfile, mode='wb')
        else:
            self.gzip_file = None

    def end_body(self):
        '''Do some clean up works.'''
        self.outfile.flush()
        if self.gzip_file:
            self.gzip_file.flush()
            self.gzip_file.close()
        if self.chunked_file:
            self.chunked_file.end_file()
        self.gzip_file = self.chunked_file = None


class FileHTTPRequestHandler(MinHTTPRequestHandler, SimpleHTTPRequestHandler):
    '''Extended SimpleHTTPRequestHandler with HTTP request header Range supported.'''

    server_version = 'FileHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        '''Same as SimpleHTTPRequestHandler, but we use self.outfile instead of self.wfile.'''
        f = self.send_head()
        if f:
            self.start_body()
            try:
                self.send_file(f)
            finally:
                f.close()
                self.end_body()
                

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
                fs = os.fstat(f.fileno())
                if 'If-Modified-Since' in self.headers:
                    if self.headers['If-Modified-Since'] == self.date_time_string(fs.st_mtime):
                        self.send_response(HTTPStatus.NOT_MODIFIED)
                        self.end_headers()
                        f.close()
                        return None
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-type', ctype)
                self.send_header('Content-Length', str(fs[6]))
                self.send_header('Last-Modified',
                                 self.date_time_string(fs.st_mtime))
                self.end_headers()
                return f
            else:
                fs = os.fstat(f.fileno())
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header('Content-type', ctype)
                self.send_header('Last-Modified',
                                 self.date_time_string(fs.st_mtime))
                rstart, rend = self.headers['Range'].split('=')[-1].split('-')
                rstart = 0 if rstart == '' else int(rstart)
                rend = fs[6] if rend == '' else int(rend)
                self.send_header('Content-Range', '{0}-{1}/{2}'.format(
                    rstart, rend, fs[6]))
                self.send_header('Content-Length', str(rend - rstart + 1))
                self.end_headers()
                return f
        except:
            f.close()
            raise

    def list_directory(self, path):
        '''Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().
        '''
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                'No permission to list directory')
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath)
        enc = sys.getfilesystemencoding()
        title = 'Directory listing for %s' % displaypath
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        r.append('<hr>\n<ul>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + '/'
                linkname = name + '/'
            if os.path.islink(fullname):
                displayname = name + '@'
                # Note: a link to a directory displays with @ and links with /
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname)))
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-type', 'text/html; charset=%s' % enc)
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        return f

    def send_file(self, f):
        '''Send content of a file object to response body.'''
        if 'Range' in self.headers:
            rstart, rend = self.headers['Range'].split('=')[-1].split('-')
            rstart = 0 if rstart == '' else int(rstart)
            rend = float('inf') if rend == '' else int(rend)
            input_file = RangedFile(f, rstart, rend)
        else:
            input_file = f
        super().copyfile(input_file, self.outfile)

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
        
