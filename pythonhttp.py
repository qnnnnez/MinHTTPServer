#!/usr/bin/env python3.5
from http.server import SimpleHTTPRequestHandler
import os
from http import HTTPStatus
import urllib.parse
import html
import sys
import io
import importlib.machinery
from rangedfile import RangedFile
from filehttp import FileHTTPRequestHandler, FileHTTPServer, run_server

__version__ = '0.1'

class PythonHTTPRequestHandler(FileHTTPRequestHandler):
    '''Extended SimpleHTTPRequestHandler with HTTP request header Range supported.'''

    server_version = 'PythonHTTP/' + __version__
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

    def do_POST(self):
        '''Handle a POST request.'''
        f = self.send_head()
        if not f:
            raise ValueError('Cannot POST to the file.')

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
            for index in 'index.html', 'index.htm', 'index.py':
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
        if ctype == 'text/x-python':
            self.run_script(path)
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

    def run_script(self, path):
        Loader = importlib.machinery.SourceFileLoader
        loader = Loader('mod', path)
        mod = loader.load_module()
        mod.handle(self)

    extensions_map = FileHTTPRequestHandler.extensions_map
    extensions_map.update({'.py': 'text/x-python'})


    pass

class PythonHTTPServer(FileHTTPServer):
    pass

def main():
    from sys import argv
    port = 8000
    for arg in argv[1:]:
        exec(arg)
    server_address = ('', port)
    with run_server(server_address, PythonHTTPServer, PythonHTTPRequestHandler) as server:
        server.content_dir = './content/'

if __name__ == '__main__':
    main()
    
