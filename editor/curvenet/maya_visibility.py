"""Owned batch visibility output; scene ray calls stay on the main thread.

None asks the caller to use the original per-point Maya/Python implementation.
PyDLL retains the GIL, matching those existing main-thread API calls.
"""
import ctypes as C
from pathlib import Path
import threading
import numpy as np
from maya import cmds
_LIB=None

def native_many(mesh_fn,points,normals,eye,direction,ortho,occlusion,lift,accelerated):
    global _LIB
    if threading.current_thread() is not threading.main_thread():return None
    p=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    n=np.ascontiguousarray(normals,dtype=np.float64).reshape(-1,3)
    e=np.ascontiguousarray(eye,dtype=np.float64).reshape(3)
    v=np.ascontiguousarray(direction,dtype=np.float64).reshape(3)
    if len(p)!=len(n) or not all(np.isfinite(a).all() for a in (p,n,e,v)):return None
    if _LIB is None:
        try:
            _LIB=C.PyDLL(str(Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/'aru_retopo_maya_visibility.dll'))
        except OSError:return None
        d=C.POINTER(C.c_double)
        _LIB.aru_maya_visibility.argtypes=[C.c_char_p,d,d,C.c_int,d,d,C.c_int,C.c_int,C.c_double,C.c_int,C.POINTER(C.c_ubyte)]
        _LIB.aru_maya_visibility.restype=C.c_int
    out=np.empty(len(p),dtype=np.uint8);d=C.POINTER(C.c_double)
    if not _LIB.aru_maya_visibility(mesh_fn.fullPathName().encode('utf-8'),p.ctypes.data_as(d),n.ctypes.data_as(d),len(p),e.ctypes.data_as(d),v.ctypes.data_as(d),int(ortho),int(occlusion),lift,int(accelerated),out.ctypes.data_as(C.POINTER(C.c_ubyte))):return None
    return out.astype(bool).tolist()
