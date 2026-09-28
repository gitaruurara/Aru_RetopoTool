"""Fused route/binding candidate; only installed by disposable tests."""
import ctypes as C
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax


fit_bound=mp.fit_routes_bound


def install():
    old=relax._fit_relax_routes
    def fit(cn,indices,mesh_fn,mesh_dag,draft):
        from Aru_RetopoTool import hard_surface
        if hard_surface.enabled():return False
        handles=[h for si in indices for h in cn.splines[si][1:3]]
        if len(handles)!=len(set(handles)) or set(handles).intersection(cn.endpoint_indices()):return False
        import math
        eligible=[si for si in indices if math.dist(cn.positions[cn.splines[si][0]],cn.positions[cn.splines[si][3]])>=1e-9]
        result=fit_bound(mesh_fn,[[cn.positions[i] for i in cn.splines[si]] for si in eligible],draft) if eligible else ([],[])
        if result is None:return old(cn,indices,mesh_fn,mesh_dag,draft)
        fitted,bindings=result
        for si in indices:cn.clear_manual_handles(cn.splines[si][1:3])
        metadata=iter(bindings)
        for si,positions in zip(eligible,fitted):
            for hi,position in zip(cn.splines[si][1:3],positions):
                cn.positions[hi]=position;cn.surface_binding[hi]=next(metadata)
        return True
    relax._fit_relax_routes=fit
    def restore():relax._fit_relax_routes=old
    return restore
