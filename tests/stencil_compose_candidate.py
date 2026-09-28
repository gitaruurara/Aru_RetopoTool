import ctypes as C
from array import array
from pathlib import Path
_LIB=None
I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).resolve().parents[1]/'bin/aru_retopo_compose_candidate.dll'))
  lib.aru_compose_rows.argtypes=[I,C.c_int,I,D,C.c_int,I,C.c_int,I,D,C.c_int,I,C.c_int];lib.aru_compose_rows.restype=C.c_void_p
  lib.aru_compose_size.argtypes=[C.c_void_p];lib.aru_compose_size.restype=C.c_int
  lib.aru_compose_copy.argtypes=[C.c_void_p,I,I,D];lib.aru_compose_copy.restype=C.c_int
  lib.aru_compose_destroy.argtypes=[C.c_void_p];lib.aru_compose_destroy.restype=None
  _LIB=lib
 return _LIB

def compose(points,offsets,indices,weights,requests):
 if not requests:return []
 po=array('i',[0]);pi=array('i');pw=array('d')
 for row in points:
  if row:
   pi.extend(row);pw.extend(row.values())
  po.append(len(pi))
 buffers=[po,pi,pw,offsets,indices,weights,array('i',requests)]
 owners=[((C.c_double if a.typecode=='d' else C.c_int)*len(a)).from_buffer(a) for a in buffers]
 lib=library();h=lib.aru_compose_rows(owners[0],len(points),owners[1],owners[2],len(pi),owners[3],len(offsets)-1,owners[4],owners[5],len(indices),owners[6],len(requests))
 if not h:raise RuntimeError('Native stencil composition failed')
 try:
  size=lib.aru_compose_size(h);off=(C.c_int*(len(requests)+1))();ids=(C.c_int*size)();w=(C.c_double*size)()
  if not lib.aru_compose_copy(h,off,ids,w):raise RuntimeError('Stencil copy failed')
  return [dict(zip(ids[off[i]:off[i+1]],w[off[i]:off[i+1]])) for i in range(len(requests))]
 finally:lib.aru_compose_destroy(h)
