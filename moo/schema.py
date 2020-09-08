#!/usr/bin/env python3

# it would be nice to use typing.NamedTuple but wanting a base type
# puts the kibosh on that.
class BaseType(object):
    name=None
    doc=""
    path=()

    def __init__(self, name=None, doc="", path=()):
        self.name=name
        self.doc=doc
        self.path=path

    def to_dict(self):
        return dict(name=self.name,
                    schema=self.schema,
                    path=self.path,
                    doc=self.doc)

    def __str__(self):
        return ".".join(self.path+[self.name])

    def __repr__(self):
        return '<%s "%s">' %(self.__class__.__name__, str(self))
    
    @property
    def schema(self):
        return self.__class__.__name__.lower()

class Boolean(BaseType):
    'A Boolean type'

class Number(BaseType):
    'A number type'
    dtype: "i4"

    def __init__(self, name=None, dtype='i4', doc="", path=()):
        super().__init__(name,doc,path)
        self.dtype = dtype

    def to_dict(self):
        d = super().to_dict()
        d.update(dtype=self.dtype)
        return d
    
class String(BaseType):
    'A string type'
    pattern = None
    format = None

    def __init__(self, name=None, pattern=None, format=None, doc="", path=()):
        super().__init__(name,doc,path)
        self.pattern=pattern
        self.format=format

    def to_dict(self):
        d = super().to_dict()
        d.update(pattern=self.pattern, format=self.format)
        return d

class Sequence(BaseType):
    'A sequence/array/vector type of one type'
    items = None

    def __init__(self, name=None, items=None, doc="", path=()):
        super().__init__(name,doc,path)
        self.items = str(items)

    @property
    def deps(self):
        return [self.items]

    def __repr__(self):
        return '<Sequence "%s" items:%s>' % (str(self), self.items)

    def to_dict(self):
        d = super().to_dict()
        d.update(items = self.items)
        return d

class Field(object):
    'A field is NOT a type'
    name = ""
    item = None
    default = None
    doc = ""

    def __init__(self, name=None, item=None, default=None, doc=""):
        self.name = name
        self.item = str(item)
        self.default = default
        self.doc = doc

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Field "%s" %s [%s]>' % (self.name, self.item, self.default)
    
class Record(BaseType):
    'A thing with fields like a struct or a class'
    fields = ()

    def __init__(self, name=None, fields=None, doc="", path=()):
        super().__init__(name, doc, path)
        self.fields = fields

    @property
    def deps(self):
        return [str(f.item) for f in self.fields]

    def to_dict(self):
        d = super().to_dict()
        d.update(fields=[dict(name=f.name, item=f.item) for f in self.fields])
        return d

    def __repr__(self):
        return '<Record "%s" fields:{%s}>' % (str(self),
                                              ", ".join([f.name for f in self.fields]))

    def __getattr__(self, key):
        for f in self.fields:
            if f.name == key:
                return f
        raise KeyError(f'no such field: {key}')

class Namespace(BaseType):

    def __init__(self, name=None, path=(), doc="", **parts):
        n = name.split(".")
        self.name = n.pop(-1)
        self.path = list(path) + n
        self.doc = doc
        self.parts = parts

    def __repr__(self):
        return '<Namespace "%s" parts:{%s}>' % (self, ", ".join(self.parts.keys()))

    def field(self, name, item, default="", doc=""):
        '''
        Make and return a field
        '''
        return Field(name, item, default, doc)

    def normalize(self, key):
        '''
        Normalize a key into this namespace.

        A key may be a sequence or a dot-deliminated string.  

        Result is a dot-delim string relative to this namespace.
        '''
        if not isinstance(key, str):
            key = '.'.join(key)
        prefix = str(self) + '.'
        if key.startswith(prefix):
            return key[len(prefix):]
        return key

    def __getitem__(self, key):
        key = self.normalize(key)        
        path = key.split(".")
        got = self.parts[path.pop(0)]
        if not path:
            return got
        return got['.'.join(path)] # sub-namespace
        

    def _make(self, cls, name, *args, **kwds):
        if not "path" in kwds:
            kwds["path"] = self.path+[self.name]
        ret = cls(name, *args, **kwds)
        self.parts[name] = ret
        return ret

    _known_types = {c.__name__.lower():c for c in [Boolean, Number, String, Record, Sequence, Namespace]}

    def __getattr__(self, key):
        try:
            C = self._known_types[key.lower()]
        except KeyError:
            pass
        else:
            return lambda name, *a, **k: self._make(C, name, *a, **k)

        return self.parts[key]

    def subnamespace(self, subpath):
        '''
        Create a subnamespace.
        '''
        subpath = self.normalize(subpath)
        subpath = subpath.split(".")
        if not subpath:
            return self
        first = subpath.pop(0)
        if first in self.parts:
            ns = self.parts[first]
        else:
            ns = Namespace(first, self.path + [self.name])
            self.parts[first] = ns
        for sp in subpath:
            ns = ns.namespace(sp)
        return ns

    def isin(self, typ):
        '''
        Return true if type is in this namespace or a subnamespace
        '''
        me = self.path + [self.name]
        n = len(typ.path)
        return n >= len(me) and typ.path == me[:n]

    def add(self, typ):
        '''
        Add type to ns
        '''
        if not self.isin(typ):
            raise ValueError("Not in %r: %r" % (self, typ))
        subpath = self.normalize(str(typ))
        ns = self.subnamespace(subpath)
        self.parts[typ.name] = typ
        return typ
        

    def types(self, recur=False):
        '''Return array of types in namespace.  

        Sub-namespaces are not considered types by themselves but if
        recur==True descend into any sub-namespaces and include their
        types.

        '''
        ret = []
        for n,t in self.parts.items():
            if "namespace" == t.schema():
                if recur:
                    ret += t.types(True)
            else:
                ret.append(t)
        return ret
        
    def to_dict(self):
        '''
        Return a dictionary representation of this namespace.
        '''
        d = dict(name=self.name, schema="namespace", path=self.path, doc=self.doc)
        for t in self.parts.values():
            d[t.name] = t.to_dict()
        return d

def from_dict(d):
    '''
    Return a schema object give a dictionary representation as made from .to_dict()
    '''
    d = dict(d)
    schema = d.pop("schema")
    deps = d.pop("deps",None)   # don't care
    name = d.pop("name")
    path = d.pop("path")

    if schema == "namespace":
        doc = d.pop("doc","")
        parts = dict()
        for n,p in d.items():   # rest of d is parts
            parts[n] = from_dict(p)
        return Namespace(name, path, doc, **parts)
    
    # otherwise make a namespace to hold the building of the type
    if path:
        nsname = path.pop(-1)
        ns = Namespace(nsname, path)
    else:
        ns = Namespace("")
    meth = getattr(ns, schema)
    if schema == "record":      # little help
        fields = [Field(**f) for f in d.pop("fields",[])]
        d["fields"] = fields
        
    return meth(name, **d)


def graph(types):
    '''
    Given a list of types, return an object which indexes each type by its fqn
    '''
    ret = dict()
    for t in types:
        path = '.'.join(t.path + [t.name])
        ret[path] = t
    return ret

def toposort(graph):
    '''
    Given a graph of types, return a toplogocal sort of nodes

    Graph is assumed to be an object such as returned by graph()

    https://en.wikipedia.org/wiki/Topological_sorting#Depth-first_search
    '''
    ret = list()
    marks = dict()
    nodes = list(graph.keys())

    def visit(node):
        mark = marks.get(node, None)
        if mark == "perm":
            return
        if mark == "temp":
            raise ValueError("type dependency graph is not a DAG")

        marks[node] = "temp"

        for dep in graph[node].deps:
            visit(dep)
        marks[node] = "perm"
        ret.append(node)

    while nodes:
        n = nodes.pop(0)
        visit(n)
        nodes = [n for n in nodes if n not in marks]

    return ret;
        
def test():

    top = Namespace("top")

    base = top.namespace("base")
    count = base.number("Count", "i4")

    email = base.string("Email", form="email")

    app = top.namespace("app.sub")
    counts = app.sequence("Counts", count)
    app.record("Person", [
        Field("email", email),
        Field("counts", counts)
        ])

    return top

def test2():

    ns = Namespace("foo.bar")
    n1 = ns.number("Count", "i4")
    f1 = ns.field("X",n1)
    f2 = ns.field("L",ns.sequence("LL",n1))
    ns.record("Myobj", [f1,f2])
    ns.to_dict()
    ns2 = ns.namespace("baz")
    ns2.boolean("TF")
    return ns
