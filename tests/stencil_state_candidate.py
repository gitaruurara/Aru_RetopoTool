import ctypes as C
from array import array
from pathlib import Path
I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).resolve().parents[1]/'bin/aru_retopo_state_candidate.dll'))
  definitions={
   'aru_state_create':([I,C.c_int],C.c_void_p),
   'aru_state_destroy':([C.c_void_p],None),
   'aru_state_step':([C.c_void_p,I,C.c_int,I,D,C.c_int,I,C.c_int],C.c_int),
   'aru_state_set':([C.c_void_p,I,C.c_int,I,I,D,C.c_int],C.c_int),
   'aru_state_pack':([C.c_void_p],C.c_void_p),
   'aru_compose_size':([C.c_void_p],C.c_int),
   'aru_compose_copy':([C.c_void_p,I,I,D],C.c_int),
   'aru_compose_destroy':([C.c_void_p],None)}
  for name,(args,result) in definitions.items():
   fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
  _LIB=lib
 return _LIB

def view(a):return ((C.c_double if a.typecode=='d' else C.c_int)*len(a)).from_buffer(a)

class Composer:
 def __init__(self,endpoints):
  self.lib=library();eps=array('i',endpoints);self.handle=self.lib.aru_state_create(view(eps),len(eps));self.count=len(eps)
  if not self.handle:raise RuntimeError('Cannot create composer')
 def close(self):
  if getattr(self,'handle',None):self.lib.aru_state_destroy(self.handle);self.handle=None
 def __enter__(self):return self
 def __exit__(self,*unused):self.close()
 def step(self,offsets,ids,weights,requests):
  requests=array('i',requests)
  if not self.lib.aru_state_step(self.handle,view(offsets),len(offsets)-1,view(ids),view(weights),len(ids),view(requests),len(requests)):raise RuntimeError('Compose step failed')
  self.count=len(offsets)-1
 def set(self,rows):
  if not rows:return
  which=array('i',rows);offsets=array('i',[0]);ids=array('i');weights=array('d')
  for row in rows.values():ids.extend(row);weights.extend(row.values());offsets.append(len(ids))
  if not self.lib.aru_state_set(self.handle,view(which),len(which),view(offsets),view(ids),view(weights),len(ids)):raise RuntimeError('Compose override failed')
 def packed(self):
  result=self.lib.aru_state_pack(self.handle)
  if not result:raise RuntimeError('Compose packing failed')
  try:
   size=self.lib.aru_compose_size(result)
   offsets=array('i',[0])*(self.count+1);ids=array('i',[0])*size;weights=array('d',[0.])*size
   if not self.lib.aru_compose_copy(result,view(offsets),view(ids),view(weights)):raise RuntimeError('Compose copy failed')
   return offsets.tolist(),ids.tolist(),weights.tolist()
  finally:self.lib.aru_compose_destroy(result)
