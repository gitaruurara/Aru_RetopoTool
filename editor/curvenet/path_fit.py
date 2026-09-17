"""Native pure numeric fit; Maya interaction remains with the caller."""
import ctypes as C
import sys
from pathlib import Path
_LIB=None
ENABLED=True

def fit(controls,path,normals,samples,rounds,fixed,eps_ratio,restore_min):
    global _LIB
    if not ENABLED or sys.platform!='win32':return None
    if _LIB is None:
        library_path=Path(__file__).resolve().parents[2]/'bin'/'aru_retopo_path_fit.dll'
        if not library_path.exists():return None
        lib=C.CDLL(str(library_path));d=C.POINTER(C.c_double)
        lib.aru_path_fit.argtypes=[d,d,C.c_int,d,C.c_int,C.c_int,C.c_int,C.c_double,C.c_double,d]
        lib.aru_path_fit.restype=C.c_int;_LIB=lib
    def pack(values):
        flat=[x for point in values for x in point];return (C.c_double*len(flat))(*flat)
    output=(C.c_double*7)()
    if not _LIB.aru_path_fit(pack(controls),pack(path),len(path),pack(normals),samples,rounds,fixed or 0,eps_ratio,restore_min,output):
        raise RuntimeError('Native path fitting failed')
    return list(output[:3]),list(output[3:6])
