import gzip
from http.server import BaseHTTPRequestHandler
from http import HTTPStatus
from chunkedfile import ChunkedWriter
from servers import ThreadingHTTPServer

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
        if not hasattr(self, 'using_gzip'):
            self.using_gzip = self.server.using_gzip
        if not hasattr(self, 'using_chunked'):
            self.using_chunked = False

        if 'Accept-Encoding' in self.headers and self.using_gzip:
            encodings = self.headers['Accept-Encoding'].split(',')
            encodings = [encoding.strip() for encoding in encodings]
            if 'gzip' in encodings:
                self.send_header('Content-Encoding', 'gzip')
                self.using_gzip = True
                if not hasattr(self, 'compress_level'):
                    self.compress_level = self.server.compress_level
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
            print('using chunked encoding.')

        super().end_headers()
        delattr(self, '_content_length')

    def just_end_headers(self):
        '''Just end headers, doing nothing else.'''
        if self._content_length:
            super().send_header('Content-Length', self._content_length)
        delattr(self, '_content_length')
        super().end_headers()

    def start_body(self):
        '''Create self.outfile, which replaces self.wfile'''
        self.outfile = self.wfile
        if self.using_chunked:
            self.outfile = self.chunked_file = ChunkedWriter(
                    self.outfile, -1)
            print('using chunked writer.')
        else:
            self.chunked_file = None
        if self.using_gzip:
            self.outfile = self.gzip_file = gzip.GzipFile(
                    fileobj=self.outfile, mode='wb',
                    compresslevel=self.compress_level)
        else:
            self.gzip_file = None

    def end_body(self):
        '''Do some clean up works.'''
        if self.gzip_file:
            self.gzip_file.flush()
            self.gzip_file.close()
        if self.chunked_file:
            self.chunked_file.end_file()
        self.gzip_file = self.chunked_file = None
        if hasattr(self, 'using_gzip'):
            delattr(self, 'using_gzip')
        if hasattr(self, 'using_chunked'):
            delattr(self, 'using_chunked')
        if hasattr(self, 'compress_level'):
            delattr(self, 'compress_level')
        if hasattr(self, 'outfile'):
            delattr(self, 'outfile')

    def send_error(self, code, message=None, explain=None):
        """Send and log an error reply.
        Arguments are
        * code:    an HTTP error code
                   3 digits
        * message: a simple optional 1 line reason phrase.
                   *( HTAB / SP / VCHAR / %x80-FF )
                   defaults to short entry matching the response code
        * explain: a detailed message defaults to the long entry
                   matching the response code.
        This sends an error response (so it must be called before any
        output has been generated), logs the error, and finally sends
        a piece of HTML explaining the error to the user.
        """
        from http.server import _quote_html
        try:
            shortmsg, longmsg = self.responses[code]
        except KeyError:
            shortmsg, longmsg = '???', '???'
        if message is None:
            message = shortmsg
        if explain is None:
            explain = longmsg
        self.log_error("code %d, message %s", code, message)
        # using _quote_html to prevent Cross Site Scripting attacks (see bug #1100201)
        content = (self.error_message_format %
                   {'code': code, 'message': _quote_html(message), 'explain': _quote_html(explain)})
        body = content.encode('UTF-8', 'replace')
        self.send_response(code, message)
        self.send_header("Content-Type", self.error_content_type)
        self.send_header('Connection', 'close')
        self.send_header('Content-Length', int(len(body)))
        self.just_end_headers()
        if (self.command != 'HEAD' and
                code >= 200 and
                code not in (
                    HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED)):
            self.wfile.write(body)

class MinHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.using_gzip = False
        self.compress_level = 9

