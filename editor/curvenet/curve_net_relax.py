"""Local, topology-preserving surface relaxation for the edit context."""
import json
import math
from maya import cmds
import maya.api.OpenMaya as om2
from .curve_net_data import RetopoGuideData
from . import curve_net_edit as edit



def _copy_surface_bindings(bindings):
    """Own numeric barycentric lists; retain deepcopy for legacy formats."""
    import copy
    memo = {}
    result = []
    for binding in bindings:
        if not binding:
            result.append(None)
            continue
        if (type(binding) in (tuple, list) and len(binding) == 2
                and type(binding[0]) is int and type(binding[1]) is list
                and all(type(pair) in (tuple, list) and len(pair) == 2
                        and type(pair[0]) is int and type(pair[1]) in (int, float)
                        for pair in binding[1])):
            bary = binding[1]
            copied = memo.get(id(bary))
            if copied is None:
                copied = []
                memo[id(bary)] = copied
                for pair in bary:
                    if type(pair) is tuple:
                        copied.append(pair)  # Two immutable numeric values.
                    else:
                        item = memo.get(id(pair))
                        if item is None:
                            item = list(pair)
                            memo[id(pair)] = item
                        copied.append(item)
            result.append((binding[0], copied))
        else:
            result.append(tuple(copy.deepcopy(binding, memo)))
    return result


def _evaluated_copy(base, values):
    """Own evaluated positions and copy topology from normalized cached netData.

    CP evaluation changes positions only. Parsed data already has classified
    endpoints and curve chains, so no graph traversal is needed here. Every
    mutable container is copied; EP/Handle wrappers are created on demand for
    this new owner. This helper must receive an unmodified parsed cache entry.
    """
    if len(values) != len(base.positions)*3:
        raise ValueError('Evaluated guide position count differs from topology')
    cn = RetopoGuideData()
    cn._lazy_objects = True
    cn._objects_dirty = True
    cn.positions = [list(p) for p in zip(values[0::3], values[1::3], values[2::3])]
    cn.surface_binding = _copy_surface_bindings(base.surface_binding)
    cn.splines = list(base.splines)  # Each spline is an immutable tuple.
    cn.standalone_eps = set(base.standalone_eps)
    cn.manual_handles = set(base.manual_handles)
    cn._endpoint_to_splines = {ep:list(ids) for ep,ids in base._endpoint_to_splines.items()}
    cn._endpoint_type = dict(base._endpoint_type)
    cn.curves = [list(chain) for chain in base.curves]
    cn._classified_topology = getattr(base, '_classified_topology', None)
    return cn


def _world_data(node, *, _source=None, _reuse_source=False):
    if edit.is_pose_driven(node):
        raise ValueError('リラックスはスキン／ポーズ駆動前のカーブネットで使用してください。')
    selection = om2.MSelectionList(); selection.add(node)
    dag = selection.getDagPath(0)
    dep = om2.MFnDependencyNode(dag.node())
    matrix = dag.inclusiveMatrix()
    if dep.hasAttribute('outPositions'):
        # A guarded numeric stroke can supply its latest owned metadata.
        # Positions still come from the currently evaluated Maya output.
        base = (_source if _source is not None else
                RetopoGuideData.from_json_cached(dep.findPlug('netData',False).asString()))
        data = dep.findPlug('outPositions',False).asMObject()
        values_fn = om2.MFnDoubleArrayData(data)
        values = list(values_fn.array())
        if _reuse_source and _source is not None and matrix==om2.MMatrix():
            if len(values)!=len(base.positions)*3:
                raise ValueError('Evaluated guide position count differs from topology')
            cn=base
            for index,p in enumerate(cn.positions):
                start=3*index
                p[0]=values[start];p[1]=values[start+1];p[2]=values[start+2]
        else:
            cn = _evaluated_copy(base, values)
    else:
        cn = RetopoGuideData.from_dict(json.loads(cmds.getAttr(node+'.outNetData')), lazy_objects=True)
    if matrix!=om2.MMatrix():
        for i, p in enumerate(cn.positions):
            q = om2.MPoint(*p)*matrix
            cn.positions[i] = [q.x, q.y, q.z]
    return cn, matrix


def brush_weights(node, sx, sy, radius=80., *, _world=None):
    cn, _ = _world_data(node) if _world is None else _world
    mesh = edit.RetopoGuideAccessor(node).mesh_name
    visible = edit.make_visibility_test(mesh)
    weights = {}
    eps = list(cn.endpoint_indices())
    from .maya_screen import radius_candidates
    positions=[cn.positions[ep] for ep in eps]
    nearby=radius_candidates(positions,sx,sy,radius)
    if nearby is not None:
        candidates=[(eps[index],distance) for index,distance in nearby]
    else:
        screens=edit._world_to_screen_many(positions)
        candidates=[]
        for ep,screen in zip(eps,screens):
            if screen is None:continue
            distance=math.hypot(screen[0]-sx,screen[1]-sy)
            if distance<radius:candidates.append((ep,distance))
    points=[cn.positions[ep] for ep,_ in candidates]
    if visible:
        batch=getattr(visible,'many',None)
        visibility=batch(points) if batch is not None else [visible(p) for p in points]
    else:visibility=[True]*len(points)
    for (ep,distance),is_visible in zip(candidates,visibility):
        if is_visible:weights[ep]=(1-distance/radius)**2
    return weights


def brush_relax(node, sx, sy, radius=80., strength=.2, draft=True, smooth=True):
    """Use one fresh evaluated snapshot for this synchronous brush event.

    The snapshot is owned by this call, never cached across events or cameras.
    Weight evaluation is read-only; relaxation consumes and writes it afterward.
    """
    world = _world_data(node)
    weights = brush_weights(node, sx, sy, radius, _world=world)
    return relax(node, weights, strength, draft, smooth, _world=world)


class _RelaxTopologyCache(tuple):
    """The key and mapping values are immutable; owned guide copies may share."""
    def __deepcopy__(self, memo):
        return self


def _relax_topology(cn):
    """Reuse immutable adjacency while an owned stroke changes positions only."""
    from types import MappingProxyType
    key = (len(cn.positions), tuple(cn.splines), frozenset(cn.standalone_eps))
    cached = getattr(cn, '_relax_topology_cache', None)
    if cached is not None and cached[0] == key:
        return cached[1]
    eps = cn.endpoint_indices()
    neighbors = {v: set() for v in eps}
    handles = {v: [] for v in eps}
    branches = {}
    for si, (a, h, j, b) in enumerate(cn.splines):
        neighbors[a].add(b); neighbors[b].add(a)
        handles[a].append(h)
        if b != a: handles[b].append(j)
        branches.setdefault(a, []).append((si, h, b))
        branches.setdefault(b, []).append((si, j, a))
    # Preserve the original set iteration order used by the Laplacian sum.
    graph = tuple(MappingProxyType({ep: tuple(items) for ep, items in mapping.items()})
                  for mapping in (neighbors, handles, branches))
    cn._relax_topology_cache = _RelaxTopologyCache((key, graph))
    return graph


def _smooth_junctions(cn, weights, mesh_fn, mesh_dag, amount=1., respect_manual=False):
    """Pair opposite branches in the tangent plane, then fit lengths only.

    Independent geodesics have no shared derivative. Keep their useful surface
    fit, but give opposite branches a common tangent so a row can flow through
    a junction. Unpaired corner/branch directions remain independent.
    """
    from Aru_RetopoTool.hard_surface import enabled
    if enabled():return set()
    import numpy as np
    # Keep vector reductions in the same three-component dot-product order.
    def dots(a, b): return (a[:, None, :] @ b[:, :, None])[:, 0, 0]
    incident = _relax_topology(cn)[2]
    directions = {}
    touched = set()
    eps = list(weights)
    if not eps: return
    points = np.asarray([cn.positions[ep] for ep in eps], dtype=float)
    from .maya_projector import normals_array
    normals = normals_array(mesh_fn, points)
    records = []
    ranges = []
    for row, ep in enumerate(eps):
        start = len(records)
        records.extend((row, si, h, other) for si, h, other in incident.get(ep, ())
                       if not respect_manual or not cn.spline_has_manual_handle(si))
        ranges.append((start, len(records)))
    if not records: return
    from .maya_projector import junction_directions
    paired=junction_directions(mesh_fn,points,normals,[weights[ep] for ep in eps],amount,
        [0]+[end for start,end in ranges],
        [[*cn.positions[other],*cn.positions[h]] for row,si,h,other in records])
    if paired is not None:
        selected,values=paired
        for index,direction in zip(selected,values):
            row,si,h,other=records[int(index)]
            directions[h]=direction;touched.add(si)
        if touched:_fit_junction_lengths(cn,touched,directions,mesh_fn)
        return
    normals /= np.maximum(np.sqrt(dots(normals, normals)), 1e-12)[:, None]
    owner = np.asarray([r[0] for r in records])
    vectors = np.asarray([cn.positions[r[3]] for r in records])-points[owner]
    ns = normals[owner]
    vectors -= ns*dots(vectors, ns)[:, None]
    lengths = np.sqrt(dots(vectors, vectors))
    valid = lengths > 1e-9
    vectors /= np.maximum(lengths, 1e-12)[:, None]
    selected = []
    for row, (start, end) in enumerate(ranges):
        branches = [(records[i][1], records[i][2], vectors[i])
                    for i in range(start, end) if valid[i]]
        candidates = sorted((float(np.dot(a[2], b[2])), i, j)
                            for i, a in enumerate(branches)
                            for j, b in enumerate(branches) if i < j)
        used = set()
        for dot, i, j in candidates:
            if dot > -.3 or i in used or j in used: continue
            used.update((i, j))
            axis = branches[i][2]-branches[j][2]
            axis /= np.sqrt(axis.dot(axis))
            for index, target in ((i, axis), (j, -axis)):
                si, h, fallback = branches[index]
                selected.append((row, si, h, target, fallback))
    if not selected: return
    owner = np.asarray([r[0] for r in selected])
    v = np.asarray([cn.positions[r[2]] for r in selected])-points[owner]
    ns = normals[owner]
    v -= ns*dots(v, ns)[:, None]
    magnitude = np.sqrt(dots(v, v))
    usable = magnitude > 1e-9
    v /= np.maximum(magnitude, 1e-12)[:, None]
    fallback = np.asarray([r[4] for r in selected])
    v[~usable] = fallback[~usable]
    alpha = np.asarray([min(1., amount*weights[eps[r[0]]]) for r in selected])[:, None]
    d = (1-alpha)*v+alpha*np.asarray([r[3] for r in selected])
    d /= np.maximum(np.sqrt(dots(d, d)), 1e-12)[:, None]
    for record, direction in zip(selected, d):
        directions[record[2]] = direction
        touched.add(record[1])
    _fit_junction_lengths(cn,touched,directions,mesh_fn)


def _fit_junction_lengths(cn,touched,directions,mesh_fn):
    """Project all independent junction curves together in each solver round."""
    import numpy as np
    from .maya_projector import points_array as project_many
    ids=list(touched)
    handles=[h for si in ids for h in cn.splines[si][1:3]]
    endpoints={ep for si in ids for ep in (cn.splines[si][0],cn.splines[si][3])}
    if len(set(handles))!=len(handles) or endpoints.intersection(handles):
        return _fit_junction_lengths_scalar(cn,touched,directions,mesh_fn)
    if not ids:return
    # Small brush strokes should not convert every CV in the network.
    # Dense edits retain the bulk gather to avoid expanding shared endpoints.
    selected=[cn.splines[si] for si in ids]
    if len(selected)*4<len(cn.positions):
        controls=np.asarray([[cn.positions[i] for i in spline] for spline in selected],dtype=float)
    else:
        controls=np.asarray(cn.positions,dtype=float)[np.asarray(selected)]
    chords=np.linalg.norm(controls[:,3]-controls[:,0],axis=1)
    valid=chords>=1e-9
    ids=[si for si,keep in zip(ids,valid) if keep]
    if not ids:return
    controls=controls[valid];chord=chords[valid,None]
    p=controls[:,0];q=controls[:,3]
    vectors=np.stack((controls[:,1]-p,controls[:,2]-q),axis=1)
    raw_lengths=np.linalg.norm(vectors,axis=2)
    ds=vectors/np.maximum(raw_lengths[:,:,None],1e-12)
    for row,si in enumerate(ids):
        for side,handle in enumerate(cn.splines[si][1:3]):
            if handle in directions:ds[row,side]=directions[handle]
    lengths=np.clip(raw_lengths,chord*.05,chord*.6)
    ts=np.linspace(.05,.95,15);us=1-ts;c0=3*us*us*ts;c1=3*us*ts*ts
    bases=(us**3+c0)[None,:,None]*p[:,None,:]+(ts**3+c1)[None,:,None]*q[:,None,:]
    columns0=c0[None,:,None]*ds[:,0,None,:];columns1=c1[None,:,None]*ds[:,1,None,:]
    count=len(ids)
    rows=np.concatenate((np.stack((columns0,columns1),axis=-1).reshape(count,-1,2),np.broadcast_to(np.eye(2)*.1,(count,2,2))),axis=1)
    inverse=np.linalg.pinv(rows,rcond=np.finfo(float).eps*rows.shape[1])
    from .maya_projector import junction_lengths
    fitted_lengths=junction_lengths(mesh_fn,bases,ds,lengths,chord[:,0],np.stack((c0,c1),axis=1),inverse)
    if fitted_lengths is not None:
        lengths=fitted_lengths
    else:
        for _ in range(4):
            samples=bases+c0[None,:,None]*lengths[:,0,None,None]*ds[:,0,None,:]+c1[None,:,None]*lengths[:,1,None,None]*ds[:,1,None,:]
            projected=project_many(mesh_fn,samples.reshape(-1,3)).reshape(samples.shape)
            rhs=np.concatenate(((projected-bases).reshape(count,-1),lengths*.1),axis=1)
            lengths=np.clip((inverse@rhs[:,:,None])[:,:,0],chord*.05,chord*.6)
    h1=p+lengths[:,0,None]*ds[:,0,:];h2=q+lengths[:,1,None]*ds[:,1,:]
    for i,si in enumerate(ids):
        h,j=cn.splines[si][1:3]
        cn.positions[h]=h1[i].tolist();cn.positions[j]=h2[i].tolist()


def _fit_junction_lengths_scalar(cn,touched,directions,mesh_fn):
    """Sequential reference also handles unusual shared control-point indices."""
    import numpy as np
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
        # Directions and Bernstein coefficients stay fixed during length fitting.
        # Assemble the least-squares matrix once, then only refresh its targets.
        ts = np.linspace(.05, .95, 15)
        us = 1-ts
        c0 = 3*us*us*ts
        c1 = 3*us*ts*ts
        bases = (us**3+c0)[:,None]*p+(ts**3+c1)[:,None]*q
        columns0 = c0[:,None]*ds[0]
        columns1 = c1[:,None]*ds[1]
        rows = np.concatenate((np.stack((columns0,columns1),axis=-1).reshape(-1,2),np.eye(2)*.1))
        for _ in range(4):
            samples = bases+c0[:,None]*lengths[0]*ds[0]+c1[:,None]*lengths[1]*ds[1]
            from .maya_projector import points_array as project_many
            projected = project_many(mesh_fn,samples)
            rhs = np.concatenate(((projected-bases).ravel(),lengths*.1))
            lengths = np.clip(np.linalg.lstsq(rows, rhs, rcond=None)[0], chord*.05, chord*.6)
        cn.positions[h] = (p+lengths[0]*ds[0]).tolist()
        cn.positions[j] = (q+lengths[1]*ds[1]).tolist()


def _fit_relax_routes(cn,indices,mesh_fn,mesh_dag,draft):
    """Independent automatic handles can be fitted in one native call."""
    from Aru_RetopoTool import hard_surface
    if hard_surface.enabled():return False
    handles=[h for si in indices for h in cn.splines[si][1:3]]
    if len(handles)!=len(set(handles)) or set(handles).intersection(cn.endpoint_indices()):return False
    eligible=[si for si in indices if math.dist(cn.positions[cn.splines[si][0]],cn.positions[cn.splines[si][3]])>=1e-9]
    from .maya_projector import fit_routes,fit_routes_bound,surface_hits
    controls=[[cn.positions[i] for i in cn.splines[si]] for si in eligible]
    result=fit_routes_bound(mesh_fn,controls,draft) if eligible else ([],[])
    if result is None:
        fitted=fit_routes(mesh_fn,controls,draft)
        if fitted is None:return False
        bindings=[(face,bary) for _q,_normal,face,bary in
                  surface_hits(mesh_fn,[position for pair in fitted for position in pair])]
    else:
        fitted,bindings=result
    for si in indices:cn.clear_manual_handles(cn.splines[si][1:3])
    metadata=iter(bindings)
    for si,positions in zip(eligible,fitted):
        for hi,position in zip(cn.splines[si][1:3],positions):
            cn.positions[hi]=position
            cn.surface_binding[hi]=next(metadata)
    return True


def relax(node, weights, strength=.2, draft=True, smooth=True, *, _world=None, _writer=None):
    """One simultaneous tangent-plane Laplacian step plus projected curve fit.

    Caller owns the undo chunk (one brush stroke). Handles may be off-surface:
    the Bézier curve, rather than its control polygon, is fitted to the mesh.
    Returns affected EP indices. CV and spline indices are never changed.
    """
    if not weights: return set()
    from . import curve_net_context as context
    from . import curve_net_symmetry as symmetry
    cn, matrix = _world_data(node) if _world is None else _world
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
    neighbors, incident_handles, _ = _relax_topology(cn)
    from Aru_RetopoTool import hard_surface
    feature_data=hard_surface.features(mesh) if hard_surface.enabled() else None
    # This phase replaces changed rows; it never edits an old row in place.
    old = list(cn.positions)
    from .maya_projector import surface_hits
    from .maya_projector import endpoint_hits
    hits=endpoint_hits(mesh_fn,old,weights,neighbors,strength,smooth)
    if hits is None:
        hits=dict(zip(weights,surface_hits(mesh_fn,[old[ep] for ep in weights])))
        moving=[ep for ep in weights if smooth and len(neighbors[ep])>=2]
        from .maya_projector import normals_array
        normals=dict(zip(moving,normals_array(mesh_fn,[hits[ep][0] for ep in moving]).tolist()))
        targets=[]
        for ep in moving:
            p=old[ep];projected=hits[ep][0];adjacent=neighbors[ep];n=normals[ep]
            center=[sum(old[v][k] for v in adjacent)/len(adjacent) for k in range(3)]
            delta=[center[k]-p[k] for k in range(3)]
            normal_length=sum(x*x for x in n)
            dn=sum(delta[k]*n[k] for k in range(3))/max(normal_length,1e-12)
            targets.append([projected[k]+strength*weights[ep]*(delta[k]-dn*n[k]) for k in range(3)])
        hits.update(zip(moving,surface_hits(mesh_fn,targets)))
    for ep, weight in weights.items():
        p=old[ep];projected,_normal,face,bary=hits[ep]
        if feature_data:
            projected=hard_surface.constrain(p,projected,feature_data)
            projected,face,bary=edit._closest_point_on_mesh(mesh_fn,mesh_dag,projected)
        cn.positions[ep] = projected
        cn.surface_binding[ep] = (face, bary)
        delta = [projected[k]-p[k] for k in range(3)]
        # Translate all incident handles before refitting, avoiding a snap in
        # the curve direction when only one endpoint moves.
        for handle in incident_handles[ep]:
            cn.positions[handle] = [old[handle][k]+delta[k] for k in range(3)]
    route_indices=[si for si,sp in enumerate(cn.splines) if sp[0] in weights or sp[3] in weights]
    if not _fit_relax_routes(cn,route_indices,mesh_fn,mesh_dag,draft):
        for si in route_indices:
            cn.clear_manual_handles(cn.splines[si][1:3])
            context._fit_spline_handles_to_mesh(cn, si, mesh,
                iters=context._FIT_DRAFT_ITERS if draft else context._FIT_ITERS,
                n_samples=context._FIT_DRAFT_SAMPLES if draft else context._FIT_SAMPLES)
    _smooth_junctions(cn, weights, mesh_fn, mesh_dag,
                      amount=min(1., strength*3) if smooth else 1.)
    # Most retopo guides have an identity world transform. Avoid constructing
    # a Maya point and replacement list for every CV in that common case.
    # Exact comparison retains the existing path for even tiny transforms.
    if matrix != om2.MMatrix():
        inverse = matrix.inverse()
        for i, p in enumerate(cn.positions):
            q = om2.MPoint(*p)*inverse
            cn.positions[i] = [q.x, q.y, q.z]
    (_writer if _writer is not None else acc.write)(cn)
    return set(weights)
