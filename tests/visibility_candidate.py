"""Scoped main-thread native visibility prototype with the legacy fallback."""
import ctypes as C,inspect,textwrap,threading
from pathlib import Path
import numpy as np
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
_LIB=None
native_calls=0

def native_many(mesh_fn,points,normals,eye,direction,ortho,occlusion,lift,accelerated):
    global _LIB,native_calls
    if threading.current_thread() is not threading.main_thread():return None
    p=np.ascontiguousarray(points,dtype=np.float64).reshape(-1,3)
    n=np.ascontiguousarray(normals,dtype=np.float64).reshape(-1,3)
    e=np.ascontiguousarray(eye,dtype=np.float64).reshape(3)
    v=np.ascontiguousarray(direction,dtype=np.float64).reshape(3)
    if len(p)!=len(n) or not all(np.isfinite(a).all() for a in (p,n,e,v)):return None
    if _LIB is None:
        _LIB=C.PyDLL(str(Path(__file__).resolve().parents[1]/'bin'/cmds.about(version=True)/'aru_retopo_maya_visibility_candidate.dll'))
        d=C.POINTER(C.c_double)
        _LIB.aru_maya_visibility.argtypes=[C.c_char_p,d,d,C.c_int,d,d,C.c_int,C.c_int,C.c_double,C.c_int,C.POINTER(C.c_ubyte)]
        _LIB.aru_maya_visibility.restype=C.c_int
    out=np.empty(len(p),dtype=np.uint8);d=C.POINTER(C.c_double)
    if not _LIB.aru_maya_visibility(mesh_fn.fullPathName().encode('utf-8'),p.ctypes.data_as(d),n.ctypes.data_as(d),len(p),e.ctypes.data_as(d),v.ctypes.data_as(d),int(ortho),int(occlusion),lift,int(accelerated),out.ctypes.data_as(C.POINTER(C.c_ubyte))):return None
    native_calls+=1
    return out.astype(bool).tolist()

def install():
    original=edit.make_visibility_test
    source=textwrap.dedent(inspect.getsource(original))
    if 'from .maya_visibility import native_many' in source:raise RuntimeError('Already integrated; run visibility_release_cases.py instead.')
    old='        return [_visible(p,n) for p,n in zip(points,normals)]'
    assert old in source
    source=source.replace('from .maya_projector import surface_hits','from .maya_projector import normals_array')
    source=source.replace('normals=[hit[1] for hit in surface_hits(mesh_fn,points)]','normals=normals_array(mesh_fn,points)')
    source=source.replace(old,'''        from Aru_RetopoTool.tests.visibility_candidate import native_many
        result=native_many(mesh_fn,points,normals,eye,vdir,ortho,occlusion,lift,use_acceleration)
        if result is not None:return result
'''+old)
    scope={};exec(compile(source,'<native-visibility>','exec'),edit.__dict__,scope)
    edit.make_visibility_test=scope['make_visibility_test']
    def restore():edit.make_visibility_test=original
    return restore
