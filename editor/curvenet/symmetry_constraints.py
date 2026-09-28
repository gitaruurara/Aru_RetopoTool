"""Symmetry seam constraints, separate from reference-surface projection."""
from . import curve_net_symmetry as sym


def _plane(mesh,axis,space):
    """Resolve scene settings and object matrices once per operation."""
    axis=sym.get_axis() if axis is None else (axis or '').lower()
    space=sym.get_space() if space is None else space
    if not axis:return None,None
    k=sym._AXIS_INDEX.get(axis)
    if k is None:return lambda p:list(p),lambda p:list(p)
    if space=='world':
        def mirror(p):
            q=list(p);q[k]=-q[k];return q
        def project(p):
            q=list(p);q[k]=0.;return q
        return mirror,project
    wm,wim=sym._object_matrices(mesh)
    if wm is None:return lambda p:list(p),lambda p:list(p)
    def transformed(p,factor):
        q=sym.om.MPoint(*p)*wim
        values=[q.x,q.y,q.z];values[k]*=factor
        q=sym.om.MPoint(*values)*wm
        return [q.x,q.y,q.z]
    return lambda p:transformed(p,-1.),lambda p:transformed(p,0.)


def _handles(cn,mirror,tolerance):
    if mirror is None:return set()
    on_plane={}
    def on(ep):
        if ep not in on_plane:
            p=cn.positions[ep];q=mirror(p)
            on_plane[ep]=sum((a-b)**2 for a,b in zip(p,q))<=tolerance*tolerance
        return on_plane[ep]
    result=set()
    for a,h,j,b in cn.splines:
        if on(a) and on(b):result.update((h,j))
    return result


def seam_handles(cn,mesh,tolerance=1e-6,axis=None,space=None):
    mirror,_=_plane(mesh,axis,space)
    return _handles(cn,mirror,tolerance)


def constrain(cn,mesh,tolerance=1e-6,axis=None,space=None):
    mirror,project=_plane(mesh,axis,space)
    handles=_handles(cn,mirror,tolerance)
    for v in handles:cn.positions[v]=project(cn.positions[v])
    return handles


def drag_position(cn, handle, position, mesh, snap_tolerance):
    if not sym.is_enabled():return list(position)
    if (handle in seam_handles(cn,mesh) or
            sym.on_symmetry_plane(position,mesh,snap_tolerance)):
        return sym.project_to_plane(position,mesh)
    return list(position)
