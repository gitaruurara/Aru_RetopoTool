"""Local, topology-preserving surface relaxation for the edit context."""
import json
import math
from maya import cmds
import maya.api.OpenMaya as om2
from .curve_net_data import RetopoGuideData
from . import curve_net_edit as edit


def _world_data(node):
    if edit.is_pose_driven(node):
        raise ValueError('リラックスはスキン／ポーズ駆動前のカーブネットで使用してください。')
    cn = RetopoGuideData.from_dict(json.loads(cmds.getAttr(node+'.outNetData')))
    selection = om2.MSelectionList(); selection.add(node)
    matrix = selection.getDagPath(0).inclusiveMatrix()
    for i, p in enumerate(cn.positions):
        q = om2.MPoint(*p)*matrix
        cn.positions[i] = [q.x, q.y, q.z]
    return cn, matrix


def brush_weights(node, sx, sy, radius=80.):
    cn, _ = _world_data(node)
    mesh = edit.RetopoGuideAccessor(node).mesh_name
    visible = edit.make_visibility_test(mesh)
    weights = {}
    for ep in cn.endpoint_indices():
        p = cn.positions[ep]
        screen = edit._world_to_screen(p)
        if screen is None or (visible and not visible(p)): continue
        distance = math.hypot(screen[0]-sx, screen[1]-sy)
        if distance < radius: weights[ep] = (1-distance/radius)**2
    return weights


def _smooth_junctions(cn, weights, mesh_fn, mesh_dag, amount=1., respect_manual=False):
    """Pair opposite branches in the tangent plane, then fit lengths only.

    Independent geodesics have no shared derivative. Keep their useful surface
    fit, but give opposite branches a common tangent so a row can flow through
    a junction. Unpaired corner/branch directions remain independent.
    """
    import numpy as np
    incident = {}
    for si, (a, h, j, b) in enumerate(cn.splines):
        if respect_manual and cn.spline_has_manual_handle(si): continue
        incident.setdefault(a, []).append((si, h, b))
        incident.setdefault(b, []).append((si, j, a))
    directions = {}
    touched = set()
    for ep, weight in weights.items():
        p = np.array(cn.positions[ep], dtype=float)
        n = np.array(edit._get_normal_at_point(mesh_fn, p.tolist()))
        n /= max(np.linalg.norm(n), 1e-12)
        branches = []
        for si, h, other in incident.get(ep, []):
            v = np.array(cn.positions[other])-p
            v -= n*np.dot(v, n)
            length = np.linalg.norm(v)
            if length > 1e-9: branches.append((si, h, v/length))
        # Greedy strongest opposites avoids coupling adjacent arms of a cross.
        candidates = sorted((float(np.dot(a[2], b[2])), i, j)
                            for i, a in enumerate(branches)
                            for j, b in enumerate(branches) if i < j)
        used = set()
        for dot, i, j in candidates:
            if dot > -.3 or i in used or j in used: continue
            used.update((i, j))
            axis = branches[i][2]-branches[j][2]
            axis /= np.linalg.norm(axis)
            for index, target in ((i, axis), (j, -axis)):
                si, h, fallback = branches[index]
                v = np.array(cn.positions[h])-p
                v -= n*np.dot(v, n)
                v = v/max(np.linalg.norm(v), 1e-12) if np.linalg.norm(v)>1e-9 else fallback
                alpha = min(1., amount*weight)
                d = (1-alpha)*v+alpha*target
                d /= max(np.linalg.norm(d), 1e-12)
                directions[h] = d
                touched.add(si)
    for si in touched:
        a, h, j, b = cn.splines[si]
        p, q = np.array(cn.positions[a]), np.array(cn.positions[b])
        chord = np.linalg.norm(q-p)
        if chord < 1e-9: continue
        ds = []; lengths = []
        for ep, handle in ((p, h), (q, j)):
            v = np.array(cn.positions[handle])-ep
            length = np.linalg.norm(v)
            ds.append(directions.get(handle, v/max(length, 1e-12)))
            lengths.append(np.clip(length, chord*.05, chord*.6))
        lengths = np.array(lengths)
        # Project samples of the continuous curve, solving only handle lengths.
        # Mild regularization prevents runaway/flattened handles on flat areas.
        for _ in range(4):
            rows = []; rhs = []
            for t in np.linspace(.05, .95, 15):
                u = 1-t; c0 = 3*u*u*t; c1 = 3*u*t*t
                base = (u**3+c0)*p+(t**3+c1)*q
                sample = base+c0*lengths[0]*ds[0]+c1*lengths[1]*ds[1]
                projected, _, _ = edit._closest_point_on_mesh(mesh_fn, mesh_dag, sample.tolist())
                rows.extend(np.column_stack((c0*ds[0], c1*ds[1])))
                rhs.extend(np.array(projected)-base)
            rows.extend(np.eye(2)*.1); rhs.extend(lengths*.1)
            lengths = np.clip(np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0], chord*.05, chord*.6)
        cn.positions[h] = (p+lengths[0]*ds[0]).tolist()
        cn.positions[j] = (q+lengths[1]*ds[1]).tolist()


def relax(node, weights, strength=.2, draft=True, smooth=True):
    """One simultaneous tangent-plane Laplacian step plus projected curve fit.

    Caller owns the undo chunk (one brush stroke). Handles may be off-surface:
    the Bézier curve, rather than its control polygon, is fitted to the mesh.
    Returns affected EP indices. CV and spline indices are never changed.
    """
    if not weights: return set()
    from . import curve_net_context as context
    from . import curve_net_symmetry as symmetry
    cn, matrix = _world_data(node)
    acc = edit.RetopoGuideAccessor(node)
    mesh = acc.mesh_name
    if not mesh or not cmds.objExists(mesh): raise ValueError('参照メッシュを設定してください。')
    mesh_fn, mesh_dag = edit._get_mesh_fn(mesh)
    eps = cn.endpoint_indices()
    weights = {v: max(0., min(1., float(w))) for v, w in weights.items() if v in eps and w > 0}
    if symmetry.is_enabled():
        tol = context._mirror_tol(mesh)
        for ep, weight in list(weights.items()):
            mirror = symmetry.find_mirror_ep(cn, mesh, ep, tol)
            if mirror is not None: weights[mirror] = max(weights.get(mirror, 0), weight)
    neighbors = {v:set() for v in eps}
    for a, _, _, b in cn.splines:
        neighbors[a].add(b); neighbors[b].add(a)
    old = [list(p) for p in cn.positions]
    for ep, weight in weights.items():
        p = old[ep]
        projected, face, bary = edit._closest_point_on_mesh(mesh_fn, mesh_dag, p)
        adjacent = neighbors[ep]
        if smooth and len(adjacent) >= 2:
            center = [sum(old[v][k] for v in adjacent)/len(adjacent) for k in range(3)]
            n = edit._get_normal_at_point(mesh_fn, projected)
            delta = [center[k]-p[k] for k in range(3)]
            normal_length = sum(x*x for x in n)
            dn = sum(delta[k]*n[k] for k in range(3))/max(normal_length, 1e-12)
            target = [projected[k]+strength*weight*(delta[k]-dn*n[k]) for k in range(3)]
            projected, face, bary = edit._closest_point_on_mesh(mesh_fn, mesh_dag, target)
        cn.positions[ep] = projected
        cn.surface_binding[ep] = (face, bary)
        delta = [projected[k]-p[k] for k in range(3)]
        # Translate all incident handles before refitting, avoiding a snap in
        # the curve direction when only one endpoint moves.
        for sp in cn.splines:
            handle = sp[1] if sp[0] == ep else (sp[2] if sp[3] == ep else None)
            if handle is not None: cn.positions[handle] = [old[handle][k]+delta[k] for k in range(3)]
    for si, sp in enumerate(cn.splines):
        if sp[0] not in weights and sp[3] not in weights: continue
        # Explicit relaxing gives the fitter control of these handles.
        cn.clear_manual_handles(sp[1:3])
        context._fit_spline_handles_to_mesh(cn, si, mesh,
            iters=context._FIT_DRAFT_ITERS if draft else context._FIT_ITERS,
            n_samples=context._FIT_DRAFT_SAMPLES if draft else context._FIT_SAMPLES)
    _smooth_junctions(cn, weights, mesh_fn, mesh_dag,
                      amount=min(1., strength*3) if smooth else 1.)
    inverse = matrix.inverse()
    for i, p in enumerate(cn.positions):
        q = om2.MPoint(*p)*inverse
        cn.positions[i] = [q.x, q.y, q.z]
    acc.write(cn)
    return set(weights)
