"""Bulk exact Maya pixel projection on the calling GUI thread."""
import ctypes as C
from pathlib import Path
import threading
import numpy as np
from maya import cmds
BINARY_NAME='aru_retopo_maya_screen_segments.dll'
_LIB=None


def project(points, *, as_array=False):
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Maya screen queries require the main thread')
    if cmds.about(batch=True):return None
    values=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    if not len(values):return (np.empty((0,2),dtype=np.int16),np.empty(0,dtype=bool)) if as_array else []
    if not np.isfinite(values).all():raise ValueError('Screen queries require finite positions')
    lib=library()
    output=np.empty((len(values),2),dtype=np.int16)
    valid=np.empty(len(values),dtype=np.uint8)
    if not lib.aru_maya_screen_points(values.ctypes.data_as(C.POINTER(C.c_double)),len(values),output.ctypes.data_as(C.POINTER(C.c_short)),valid.ctypes.data_as(C.POINTER(C.c_ubyte))):raise RuntimeError('Maya screen projection failed')
    if as_array:return output,valid.astype(bool)
    return [(int(p[0]),int(p[1])) if ok else None for p,ok in zip(output,valid)]


def segment_candidates(positions,curves,sx,sy,tolerance):
    """Fused native picker; None is reserved for viewport-free batch execution."""
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Maya screen queries require the main thread')
    if cmds.about(batch=True):return None
    values=np.ascontiguousarray(positions,dtype=np.float64).reshape(-1,3)
    controls=np.ascontiguousarray(curves,dtype=np.int32).reshape(-1,4)
    if not len(controls):return []
    if not np.isfinite(values).all():raise ValueError('Screen queries require finite positions')
    size=len(controls)*24
    indices=np.empty(size,dtype=np.int32);parameters=np.empty(size);distances=np.empty(size)
    d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
    fn=library().aru_maya_screen_segments
    count=fn(values.ctypes.data_as(d),len(values),controls.ctypes.data_as(i),len(controls),sx,sy,tolerance,indices.ctypes.data_as(i),parameters.ctypes.data_as(d),distances.ctypes.data_as(d))
    if count<0:raise RuntimeError('Maya curve picking failed')
    return zip(indices[:count].tolist(),parameters[:count].tolist(),distances[:count].tolist())


def radius_candidates(points,sx,sy,radius):
    """Cull outside the brush square before allocating Python pixel tuples.

    The final hypot and strict radius comparison match the scalar brush exactly.
    None requests the viewport-free batch path.
    """
    import math
    projected=project(points,as_array=True)
    if projected is None:return None
    screens,valid=projected
    pixels=screens.astype(np.float64)
    mask=valid & (np.abs(pixels[:,0]-sx)<radius) & (np.abs(pixels[:,1]-sy)<radius)
    result=[]
    for index in np.flatnonzero(mask).tolist():
        distance=math.hypot(int(screens[index,0])-sx,int(screens[index,1])-sy)
        if distance<radius:result.append((index,distance))
    return result


def library():
    global _LIB
    if _LIB is None:
        _LIB=load_library(Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/BINARY_NAME)
    return _LIB


def load_library(path):
    try:lib=C.PyDLL(str(path))
    except OSError as exc:
        raise RuntimeError('Aru Retopo screen DLL could not be loaded: '+str(path)+'. Reinstall the matching Maya binaries and restart Maya.') from exc
    required=('aru_maya_screen_points','aru_maya_screen_segments')
    missing=[name for name in required if not hasattr(lib,name)]
    if missing:raise RuntimeError('Aru Retopo screen ABI mismatch: '+str(path)+'; missing '+', '.join(missing))
    d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
    lib.aru_maya_screen_points.argtypes=[d,C.c_int,C.POINTER(C.c_short),C.POINTER(C.c_ubyte)]
    lib.aru_maya_screen_points.restype=C.c_int
    lib.aru_maya_screen_segments.argtypes=[d,C.c_int,i,C.c_int,C.c_double,C.c_double,C.c_double,i,d,d]
    lib.aru_maya_screen_segments.restype=C.c_int
    return lib
