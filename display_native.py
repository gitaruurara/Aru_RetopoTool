"""Batched native wire visibility, shared by all supported Maya versions."""
import ctypes as C
import os,sys
from .native import D,I,packed,ints,unpack
_lib=None

def library():
    global _lib
    if _lib is None:
        name='aru_retopo_display_v3.dll' if sys.platform=='win32' else ('libaru_retopo_display_v3.dylib' if sys.platform=='darwin' else 'libaru_retopo_display_v3.so')
        lib=C.CDLL(os.path.join(os.path.dirname(__file__),'bin',name))
        lib.aru_surface_create.argtypes=[D,C.c_int,I,C.c_int];lib.aru_surface_create.restype=C.c_void_p
        lib.aru_surface_destroy.argtypes=[C.c_void_p];lib.aru_surface_destroy.restype=None
        lib.aru_wire_visible.argtypes=[C.c_void_p,D,I,D,C.c_int,D,D,C.c_int,D]
        lib.aru_wire_visible.restype=C.c_int
        lib.aru_wire_visible_compact.argtypes=lib.aru_wire_visible.argtypes
        lib.aru_wire_visible_compact.restype=C.c_int
        lib.aru_wire_refit.argtypes=[C.c_void_p,D,I,C.c_int];lib.aru_wire_refit.restype=C.c_int
        _lib=lib
    return _lib

class Wire:
    def __init__(self,points,triangles,edges,normals):
        self.lib=library();self.points=packed(points);self.edges=ints([v for (a,b),faces in edges for v in (a,b,faces[0],faces[1] if len(faces)>1 else -1)])
        self.normals=packed(normals);self.count=len(edges)
        self.triangles=tuple(triangles);self.triangle_buffer=ints(triangles)
        self.output=(C.c_double*(self.count*24))()
        self.handle=self.lib.aru_surface_create(self.points,len(points),ints(triangles),len(triangles)//3)
        if not self.handle:raise ValueError('Cannot build wire visibility BVH')
    def update(self,points,normals):
        self.points=packed(points);self.normals=packed(normals)
        if not self.lib.aru_wire_refit(self.handle,self.points,self.triangle_buffer,len(self.triangles)//3):
            raise RuntimeError("Wire refit failed")

    def close(self):
        if getattr(self,'handle',None):self.lib.aru_surface_destroy(self.handle);self.handle=None
    def __del__(self):self.close()
    def visible(self,eye,direction,ortho,compact=False):
        fn=self.lib.aru_wire_visible_compact if compact else self.lib.aru_wire_visible
        n=fn(self.handle,self.points,self.edges,self.normals,self.count,packed([eye]),packed([direction]),int(ortho),self.output)
        if n<0:raise RuntimeError('Wire visibility failed')
        return unpack(self.output,count=n)
