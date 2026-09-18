"""Carry only explicitly filled regions through the guide mirror command."""
import json
from maya import cmds
from . import core, patch_transfer
from .editor.curvenet import curve_net_edit as edit, curve_net_symmetry as sym


def snapshot(guide, cn):
    # This also transfers keys when the mirror command split crossing splines.
    updates=dict(patch_transfer.prepare(guide,cn))
    result=[]
    for node in cmds.listConnections(guide+'.outNetData',s=False,d=True,type='aruRetopoMesh') or []:
        keys=updates.get(node,set(json.loads(cmds.getAttr(node+'.selectedPatches') or '[]')))
        result.append((node,[tuple(tuple(cn.splines[si]) for si,_ in json.loads(key)) for key in keys]))
    return result


def resolve(cn, mesh, records, axis, space, source_sign):
    fn,_=edit._get_mesh_fn(mesh)
    normal=lambda p:edit._get_normal_at_point(fn,p)
    try:loops=core.regions(cn.positions,cn.splines,normal)
    except ValueError:loops=[]
    by_edges={frozenset(si for side in loop for si,_ in side):core.patch_key(loop) for loop in loops}
    by_spline={tuple(sp):i for i,sp in enumerate(cn.splines)}
    tolerance=max(edit._snap_radius(mesh)*1e-4,1e-6)
    def reflected_edge(sp):
        a=sym.mirror_point(cn.positions[sp[0]],mesh,axis,space)
        b=sym.mirror_point(cn.positions[sp[3]],mesh,axis,space)
        def close(p,q):return sum((p[k]-q[k])**2 for k in range(3))<=tolerance*tolerance
        for i,s in enumerate(cn.splines):
            p,q=cn.positions[s[0]],cn.positions[s[3]]
            if (close(a,p) and close(b,q)) or (close(a,q) and close(b,p)):return i
        return None
    result=[]
    for node,boundaries in records:
        selected=set()
        for boundary in boundaries:
            # Existing destination regions survive only if their curves survived.
            ids=[by_spline.get(sp) for sp in boundary]
            key=by_edges.get(frozenset(ids)) if None not in ids else None
            if key:selected.add(key)
            coords=[sym.plane_coord(cn.positions[sp[end]],mesh,axis,space) for sp in boundary for end in (0,3)]
            if any(c is None for c in coords):continue
            if any(c*source_sign < -tolerance for c in coords):
                # A confirmed patch can straddle the plane. Its source half
                # and reflected half form the new boundary after replacement.
                source=[sp for sp in boundary if all(sym.plane_coord(cn.positions[sp[e]],mesh,axis,space)*source_sign>=-tolerance for e in (0,3))]
                ids=[by_spline.get(sp) for sp in source]+[reflected_edge(sp) for sp in source]
                key=by_edges.get(frozenset(ids)) if ids and None not in ids else None
                if key:selected.add(key)
                continue
            ids=[reflected_edge(sp) for sp in boundary]
            key=by_edges.get(frozenset(ids)) if None not in ids else None
            if key:selected.add(key)
        result.append((node,selected))
    return result
