import ctypes as C,inspect,numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax

def fit(mesh_fn,controls,ds,lengths,chords):
 projector=mp.get_projector(mesh_fn);fn=projector.lib.aru_maya_junction_compact
 d=C.POINTER(C.c_double);fn.argtypes=[C.c_void_p,d,d,d,d,d,C.c_int,d];fn.restype=C.c_int
 ts=np.linspace(.05,.95,15);us=1-ts;c0=3*us*us*ts;c1=3*us*ts*ts
 coefficients=np.stack((c0,c1,us**3+c0,ts**3+c1),axis=1)
 arrays=[np.ascontiguousarray(x,dtype=np.float64) for x in (controls,ds,lengths,chords,coefficients)]
 result=np.empty_like(lengths)
 if not fn(projector.handle,*(x.ctypes.data_as(d) for x in arrays),len(lengths),result.ctypes.data_as(d)):raise RuntimeError('Compact junction failed')
 return result

def install():
 if hasattr(mp,"junction_compact"):raise RuntimeError("Compact junction is already integrated; use release tests")
 original=relax._fit_junction_lengths;source=inspect.getsource(original)
 a=source.index('    ts=np.linspace(');b=source.index('    h1=p+',a)
 source=source[:a]+'    lengths=_compact_junction(mesh_fn,controls,ds,lengths,chord[:,0])\n'+source[b:]
 relax._compact_junction=fit;scope={};exec(compile(source,'<compact junction>','exec'),relax.__dict__,scope)
 relax._fit_junction_lengths=scope['_fit_junction_lengths']
 def restore():relax._fit_junction_lengths=original
 return restore
