"""Symmetry seam constraints, separate from reference-surface projection."""
from . import curve_net_symmetry as sym


def seam_handles(cn, mesh, tolerance=1e-6, axis=None, space=None):
    axis=sym.get_axis() if axis is None else axis
    if not axis:return set()
    result=set()
    for a,h,j,b in cn.splines:
        if all(sym.on_symmetry_plane(cn.positions[v],mesh,tolerance,axis,space) for v in (a,b)):
            result.update((h,j))
    return result


def constrain(cn, mesh, tolerance=1e-6, axis=None, space=None):
    handles=seam_handles(cn,mesh,tolerance,axis,space)
    for v in handles:cn.positions[v]=sym.project_to_plane(cn.positions[v],mesh,axis,space)
    return handles


def drag_position(cn, handle, position, mesh, snap_tolerance):
    if not sym.is_enabled():return list(position)
    if (handle in seam_handles(cn,mesh) or
            sym.on_symmetry_plane(position,mesh,snap_tolerance)):
        return sym.project_to_plane(position,mesh)
    return list(position)
