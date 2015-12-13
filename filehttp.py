#!/usr/bin/env python3.5
from http.server import SimpleHTTPRequestHandler
import os
from http import HTTPStatus
import urllib.parse
import html
import sys
import io
import posixpath
from servers import run_server
from minhttp import MinHTTPRequestHandler, MinHTTPServer
from rangedfile import RangedFile

__version__ = '0.1'

class FileHTTPRequestHandler(MinHTTPRequestHandler,
                             SimpleHTTPRequestHandler):
    '''Extended SimpleHTTPRequestHandler with HTTP request header Range supported.'''

    server_version = 'FileHTTP/' + __version__
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        '''Same as SimpleHTTPRequestHandler, but we use self.outfile instead of self.wfile.'''
        f = self.send_head()
        if f:
            self.start_body()
            try:
                self.send_fileobj(f)
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
                if self.server.allow_lsdir:
                    return self.list_directory(path)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, 'File not found')
                    return None
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

    def send_fileobj(self, f):
        '''Send content of a file object to response body.'''
        if 'Range' in self.headers:
            rstart, rend = self.headers['Range'].split('=')[-1].split('-')
            rstart = 0 if rstart == '' else int(rstart)
            rend = float('inf') if rend == '' else int(rend)
            input_file = RangedFile(f, rstart, rend)
        else:
            input_file = f
        super().copyfile(input_file, self.outfile)

    def translate_path(self, path):
        '''Same as SimpleHTTPServer.translate_path, buf self.server.content_dir is used instead of os.getcwd()'''
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = self.server.content_dir
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

class FileHTTPServer(MinHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.content_dir = './'
        self.allow_lsdir = True

    @property
    def content_dir(self):
        return self._content_dir
    @content_dir.setter
    def content_dir(self, value):
        if not value.endswith('/'):
            value += '/'
        self._content_dir = value

def main(args):
    if len(args) == 1:
        port = int(args[0])
    else:
        port = 8000
    server_address = ('', port)
    with run_server(server_address, FileHTTPServer, FileHTTPRequestHandler) as server:
        pass

if __name__ == '__main__':
    from sys import argv
    main(argv[1:])
    
