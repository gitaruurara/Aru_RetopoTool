import ctypes as C, numpy as np, inspect
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax

def endpoint_hits(mesh_fn,old,weights,neighbors,strength,smooth):
 p=mp.get_projector(mesh_fn);fn=p.lib.aru_maya_relax_endpoints
 d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
 fn.argtypes=[C.c_void_p,d,C.c_int,i,i,i,d,C.c_int,C.c_double,C.c_int,d,i];fn.restype=C.c_int
 original_ids=list(weights)
 flat=[];offsets=[0]
 for ep in original_ids:flat.extend(neighbors[ep]);offsets.append(len(flat))
 used=list(dict.fromkeys(original_ids+flat));remap={ep:i for i,ep in enumerate(used)}
 ids=np.array([remap[ep] for ep in original_ids],dtype=np.int32)
 xyz=np.ascontiguousarray([old[ep] for ep in used],dtype=np.float64)
 flat=[remap[ep] for ep in flat]
 adj=np.array(flat or [0],dtype=np.int32);off=np.array(offsets,dtype=np.int32);w=np.array(list(weights.values()),dtype=np.float64)
 out=np.empty((len(ids),9),dtype=np.float64);meta=np.empty((len(ids),5),dtype=np.int32)
 if not len(ids):return {}
 if not fn(p.handle,xyz.ctypes.data_as(d),len(xyz),ids.ctypes.data_as(i),off.ctypes.data_as(i),adj.ctypes.data_as(i),w.ctypes.data_as(d),len(ids),strength,int(smooth),out.ctypes.data_as(d),meta.ctypes.data_as(i)):raise RuntimeError('Endpoint kernel failed')
 return {int(ep):(row[:3].tolist(),row[3:6].tolist(),int(m[0]),[(int(m[j+1]),float(row[j+6])) for j in range(m[4])]) for ep,row,m in zip(original_ids,out,meta)}

def install():
 if hasattr(mp,"endpoint_hits"):raise RuntimeError("Endpoint kernel is already integrated; use release tests")
 original=relax.relax
 source=inspect.getsource(original)
 start=source.index('    hits=dict(zip(weights,surface_hits(')
 end=source.index('    for ep, weight in weights.items():',start)
 source=source[:start]+'    hits=_endpoint_candidate(mesh_fn,old,weights,neighbors,strength,smooth)\n'+source[end:]
 scope={};relax._endpoint_candidate=endpoint_hits
 exec(compile(source,'<endpoint candidate>','exec'),relax.__dict__,scope)
 relax.relax=scope['relax']
 def restore():relax.relax=original
 return restore
