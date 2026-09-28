"""Native branch-pairing candidate for disposable tests."""
import ctypes as C
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax


def install():
    original=relax._smooth_junctions
    def smooth(cn,weights,mesh_fn,mesh_dag,amount=1.,respect_manual=False):
        from Aru_RetopoTool.hard_surface import enabled
        if enabled():return set()
        projector=mp.get_projector(mesh_fn)
        if projector is None or not hasattr(projector.lib,'aru_maya_junction_directions'):
            return original(cn,weights,mesh_fn,mesh_dag,amount,respect_manual)
        eps=list(weights)
        if not eps:return
        incident=relax._relax_topology(cn)[2];records=[];offsets=[0]
        for ep in eps:
            records.extend((si,h,other) for si,h,other in incident.get(ep,()) if not respect_manual or not cn.spline_has_manual_handle(si))
            offsets.append(len(records))
        if not records:return
        points=np.ascontiguousarray([cn.positions[ep] for ep in eps],dtype=np.float64)
        normals=mp.normals_array(mesh_fn,points)
        strengths=np.ascontiguousarray([weights[ep] for ep in eps],dtype=np.float64)
        offsets=np.ascontiguousarray(offsets,dtype=np.int32)
        branches=np.ascontiguousarray([[*cn.positions[other],*cn.positions[h]] for si,h,other in records],dtype=np.float64)
        selected=np.empty(len(records),dtype=np.int32);directions=np.empty((len(records),3),dtype=np.float64)
        d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
        fn=projector.lib.aru_maya_junction_directions
        fn.argtypes=[d,d,d,C.c_double,i,d,C.c_int,C.c_int,i,d];fn.restype=C.c_int
        count=fn(points.ctypes.data_as(d),normals.ctypes.data_as(d),strengths.ctypes.data_as(d),amount,offsets.ctypes.data_as(i),branches.ctypes.data_as(d),len(eps),len(records),selected.ctypes.data_as(i),directions.ctypes.data_as(d))
        if count<0:raise RuntimeError('Native junction directions failed')
        if count:
            values={};touched=set()
            for record,direction in zip(selected[:count],directions[:count]):
                si,h,other=records[int(record)];values[h]=direction;touched.add(si)
            relax._fit_junction_lengths(cn,touched,values,mesh_fn)
    relax._smooth_junctions=smooth
    def restore():relax._smooth_junctions=original
    return restore
