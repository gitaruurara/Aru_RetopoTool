"""Bulk position-only projection using the same Maya MMeshIntersector algorithm.

Python entry points run on the interactive main thread. Native route fitting and bulk point projection
use up to four workers for immutable, thread-safe intersector queries.
The owning _MeshAccel supplies dirty invalidation and DAG instance identity.
"""
import ctypes as C
from pathlib import Path
import numpy as np
from maya import cmds
_LIB=None

def library():
    global _LIB
    if _LIB is None:
        path=Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/'aru_retopo_maya_projector_tangents.dll'
        _LIB=_load_library(path)
    return _LIB

def _load_library(path):
    lib=C.CDLL(str(path))
    lib.aru_maya_projector_create.argtypes=[C.c_char_p];lib.aru_maya_projector_create.restype=C.c_void_p
    lib.aru_maya_projector_destroy.argtypes=[C.c_void_p];lib.aru_maya_projector_destroy.restype=None
    lib.aru_maya_projector_points.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_int,C.POINTER(C.c_double)]
    lib.aru_maya_projector_points.restype=C.c_int
    d=C.POINTER(C.c_double)
    lib.aru_maya_fit_routes.argtypes=[C.c_void_p,d,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_double,C.c_double,C.c_double,d]
    lib.aru_maya_fit_routes.restype=C.c_int
    lib.aru_maya_surface_hits.argtypes=[C.c_void_p,d,C.c_int,d,C.POINTER(C.c_int)]
    lib.aru_maya_surface_hits.restype=C.c_int
    if hasattr(lib,'aru_maya_normals'):
        lib.aru_maya_normals.argtypes=[C.c_void_p,d,C.c_int,d]
        lib.aru_maya_normals.restype=C.c_int
    if hasattr(lib,'aru_maya_junction_lengths'):
        lib.aru_maya_junction_lengths.argtypes=[C.c_void_p,d,d,d,d,d,d,C.c_int,d]
        lib.aru_maya_junction_lengths.restype=C.c_int
    if hasattr(lib,'aru_maya_fit_routes_bound'):
        lib.aru_maya_fit_routes_bound.argtypes=[C.c_void_p,d,C.c_int,C.c_int,C.c_int,C.c_int,C.c_int,C.c_double,C.c_double,C.c_double,d,d,C.POINTER(C.c_int)]
        lib.aru_maya_fit_routes_bound.restype=C.c_int
    if hasattr(lib,'aru_maya_junction_directions'):
        lib.aru_maya_junction_directions.argtypes=[d,d,d,C.c_double,C.POINTER(C.c_int),d,C.c_int,C.c_int,C.POINTER(C.c_int),d]
        lib.aru_maya_junction_directions.restype=C.c_int
    return lib

class Projector:
    def __init__(self,path):
        self.lib=library();self.handle=self.lib.aru_maya_projector_create(path.encode('utf-8'))
        if not self.handle:raise RuntimeError('Cannot build Maya projection accelerator')
    def close(self):
        if getattr(self,'handle',None):
            self.lib.aru_maya_projector_destroy(self.handle);self.handle=None
    def __del__(self):self.close()
    def points(self,points,*,as_array=False):
        values=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
        output=np.empty_like(values)
        if not self.lib.aru_maya_projector_points(self.handle,values.ctypes.data_as(C.POINTER(C.c_double)),len(values),output.ctypes.data_as(C.POINTER(C.c_double))):
            raise RuntimeError('Maya batch projection failed')
        return output if as_array else output.tolist()

_CACHE={}

def clear(mesh_name=None):
    names=list(_CACHE) if mesh_name is None else [mesh_name]
    for name in names:
        cached=_CACHE.pop(name,None)
        if cached:cached[1].close()

def get_projector(mesh_fn):
    from . import curve_net_edit as edit
    # Existing Maya dirty callbacks invalidate the owner on geometry/transform edits.
    for name,(owner,projector) in list(_CACHE.items()):
        if not owner.alive():projector.close();del _CACHE[name]
    owner=edit._accel_for(mesh_fn)
    if owner is None:return None
    name=mesh_fn.fullPathName()
    cached=_CACHE.get(name)
    if cached is None or cached[0] is not owner:
        if cached:cached[1].close();del _CACHE[name]
        try:projector=Projector(name)
        except (OSError,RuntimeError):
            return None
        _CACHE[name]=(owner,projector)
    return _CACHE[name][1]

def points(mesh_fn,queries):
    projector=get_projector(mesh_fn)
    if projector is None:
        from . import curve_net_edit as edit
        return [edit._closest_point_pos_only(mesh_fn,p) for p in queries]
    return projector.points(queries)

def points_array(mesh_fn,queries):
    """Return an owned contiguous float64 buffer for numeric consumers."""
    projector=get_projector(mesh_fn)
    if projector is None:
        from . import curve_net_edit as edit
        return np.asarray([edit._closest_point_pos_only(mesh_fn,p) for p in queries],dtype=np.float64).reshape(-1,3)
    return projector.points(queries,as_array=True)


def fit_routes(mesh_fn,controls,draft=True):
    from . import curve_net_context as context
    projector=get_projector(mesh_fn)
    if projector is None:return None
    values=np.ascontiguousarray(controls,dtype=np.float64).reshape(-1,12)
    output=np.empty((len(values),6),dtype=np.float64)
    d=C.POINTER(C.c_double)
    iterations=context._FIT_DRAFT_ITERS if draft else context._FIT_ITERS
    segments=context._GEO_DRAFT_SEGMENTS if iterations<=context._FIT_DRAFT_ITERS else context._GEO_SEGMENTS
    samples=context._FIT_DRAFT_SAMPLES if draft else context._FIT_SAMPLES
    if not projector.lib.aru_maya_fit_routes(projector.handle,values.ctypes.data_as(d),len(values),segments,iterations,samples,context._FIT_PARAM_ROUNDS,context._GEO_RELAX,context._FIT_EPS_RATIO,context._TANGENT_RESTORE_MIN,output.ctypes.data_as(d)):
        raise RuntimeError('Batch route fitting failed')
    return output.reshape(-1,2,3).tolist()

def surface_hits(mesh_fn,queries):
    if len(queries)==0:return []
    projector=get_projector(mesh_fn)
    if projector is None:
        from . import curve_net_edit as edit
        fn,dag=edit._get_mesh_fn(mesh_fn.fullPathName())
        result=[]
        for query in queries:
            position,face,bary=edit._closest_point_on_mesh(fn,dag,query)
            result.append((position,edit._get_normal_at_point(fn,query),face,bary))
        return result
    output,metadata=_surface_buffers(projector,queries)
    return [(row[:3].tolist(),row[3:6].tolist(),int(meta[0]),[(int(meta[i+1]),float(row[i+6])) for i in range(meta[4])]) for row,meta in zip(output,metadata)]


def _surface_buffers(projector,queries):
    values=np.ascontiguousarray(queries,dtype=np.float64).reshape(-1,3)
    output=np.empty((len(values),9),dtype=np.float64);metadata=np.empty((len(values),5),dtype=np.int32)
    d=C.POINTER(C.c_double)
    if not projector.lib.aru_maya_surface_hits(projector.handle,values.ctypes.data_as(d),len(values),output.ctypes.data_as(d),metadata.ctypes.data_as(C.POINTER(C.c_int))):
        raise RuntimeError('Batch surface metadata failed')
    return output,metadata


def normals_array(mesh_fn,queries):
    """Read the same native normals without constructing unused binding lists."""
    if len(queries)==0:return np.empty((0,3),dtype=np.float64)
    projector=get_projector(mesh_fn)
    if projector is None:
        from . import curve_net_edit as edit
        fn,_dag=edit._get_mesh_fn(mesh_fn.fullPathName())
        return np.asarray([edit._get_normal_at_point(fn,query) for query in queries],dtype=np.float64).reshape(-1,3)
    if hasattr(projector.lib,'aru_maya_normals'):
        values=np.ascontiguousarray(queries,dtype=np.float64).reshape(-1,3)
        output=np.empty_like(values)
        d=C.POINTER(C.c_double)
        if not projector.lib.aru_maya_normals(projector.handle,values.ctypes.data_as(d),len(values),output.ctypes.data_as(d)):
            raise RuntimeError('Batch surface normals failed')
        return output
    output,_metadata=_surface_buffers(projector,queries)
    return np.ascontiguousarray(output[:,3:6])


def junction_lengths(mesh_fn, bases, directions, lengths, chords, coefficients, inverses):
    """Return fused native fit lengths, or None for older projection libraries."""
    projector = get_projector(mesh_fn)
    if projector is None or not hasattr(projector.lib, 'aru_maya_junction_lengths'):
        return None
    arrays = [np.ascontiguousarray(a, dtype=np.float64) for a in
              (bases, directions, lengths, chords, coefficients, inverses)]
    count = len(lengths)
    sizes = (count*45, count*6, count*2, count, 30, count*94)
    if any(a.size != size for a, size in zip(arrays, sizes)):
        raise ValueError('Invalid junction length buffer size')
    result = np.empty((count, 2), dtype=np.float64)
    d = C.POINTER(C.c_double)
    if not projector.lib.aru_maya_junction_lengths(projector.handle,
            *(a.ctypes.data_as(d) for a in arrays), count, result.ctypes.data_as(d)):
        raise RuntimeError('Native junction length fitting failed')
    return result


def fit_routes_bound(mesh_fn,controls,draft=True):
    """Fit handles and return bindings in one batch; None on older DLLs."""
    from . import curve_net_context as context
    projector=get_projector(mesh_fn)
    if projector is None or not hasattr(projector.lib,'aru_maya_fit_routes_bound'):return None
    function=projector.lib.aru_maya_fit_routes_bound
    d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
    values=np.ascontiguousarray(controls,dtype=np.float64).reshape(-1,12)
    count=len(values)
    output=np.empty((count,2,3),dtype=np.float64)
    hits=np.empty((count*2,9),dtype=np.float64);metadata=np.empty((count*2,5),dtype=np.int32)
    iterations=context._FIT_DRAFT_ITERS if draft else context._FIT_ITERS
    segments=context._GEO_DRAFT_SEGMENTS if iterations<=context._FIT_DRAFT_ITERS else context._GEO_SEGMENTS
    samples=context._FIT_DRAFT_SAMPLES if draft else context._FIT_SAMPLES
    if not function(projector.handle,values.ctypes.data_as(d),count,segments,iterations,samples,context._FIT_PARAM_ROUNDS,context._GEO_RELAX,context._FIT_EPS_RATIO,context._TANGENT_RESTORE_MIN,output.ctypes.data_as(d),hits.ctypes.data_as(d),metadata.ctypes.data_as(i)):
        raise RuntimeError('Bound route fitting failed')
    bindings=[(int(meta[0]),[(int(meta[k+1]),float(row[k+6])) for k in range(meta[4])]) for row,meta in zip(hits,metadata)]
    return output.tolist(),bindings



def junction_directions(mesh_fn, points, normals, weights, amount, offsets, branches):
    """Pair branches and blend tangents; None retains the legacy Python solver."""
    projector=get_projector(mesh_fn)
    if projector is None or not hasattr(projector.lib,'aru_maya_junction_directions'):return None
    points=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    normals=np.ascontiguousarray(normals,dtype=np.float64).reshape(-1,3)
    weights=np.ascontiguousarray(weights,dtype=np.float64).reshape(-1)
    offsets=np.ascontiguousarray(offsets,dtype=np.int32).reshape(-1)
    branches=np.ascontiguousarray(branches,dtype=np.float64).reshape(-1,6)
    if len(normals)!=len(points) or len(weights)!=len(points) or len(offsets)!=len(points)+1:
        raise ValueError('Invalid junction direction buffer size')
    selected=np.empty(len(branches),dtype=np.int32)
    directions=np.empty((len(branches),3),dtype=np.float64)
    d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
    count=projector.lib.aru_maya_junction_directions(
        points.ctypes.data_as(d),normals.ctypes.data_as(d),weights.ctypes.data_as(d),amount,
        offsets.ctypes.data_as(i),branches.ctypes.data_as(d),len(points),len(branches),
        selected.ctypes.data_as(i),directions.ctypes.data_as(d))
    if count<0 or count>len(branches):raise RuntimeError('Native junction directions failed')
    return selected[:count],directions[:count]
