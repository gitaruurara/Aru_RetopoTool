"""Owned batch visibility output; scene ray calls stay on the main thread.

PyDLL retains the GIL while Maya's intersection API reads the scene.
"""
import ctypes as C
from pathlib import Path
import threading
import numpy as np
from maya import cmds
BINARY_NAME='aru_retopo_maya_visibility.dll'
_LIB=None


def library():
    global _LIB
    if _LIB is None:
        path=Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/BINARY_NAME
        try:
            lib=C.PyDLL(str(path))
        except OSError as exc:
            raise RuntimeError('Aru Retopo visibility DLL could not be loaded: '+str(path)+'. Reinstall the matching Maya binaries and restart Maya.') from exc
        if not hasattr(lib,'aru_maya_visibility'):
            raise RuntimeError('Aru Retopo visibility ABI mismatch: '+str(path))
        d=C.POINTER(C.c_double)
        lib.aru_maya_visibility.argtypes=[C.c_char_p,d,d,C.c_int,d,d,C.c_int,C.c_int,C.c_double,C.c_int,C.POINTER(C.c_ubyte)]
        lib.aru_maya_visibility.restype=C.c_int
        _LIB=lib
    return _LIB


def native_many(mesh_fn,points,normals,eye,direction,ortho,occlusion,lift,accelerated):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Maya visibility queries require the main thread')
    p=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    n=np.ascontiguousarray(normals,dtype=np.float64).reshape(-1,3)
    e=np.ascontiguousarray(eye,dtype=np.float64).reshape(3)
    v=np.ascontiguousarray(direction,dtype=np.float64).reshape(3)
    if len(p)!=len(n) or not all(np.isfinite(a).all() for a in (p,n,e,v)) or not np.isfinite(lift):
        raise ValueError('Visibility requires matching points/normals and finite inputs')
    if not len(p):return []
    lib=library()
    out=np.empty(len(p),dtype=np.uint8);d=C.POINTER(C.c_double)
    if not lib.aru_maya_visibility(mesh_fn.fullPathName().encode('utf-8'),p.ctypes.data_as(d),n.ctypes.data_as(d),len(p),e.ctypes.data_as(d),v.ctypes.data_as(d),int(ortho),int(occlusion),lift,int(accelerated),out.ctypes.data_as(C.POINTER(C.c_ubyte))):
        raise RuntimeError('Maya batch visibility query failed')
    return out.astype(bool).tolist()
