class FileString(object):
    """Bare-bones pseudo-file class"""
    def __init__(self, str=""):
        object.__init__(self)
        self.str = str

    def __iter__(self):
        for line in self.str.splitlines(True):
            yield line

    def write(self, line):
        self.str += line


def parse(f):
    """Parses a mapfile, returns a Dictionary

    >>> f = FileString("1:q\\n2:q\\n3:q\\n>p\\n4:q\\n5:q\\n6:q\\n")
    >>> parse(f)["q"]
    'p'
    >>> parse("1:q\\n2:q\\n3:q\\n>r\\n4:q\\n5:q\\n6:q\\n")["q"]
    'r'
    >>> parse("1:q:5\\n>s\\n2:q:5\\n")["q:5"]
    's'
    >>> parse("1:q\\n>s\\n2:q\\n1:q\\n>s\\n2:q\\n")
    Traceback (most recent call last):
      File "<stdin>", line 1, in ?
      File "libbe/mapfile.py", line 41, in parse
        assert (lnum == prev_num + 1)
    AssertionError
    >>> parse("1:q\\n>s\\n2:q\\n1:l\\n>s\\n2:l\\n1:q\\n>s\\n2:q\\n")
    Traceback (most recent call last):
    AssertionError
    >>> parse("1:q\\n>s\\n>s\\n2:q\\n")
    Traceback (most recent call last):
    AssertionError
    """
    if isinstance(f, basestring):
        f = FileString(f)
    result = {}
    name = None
    prev_num = None
    for line in f:
        value = None
        # Handle values
        if line.startswith(">"):
            assert (name is not None)
            assert (not result.has_key(name))
            result[name] = line[1:].rstrip("\n")
        # Handle names
        else:
            lname = ":".join(line.split(":")[1:]).rstrip("\n")
            lnum = int(line.split(":")[0])

            #special-case the first execution
            if name is None:
                name = lname 

            #ensure sequential operation
            elif lname == name:
                assert (lnum == prev_num + 1)
            #if name changes, start over at 1
            else:
                if lnum != 1:
                    assert(lname != name)
                    raise "%i %s %s" % (lnum, lname, name)
                assert (lnum == 1)
                name = lname
            prev_num = lnum
    return result
 

def generate(f, map, context=3):
    """
    >>> f = FileString()
    >>> generate(f, {"q":"p"})
    >>> f.str
    '1:q\\n2:q\\n3:q\\n>p\\n4:q\\n5:q\\n6:q\\n'
    >>> parse(f)["q"]
    'p'
    >>> f = FileString()
    >>> generate(f, {"a":"b", "c":"d", "e":"f"})
    >>> dict = parse(f)
    >>> dict["a"]
    'b'
    >>> dict["c"]
    'd'
    >>> dict["e"]
    'f'
    """
    assert(context > 0)
    keys = map.keys()
    keys.sort()
    for key in keys:
        for i in range(context):
            f.write("%i:%s\n" % (i+1, key))
        f.write(">%s\n" % map[key])
        for i in range(context):
            f.write("%i:%s\n" % (i+context+1, key))

class IllegalKey(Exception):
    def __init__(self, key):
        Exception.__init__(self, 'Illegal key "%s"' % key)
        self.key = key

class IllegalValue(Exception):
    def __init__(self, value):
        Exception.__init__(self, 'Illegal value "%s"' % value)
        self.value = value 

def generate2(f, map, context=3):
    """Generate a format-2 mapfile.  This is a simpler format, but should merge
    better, because there's no chance of confusion for appends, and lines
    are unique for both key and value.

    >>> f = FileString()
    >>> generate2(f, {"q":"p"})
    >>> f.str
    '\\n\\n\\nq=p\\n\\n\\n\\n'
    >>> generate2(f, {"q=":"p"})
    Traceback (most recent call last):
    IllegalKey: Illegal key "q="
    >>> generate2(f, {"q\\n":"p"})
    Traceback (most recent call last):
    IllegalKey: Illegal key "q\\n"
    >>> generate2(f, {"":"p"})
    Traceback (most recent call last):
    IllegalKey: Illegal key ""
    >>> generate2(f, {">q":"p"})
    Traceback (most recent call last):
    IllegalKey: Illegal key ""
    >>> generate2(f, {"q":"p\\n"})
    Traceback (most recent call last):
    IllegalValue: Illegal value "p\\n"
    """
    assert(context > 0)
    keys = map.keys()
    keys.sort()
    for key in keys:
        try:
            assert not key.startswith('>')
            assert('\n' not in key)
            assert('=' not in key)
            assert(len(key) > 0)
        except AssertionError:
            raise IllegalKey(key.encode('string_escape'))
        if "\n" in map[key]:
            raise IllegalValue(map[key].encode('string_escape'))

    for key in keys:
        for i in range(context):
            f.write("\n")
        f.write("%s=%s\n" % (key, map[key]))
        for i in range(context):
            f.write("\n")

def parse2(f):
    """
    Parse a format-2 mapfile.
    >>> parse2('\\n\\n\\nq=p\\n\\n\\n\\n')['q']
    'p'
    >>> parse2('\\n\\nq=\\'p\\'\\n\\n\\n\\n')['q']
    "\'p\'"
    >>> f = FileString()
    >>> generate2(f, {"a":"b", "c":"d", "e":"f"})
    >>> dict = parse2(f)
    >>> dict["a"]
    'b'
    >>> dict["c"]
    'd'
    >>> dict["e"]
    'f'
    """
    if isinstance(f, basestring):
        f = FileString(f)
    result = {}
    for line in f:
        line = line.rstrip('\n')
        if len(line) == 0:
            continue
        name,value = line.split('=', 1)
        assert not result.has_key('name')
        result[name] = value
    return result
