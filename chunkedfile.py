'''
Read and write chunked encoded data.

RFC 2616, section 3.6.1

Chunked-Body   = *chunk
                 last-chunk
                 trailer
                 CRLF

chunk          = chunk-size [ chunk-extension ] CRLF
                 chunk-data CRLF
chunk-size     = 1*HEX
last-chunk     = 1*("0") [ chunk-extension ] CRLF

chunk-extension= *( ";" chunk-ext-name [ "=" chunk-ext-val ] )
chunk-ext-name = token
chunk-ext-val  = token | quoted-string
chunk-data     = chunk-size(OCTET)
trailer        = *(entity-header CRLF)

>>> from io import BytesIO
>>> buf = BytesIO()
>>> writer = ChunkedWriter(buf, bufsize=10)
>>> writer.write(b'abcdefghijklmnopqrstuvwxyz')
26
>>> writer.write(b'ABCDE', flush=True)
5
>>> writer.end_file()
>>> writer.close()
>>> buf.seek(0)
0
>>> reader = ChunkedReader(buf)
>>> reader.read(26)
b'abcdefghijklmnopqrstuvwxyz'
>>> reader.read()
b'ABCDE'
>>> reader.eof
True
>>> reader.close()
'''

from io import BytesIO

class ChunkedWriter(object):
    def __init__(self, fileobj, bufsize=4096):
        self.fileobj = fileobj
        self.bufsize = bufsize
        self.buffer = BytesIO()
        self.closed = False
        self.ended = False

    def write(self, data, flush=False):
        if self.closed or self.ended:
            raise ValueError('Operation is not allowed.')
        if self.bufsize <= 0:
            self.write_chunk(data)
        else:
            self.buffer.write(data)
            if self.buffer.tell() >= self.bufsize or flush:
                self.flush()
        return len(data)

    def write_chunk(self, data):
        if self.closed or self.ended:
            raise ValueError('Operation is not allowed.')
        if not data:
            return
        # chunk-size
        self.fileobj.write('{:x}'.format(len(data)).encode(
            'latin-1', 'strict'))
        self.fileobj.write(b'\r\n')
        # chunk-data
        self.fileobj.write(data)
        self.fileobj.write(b'\r\n')

    def flush(self):
        if self.closed:
            raise ValueError('Operation is not allowed.')
        buffered = self.buffer.tell()
        if buffered == 0: return
        self.buffer.seek(0)
        data = self.buffer.read(buffered)
        self.write_chunk(data)
        self.buffer.seek(0)

    def end_file(self):
        if self.closed:
            raise ValueError('Operation is not allowed.')
        self.flush()
        # last-chunk
        self.fileobj.write(b'0\r\n')
        # end of Chunked-Body
        self.fileobj.write(b'\r\n')
        self.ended = True

    def close(self):
        if self.closed:
            return
        if not self.ended:
            self.end_file()
        delattr(self, 'fileobj')
        self.closed = True

class ChunkedReader(object):
    def __init__(self, fileobj):
        self.fileobj = fileobj
        self.buffer = BytesIO()
        self.eof = False
        self.closed = False

    def read(self, size=-1):
        if self.closed:
            raise ValueError('I/O operation on closed file.')
        if self.eof: return b''
        if size < 0:
            data = b''
            while not self.eof:
                data += self.read_chunk()
            return data
        data = self.buffer.read(size)
        if len(data) != size:
            self.buffer = BytesIO(self.read_chunk())
            data += self.buffer.read(size - len(data))
        return data

    def read_chunk(self):
        if self.closed:
            raise ValueError('I/O operation on closed file.')
        if self.eof:
            raise ValueError('File ended.')
        # chunk-size
        size = self.fileobj.readline().strip()
        size = int(size.decode(), 16)
        if size == 0:
            self.eof = True
            del self.fileobj
            return b''
        # chunk-data
        data = self.fileobj.read(size)
        if self.fileobj.read(2) != b'\r\n':
            raise ValueError('Excepting \\r\\n after data.')
        return data

    def close(self):
        self.closed = True

if __name__ == '__main__':
    import doctest
    doctest.testmod()

