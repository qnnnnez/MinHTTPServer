class RangedFile(object):
    '''Subranged file object.
    >>> from io import BytesIO
    >>> buf = BytesIO(b'0123456789')
    >>> ranged = RangedFile(buf, 1, 5)
    >>> ranged.read(4)
    b'1234'
    >>> ranged.tell()
    4
    >>> ranged.read()
    b'5'
    >>> ranged = RangedFile(buf, 1)
    >>> ranged.fix_position()
    >>> buf.seek = None
    >>> ranged.read()
    b'123456789'
    >>> ranged.length
    9
    '''
    def __init__(self, fileobj, start=0, end=float('inf')):
        self.fileobj = fileobj
        self.start = start
        self.end = end
        self.position = 0

    def tell(self):
        return self.position

    def seek(self, position):
        self.fileobj.seek(min(self.start + position, self.end))
        self.position = self.fileobj.tell() - self.start
        return self.position

    def read(self, size=-1):
        self.fix_position()
        if size < 0:
            if self.end == float('inf'):
                data = self.fileobj.read()
                self.end = self.fileobj.tell()
                self.position = self.end - self.start
                return data
            else:
                length = self.end - self.position
        else:
            length = min(size, self.end - self.position)
        data = self.fileobj.read(length)
        self.position += length
        if length == 0:
            self.end = self.fileobj.tell()
            self.position = self.end - self.start
        return data

    def fix_position(self):
        if self.start + self.position != self.fileobj.tell():
            self.seek(self.position)

    @property
    def length(self):
        if self.end == float('inf'):
            return None
        return self.end - self.start

if __name__ == '__main__':
    import doctest
    doctest.testmod()

