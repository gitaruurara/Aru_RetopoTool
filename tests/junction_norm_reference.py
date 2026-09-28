"""Pre-optimization junction directions, retained for numeric parity tests."""
def _smooth_junctions(cn, weights, mesh_fn, mesh_dag, amount=1., respect_manual=False):
    """Pair opposite branches in the tangent plane, then fit lengths only.

    Independent geodesics have no shared derivative. Keep their useful surface
    fit, but give opposite branches a common tangent so a row can flow through
    a junction. Unpaired corner/branch directions remain independent.
    """
    from Aru_RetopoTool.hard_surface import enabled
    if enabled():return set()
    import numpy as np
    incident = {}
    for si, (a, h, j, b) in enumerate(cn.splines):
        if respect_manual and cn.spline_has_manual_handle(si): continue
        incident.setdefault(a, []).append((si, h, b))
        incident.setdefault(b, []).append((si, j, a))
    directions = {}
    touched = set()
    from Aru_RetopoTool.editor.curvenet.maya_projector import surface_hits
    normal_map={ep:hit[1] for ep,hit in zip(weights,surface_hits(mesh_fn,[cn.positions[ep] for ep in weights]))}
    for ep, weight in weights.items():
        p = np.array(cn.positions[ep], dtype=float)
        n = np.array(normal_map[ep])
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
    _fit_junction_lengths(cn,touched,directions,mesh_fn)

