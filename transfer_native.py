"""Optional native endpoint correspondence with identical Python fallback."""
import ctypes as C
import sys
from array import array
from pathlib import Path
from .stencil_compiler import view
_LIB=None


def matches(old,new):
    global _LIB
    if sys.platform!='win32':return None
    if _LIB is None:
        path=Path(__file__).resolve().parent/'bin'/'aru_retopo_transfer_v1.dll'
        if not path.exists():return None
        lib=C.CDLL(str(path));d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
        lib.aru_match_spline_endpoints.argtypes=[d,C.c_int,i,C.c_int,d,C.c_int,i,C.c_int,i]
        lib.aru_match_spline_endpoints.restype=C.c_int
        _LIB=lib
    op=array('d',(v for p in old.positions for v in p));np=array('d',(v for p in new.positions for v in p))
    os=array('i',(v for sp in old.splines for v in sp));ns=array('i',(v for sp in new.splines for v in sp))
    if len(op)!=3*len(old.positions) or len(np)!=3*len(new.positions) or len(os)!=4*len(old.splines) or len(ns)!=4*len(new.splines):
        raise ValueError('Invalid endpoint correspondence dimensions')
    out=array('i',[0])*(2*len(new.splines))
    if not _LIB.aru_match_spline_endpoints(view(op),len(old.positions),view(os),len(old.splines),view(np),len(new.positions),view(ns),len(new.splines),view(out)):
        raise ValueError('Invalid endpoint correspondence data')
    return {i:((out[2*i],out[2*i+1]),) for i in range(len(new.splines)) if out[2*i]>=0}
