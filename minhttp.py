import gzip
from http.server import BaseHTTPRequestHandler
from http import HTTPStatus
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


