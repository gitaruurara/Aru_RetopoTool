"""Small ctypes bridge; shared library is independent of Maya/Python versions."""
import ctypes as C
import os
import sys
import struct

_lib = None
D = C.POINTER(C.c_double)
I = C.POINTER(C.c_int)


def library():
    global _lib
    if _lib is None:
        filename = 'aru_retopo_core_v5.dll' if sys.platform == 'win32' else ('libaru_retopo_core_v5.dylib' if sys.platform == 'darwin' else 'libaru_retopo_core_v5.so')
        path = os.path.join(os.path.dirname(__file__), 'bin', filename)
        # Standalone ABI: no Maya commands during DG evaluation on worker threads.
        if not os.path.isfile(path):
            raise RuntimeError('C++ライブラリがありません。Aru_RetopoTool/cpp のビルド手順を実行してください。')
        lib = C.CDLL(path)
        lib.aru_retopo_version.restype = C.c_int
        if lib.aru_retopo_version() != 5: raise RuntimeError('Retopo C++ ABI mismatch')
        lib.aru_surface_create.argtypes = [D, C.c_int, I, C.c_int]
        lib.aru_surface_create.restype = C.c_void_p
        lib.aru_surface_destroy.argtypes = [C.c_void_p]
        lib.aru_surface_destroy.restype = None
        lib.aru_project.argtypes = [C.c_void_p, D, C.c_int, D, I, D, C.c_int]
        lib.aru_stencil.argtypes = [D, I, I, D, C.c_int, D]
        lib.aru_relax.argtypes = [C.c_void_p, D, C.c_int, I, I, D, C.c_int, C.c_double, I, C.c_int]
        from .stencil_compiler import configure
        configure(lib)
        _lib = lib
    return _lib


def doubles(values): return (C.c_double*len(values))(*values)
def ints(values):
    if isinstance(values,C.Array) and values._type_ is C.c_int:
        # Copy in native memory; subsequent projection must not mutate its input.
        return type(values).from_buffer_copy(values)
    return (C.c_int*len(values))(*values)
def packed(points): return doubles([x for p in points for x in p])
def unpack(values, count=None):
    """Copy triples directly from the native buffer without per-point slicing."""
    try:
        view=memoryview(values).cast('B')
    except TypeError:
        end=len(values) if count is None else count*3
        return [tuple(values[i:i+3]) for i in range(0,end,3)]
    if count is not None:view=view[:count*24]
    return list(struct.iter_unpack('=ddd',view))


class PackedPoints:
    """Owned native point array; keep stencil-to-relax transfer in native memory."""
    def __init__(self, values): self.values=values
    def __len__(self): return len(self.values)//3
    def __iter__(self):
        for i in range(0,len(self.values),3): yield tuple(self.values[i:i+3])
    def __getitem__(self,index):
        if isinstance(index,slice): return list(self)[index]
        if index<0:index+=len(self)
        if index<0 or index>=len(self):raise IndexError(index)
        return tuple(self.values[index*3:index*3+3])


def stencil(points, offsets, indices, weights):
    out = (C.c_double*((len(offsets)-1)*3))()
    library().aru_stencil(packed(points), ints(offsets), ints(indices), doubles(weights), len(offsets)-1, out)
    return unpack(out)


class CompiledStencil:
    def __init__(self,offsets,indices,weights):
        self.offsets=ints(offsets);self.indices=ints(indices);self.weights=doubles(weights)
        self.count=len(offsets)-1;self.output=(C.c_double*(self.count*3))()
    def __call__(self,points):
        output=(C.c_double*(self.count*3))()
        library().aru_stencil(packed(points),self.offsets,self.indices,self.weights,self.count,output)
        return PackedPoints(output)

stencil.compile=CompiledStencil


class Surface:
    def __init__(self, points, triangles):
        self.lib = library()
        if len(triangles)%3: raise ValueError('Triangle indices must be triples')
        self.handle = self.lib.aru_surface_create(packed(points), len(points), ints(triangles), len(triangles)//3)
        if not self.handle: raise ValueError('参照メッシュに有効な三角形がありません。')

    def close(self):
        if getattr(self, 'handle', None):
            self.lib.aru_surface_destroy(self.handle); self.handle = None

    def __del__(self): self.close()

    def project(self, points, seeds=None, guard=True):
        n = len(points)
        if seeds is not None and len(seeds) != n: raise ValueError('Seed size mismatch')
        seed_array = ints(seeds if seeds is not None else [-1]*n)
        out, normals = (C.c_double*(n*3))(), (C.c_double*(n*3))()
        if not self.lib.aru_project(self.handle, packed(points), n, out, seed_array, normals, int(guard)):
            raise RuntimeError('Projection failed')
        return unpack(out), list(seed_array), unpack(normals)

    def relax(self, points, plan, iterations=3, strength=.35, guide_weight=1., seeds=None, guard=True, native_seeds=False):
        n = len(points)
        if n != plan.count: raise ValueError('Point count differs from topology plan')
        if seeds is not None and len(seeds) != n: raise ValueError('Seed size mismatch')
        if isinstance(points,PackedPoints):
            data=(C.c_double*(n*3))()
            C.memmove(data,points.values,C.sizeof(data))
        else:data = packed(points)
        seed_array = ints(seeds if seeds is not None else [-1]*n)
        if getattr(self,'_plan',None) is not plan:
            self._plan=plan
            self._offsets=ints(plan.adj_offsets);self._neighbors=ints(plan.adj_ids)
            self._weight_value=None
        if self._weight_value!=guide_weight:
            self._weights=doubles([guide_weight if i in plan.guide_vertices else 0. for i in range(n)])
            self._weight_value=guide_weight
        if not self.lib.aru_relax(self.handle, data, n, self._offsets, self._neighbors, self._weights,
                                  iterations, strength, seed_array, int(guard)):
            raise RuntimeError('Surface relaxation failed')
        return unpack(data), seed_array if native_seeds else list(seed_array)
