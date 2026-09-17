"""Bulk exact Maya pixel projection on the calling GUI thread."""
import ctypes as C
from pathlib import Path
import threading
import numpy as np
from maya import cmds
_LIB=None


def project(points, *, as_array=False):
    global _LIB
    if threading.current_thread() is not threading.main_thread():return None
    if cmds.about(batch=True):return None
    values=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    if not len(values):return (np.empty((0,2),dtype=np.int16),np.empty(0,dtype=bool)) if as_array else []
    if not np.isfinite(values).all():return None
    if _LIB is None:
        path=Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/'aru_retopo_maya_screen_segments.dll'
        try:
            _LIB=load_library(path)
        except (OSError,AttributeError):return None
    output=np.empty((len(values),2),dtype=np.int16)
    valid=np.empty(len(values),dtype=np.uint8)
    if not _LIB.aru_maya_screen_points(values.ctypes.data_as(C.POINTER(C.c_double)),len(values),output.ctypes.data_as(C.POINTER(C.c_short)),valid.ctypes.data_as(C.POINTER(C.c_ubyte))):return None
    if as_array:return output,valid.astype(bool)
    return [(int(p[0]),int(p[1])) if ok else None for p,ok in zip(output,valid)]


def segment_candidates(positions,curves,sx,sy,tolerance):
    """Optional fused native picker; legacy binaries retain the NumPy path."""
    if threading.current_thread() is not threading.main_thread() or cmds.about(batch=True):return None
    if _LIB is None or not hasattr(_LIB,'aru_maya_screen_segments'):return None
    values=np.ascontiguousarray(positions,dtype=np.float64).reshape(-1,3)
    controls=np.ascontiguousarray(curves,dtype=np.int32).reshape(-1,4)
    if not len(controls):return []
    if not np.isfinite(values).all():return None
    size=len(controls)*24
    indices=np.empty(size,dtype=np.int32);parameters=np.empty(size);distances=np.empty(size)
    d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
    fn=_LIB.aru_maya_screen_segments
    fn.argtypes=[d,C.c_int,i,C.c_int,C.c_double,C.c_double,C.c_double,i,d,d];fn.restype=C.c_int
    count=fn(values.ctypes.data_as(d),len(values),controls.ctypes.data_as(i),len(controls),sx,sy,tolerance,indices.ctypes.data_as(i),parameters.ctypes.data_as(d),distances.ctypes.data_as(d))
    if count<0:return None
    return zip(indices[:count].tolist(),parameters[:count].tolist(),distances[:count].tolist())


def radius_candidates(points,sx,sy,radius):
    """Cull outside the brush square before allocating Python pixel tuples.

    The final hypot and strict radius comparison match the scalar brush exactly.
    None requests the existing Maya/Python fallback (batch or missing DLL).
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


def load_library(path):
    lib=C.PyDLL(str(path))
    lib.aru_maya_screen_points.argtypes=[C.POINTER(C.c_double),C.c_int,C.POINTER(C.c_short),C.POINTER(C.c_ubyte)]
    lib.aru_maya_screen_points.restype=C.c_int
    return lib
