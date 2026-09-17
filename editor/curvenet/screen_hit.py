"""Batched screen-space curve picking; exact Maya pixel projection."""
import numpy as np
from . import curve_net_edit as edit


def find_spline(cn, sx, sy, tol_px, exclude_eps=None, mesh_name=''):
    from . import curve_net_context as context
    excluded=exclude_eps or set()
    valid=[(si,sp) for si,sp in enumerate(cn.splines)
           if not any(i>=len(cn.positions) for i in sp)
           and sp[0] not in excluded and sp[3] not in excluded]
    if not valid:return None
    from .maya_screen import segment_candidates
    candidates=segment_candidates(cn.positions,[sp for _,sp in valid],sx,sy,tol_px*tol_px)
    if candidates is not None:
        best=None;best_d2=tol_px*tol_px
        vis=context.make_visibility_test(mesh_name) if mesh_name else None
        for index,t,distance in candidates:
            if distance>=best_d2 or t<.04 or t>.96:continue
            si,sp=valid[index//24]
            point=context._bezier_point(*(cn.positions[i] for i in sp),t)
            if vis is not None and not vis(point):continue
            best_d2=distance;best=(si,t,point)
        return best
    count=24
    ts=[k/count for k in range(count+1)]
    # Scalar coefficient construction matches the original Bezier arithmetic.
    basis=np.asarray([[(1-t)**3,3*(1-t)**2*t,3*(1-t)*t**2,t**3] for t in ts])
    controls=np.asarray(cn.positions,dtype=float)[np.asarray([sp for _,sp in valid])]
    samples=(basis[None,:,0,None]*controls[:,None,0,:]
             +basis[None,:,1,None]*controls[:,None,1,:]
             +basis[None,:,2,None]*controls[:,None,2,:]
             +basis[None,:,3,None]*controls[:,None,3,:])
    from .maya_screen import project
    native=project(samples.reshape(-1,3),as_array=True)
    if native is not None:
        xy=native[0].astype(float).reshape(-1,count+1,2)
        visible=native[1].reshape(-1,count+1)
    else:
        screens=edit._world_to_screen_many(samples.reshape(-1,3))
        visible=np.asarray([p is not None for p in screens]).reshape(-1,count+1)
        xy=np.asarray([p if p is not None else (0,0) for p in screens],dtype=float).reshape(-1,count+1,2)
    a=xy[:,:-1];edge=xy[:,1:]-a
    length=edge[:,:,0]**2+edge[:,:,1]**2
    u=((sx-a[:,:,0])*edge[:,:,0]+(sy-a[:,:,1])*edge[:,:,1])/np.maximum(length,1e-12)
    u=np.where(length<1e-12,0.,np.clip(u,0.,1.))
    closest=a+edge*u[:,:,None]
    d2=(sx-closest[:,:,0])**2+(sy-closest[:,:,1])**2
    best=None;best_d2=tol_px*tol_px
    # Preserve spline/segment traversal and visibility-test order, including ties.
    candidates=np.flatnonzero((d2<best_d2)&visible[:,:-1]&visible[:,1:])
    vis=context.make_visibility_test(mesh_name) if mesh_name else None
    for index in candidates:
        row,k=divmod(int(index),count)
        distance=float(d2[row,k])
        if distance>=best_d2:continue
        t=ts[k]+(ts[k+1]-ts[k])*float(u[row,k])
        if t<.04 or t>.96:continue
        si,sp=valid[row]
        point=context._bezier_point(*(cn.positions[i] for i in sp),t)
        if vis is not None and not vis(point):continue
        best_d2=distance;best=(si,t,point)
    return best
