"""Maya-independent topology planning. Catmull-Clark masks, not OpenSubdiv bindings.

Plans depend on connectivity only; moving guides reuses face and vertex indices.
All coordinates passed to this module are in the same (world) space.
"""
import math
from array import array
from collections import defaultdict


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def unit(v): return mul(v, 1.0 / max(math.sqrt(dot(v, v)), 1e-15))
def mean(points):
    return tuple(sum(p[i] for p in points)/len(points) for i in range(3))


def bezier(positions, spline, t):
    s = 1-t
    weights = (s*s*s, 3*s*s*t, 3*s*t*t, t*t*t)
    return tuple(sum(positions[v][k]*w for v, w in zip(spline, weights)) for k in range(3))


def regions(positions, splines, normal_at):
    """Walk surface-oriented halfedges; discard exterior and dangling walks.

Intersections MUST share endpoint indices. Crossings are not inferred in 3D.
Degree-two chains are collapsed into logical sides, preserving their Béziers.
"""
    incident = defaultdict(list)
    for si, sp in enumerate(splines):
        if len(sp) != 4 or any(v < 0 or v >= len(positions) for v in sp):
            raise ValueError("Invalid spline CV indices")
        if sp[0] == sp[3]:
            raise ValueError("Self-loop spline: insert at least three distinct corners")
        incident[sp[0]].append((si, 1))
        incident[sp[3]].append((si, -1))
    normals={ep:normal_at(positions[ep]) for ep in incident}
    order = {}
    for ep, outgoing in incident.items():
        n = unit(normals[ep])
        u = unit(cross(n, (1, 0, 0) if abs(n[0]) < .8 else (0, 1, 0)))
        v = cross(n, u)
        def angle(h):
            sp = splines[h[0]]
            tangent = sub(positions[sp[1] if h[1] == 1 else sp[2]], positions[ep])
            if dot(tangent, tangent) < 1e-18:
                tangent = sub(positions[sp[3] if h[1] == 1 else sp[0]], positions[ep])
            return math.atan2(dot(tangent, v), dot(tangent, u))
        order[ep] = sorted(outgoing, key=angle)
    visited, loops = set(), []
    for si in range(len(splines)):
        for direction in (1, -1):
            start = (si, direction)
            if start in visited: continue
            h, walk = start, []
            while h not in visited:
                visited.add(h)
                walk.append(h)
                sp = splines[h[0]]
                end = sp[3] if h[1] == 1 else sp[0]
                outgoing = order[end]
                reverse = (h[0], -h[1])
                h = outgoing[(outgoing.index(reverse)-1) % len(outgoing)]
            if h != start or len(walk) < 3: continue
            ids = [splines[i][0 if d == 1 else 3] for i, d in walk]
            if len(set(ids)) != len(ids): continue
            pts = [positions[i] for i in ids]
            center = mean(pts)
            area = (0, 0, 0)
            for a, b in zip(pts, pts[1:]+pts[:1]):
                area = add(area, cross(sub(a, center), sub(b, center)))
            # Local orientation distinguishes the unbounded walk on an open patch.
            n = mean([normals[i] for i in ids])
            if dot(area, n) <= 1e-12: continue
            # Preserve all corners of an isolated loop; collapse degree-two points
            # only when >=3 junctions already provide an unambiguous polygon.
            corners = [j for j, ep in enumerate(ids) if len(incident[ep]) != 2]
            if len(corners) < 3: corners = list(range(len(walk)))
            sides = []
            for j, begin in enumerate(corners):
                end = corners[(j+1) % len(corners)]
                indices = list(range(begin, end if end > begin else end+len(walk)))
                sides.append(tuple(walk[k % len(walk)] for k in indices))
            loops.append(sides)
    # On a wrapping surface the exterior can also pass the average-normal
    # orientation test. Detect a closed shell of candidates and leave its
    # clearly dominant perimeter open. Never arbitrarily remove a comparable
    # cell from a uniformly closed network. Work per component, not globally.
    owners = defaultdict(list)
    for li, loop in enumerate(loops):
        for side in loop:
            for si, _ in side: owners[si].append(li)
    remaining = set(range(len(loops))); excluded = set()
    while remaining:
        component = {remaining.pop()}; pending = list(component)
        while pending:
            li = pending.pop()
            for side in loops[li]:
                for si, _ in side:
                    for neighbor in owners[si]:
                        if neighbor in remaining:
                            remaining.remove(neighbor); component.add(neighbor); pending.append(neighbor)
        edges = {si for li in component for side in loops[li] for si, _ in side}
        if len(component) < 3 or any(len(owners[si]) != 2 for si in edges): continue
        def perimeter(li):
            total = 0.
            for side in loops[li]:
                for si, _ in side:
                    samples = [bezier(positions, splines[si], k/8.) for k in range(9)]
                    total += sum(math.sqrt(dot(sub(b,a),sub(b,a))) for a,b in zip(samples,samples[1:]))
            return total
        ranked = sorted((perimeter(li), li) for li in component)
        if ranked[-1][0] > 1.5*ranked[-2][0]: excluded.add(ranked[-1][1])
    loops = [loop for li, loop in enumerate(loops) if li not in excluded]
    if not loops:
        raise ValueError("閉じた領域がありません。交点を接続し、3辺以上で領域を囲んでください。")
    return loops


def side_point(positions, splines, side, t):
    # Parameter allocation is fixed across edits to avoid vertex index changes.
    x = min(max(t, 0.0), 1.0) * len(side)
    k = min(int(x), len(side)-1)
    si, direction = side[k]
    local = x-k
    return bezier(positions, splines[si], local if direction == 1 else 1-local)


class Plan:
    def __init__(self, positions, splines, normal_at, levels=2, max_faces=200000, selected=None):
        if not 1 <= levels <= 6: raise ValueError("Subdivision must be 1..6")
        loops = [] if selected is not None and not selected else regions(positions, splines, normal_at)
        if selected is not None:
            loops = [loop for loop in loops if patch_key(loop) in selected]
        self.region_keys = [patch_key(loop) for loop in loops]
        endpoints = sorted({splines[s[0][0]][0 if s[0][1] == 1 else 3]
                            for loop in loops for s in loop})
        index = {ep: i for i, ep in enumerate(endpoints)}
        faces, guides = [], {}
        self.guide_vertices = {index[ep]: ("ep", ep) for ep in endpoints}
        for loop in loops:
            face = []
            for side in loop:
                a = index[splines[side[0][0]][0 if side[0][1] == 1 else 3]]
                b = index[splines[side[-1][0]][3 if side[-1][1] == 1 else 0]]
                face.append(a)
                key = tuple(sorted((a, b)))
                canonical = side if a < b else tuple((si, -d) for si, d in reversed(side))
                if key in guides and guides[key][0] != canonical:
                    raise ValueError("Multiple sides share the same corners; add guide intersections")
                guides[key] = (canonical, 0., 1.)
            faces.append(face)
        incidence = defaultdict(int)
        for f in faces:
            for a, b in zip(f, f[1:]+f[:1]): incidence[tuple(sorted((a, b)))] += 1
        if incidence and max(incidence.values()) > 2: raise ValueError("Non-manifold guide regions")
        estimate = sum(map(len, faces)) * 4**(levels-1)
        if estimate > max_faces: raise ValueError("生成面数が上限を超えます。分割レベルを下げてください。")
        self.endpoints = endpoints
        from .subdivision import plan as subdivision_plan
        guide_sides=[value[0] for value in guides.values()]
        self.steps,buffers=subdivision_plan(len(endpoints),faces,guides,levels)
        (flat,self.adj_offsets,self.adj_ids,guide_ids,guide_sources,
         patch_offsets,patch_ids,patch_faces,guide_t,patch_u,patch_v)=buffers
        for vertex,source,t in zip(guide_ids,guide_sources,guide_t):
            self.guide_vertices[vertex]=('side',guide_sides[source],t)
        self.faces=tuple(zip(flat[::4],flat[1::4],flat[2::4],flat[3::4]))
        self.count=len(self.adj_offsets)-1
        self.region_count=len(loops)
        self.patches=[(loops[face],{patch_ids[j]:(patch_u[j],patch_v[j])
                                 for j in range(patch_offsets[i],patch_offsets[i+1])})
                      for i,face in enumerate(patch_faces)]

    def compile_stencil(self,splines):
        """Compose the exact subdivision, guide and Coons linear coefficients once."""
        def accumulate(dst,src,factor):
            for v,w in src.items():dst[v]=dst.get(v,0.)+w*factor
        # Rows are read-only after construction; shared boundary samples can
        # reuse coefficients within this compilation without retaining a cache.
        samples={}
        def sample(side,t):
            key=(side,t)
            if key in samples:return samples[key]
            x=min(max(t,0.),1.)*len(side);k=min(int(x),len(side)-1)
            si,d=side[k];t=x-k if d==1 else 1-(x-k);u=1-t
            row={}
            for v,w in zip(splines[si],(u*u*u,3*u*u*t,3*u*t*t,t*t*t)):
                row[v]=row.get(v,0.)+w
            samples[key]=row
            return row
        # Coons interiors replace subdivision coefficients outright. Walk
        # backwards from remaining outputs so mixed n-gon patches still retain
        # every subdivision dependency, including guide overrides at each level.
        coons={v for _,uv in self.patches for v in uv if v not in self.guide_vertices}
        needed=set(range(self.count))-coons
        levels=[]
        for offsets,ids,weights in reversed(self.steps):
            levels.append(needed)
            needed={ids[j] for i in needed if i not in self.guide_vertices
                    for j in range(offsets[i],offsets[i+1])}
        from .stencil_compiler import Composer
        composer=Composer(self.endpoints)
        try:
            for (offsets,ids,weights),needed in zip(self.steps,reversed(levels)):
                overrides={};requests=[]
                for i in sorted(needed):
                    guide=self.guide_vertices.get(i)
                    if guide is not None:
                        overrides[i]={guide[1]:1.} if guide[0]=='ep' else sample(guide[1],guide[2])
                    else:requests.append(i)
                composer.step(offsets,ids,weights,requests)
                composer.set(overrides)
            points={}
            # Identical patch layouts share coefficient arithmetic within this build.
            # Include CV aliasing and side directions: reused handles and reversed
            # or multi-segment sides must retain their exact accumulation order.
            templates={}
            for sides,uv in self.patches:
                local={}
                layout=[]
                for side in sides:
                    segments=[]
                    for si,d in side:
                        controls=tuple(local.setdefault(cv,len(local)) for cv in splines[si])
                        segments.append((controls,d))
                    layout.append(tuple(segments))
                global_ids=tuple(local)
                interior=sorted(((coord,vertex) for vertex,coord in uv.items()
                                 if vertex not in self.guide_vertices))
                key=(tuple(layout),tuple(coord for coord,_ in interior))
                template=templates.get(key)
                if template is not None:
                    for (_,vertex),row in zip(interior,template):
                        points[vertex]={global_ids[i]:w for i,w in row}
                    continue
                corners=[sample(side,0.) for side in sides]
                template=[]
                for (u,v),vertex in interior:
                    row={}
                    for side,t,factor in ((0,u,1-v),(2,1-u,v),(3,1-v,1-u),(1,v,u)):
                        accumulate(row,sample(sides[side],t),factor)
                    for corner,factor in zip(corners,((1-u)*(1-v),u*(1-v),u*v,(1-u)*v)):
                        accumulate(row,corner,-factor)
                    points[vertex]=row
                    template.append(tuple((local[cv],w) for cv,w in row.items()))
                templates[key]=template
            composer.set(points)
            return composer.packed()
        finally:composer.close()

    def evaluate(self, positions, splines, stencil=None):
        if stencil and hasattr(stencil,'compile'):
            if not hasattr(self,'_compiled_stencil'):
                self._compiled_stencil=stencil.compile(*self.compile_stencil(splines))
            return self._compiled_stencil(positions)
        points = [positions[ep] for ep in self.endpoints]
        for offsets, ids, weights in self.steps:
            if stencil:
                points = stencil(points, offsets, ids, weights)
            else:
                points = [tuple(sum(points[ids[j]][k]*weights[j]
                                    for j in range(offsets[i], offsets[i+1])) for k in range(3))
                          for i in range(len(offsets)-1)]
            for v, guide in self.guide_vertices.items():
                if v >= len(points): continue
                points[v] = positions[guide[1]] if guide[0] == "ep" else side_point(positions, splines, guide[1], guide[2])
        for sides, uv in self.patches:
            corners = [side_point(positions, splines, side, 0.) for side in sides]
            cache = {}
            def sample(side, t):
                key = (side, t)
                if key not in cache:
                    cache[key] = side_point(positions, splines, sides[side], t)
                return cache[key]
            for vertex, (u, v) in uv.items():
                if vertex in self.guide_vertices: continue
                bottom, right = sample(0,u), sample(1,v)
                top, left = sample(2,1-u), sample(3,1-v)
                bilinear = [(1-u)*(1-v)*corners[0][k]+u*(1-v)*corners[1][k]
                            +u*v*corners[2][k]+(1-u)*v*corners[3][k] for k in range(3)]
                points[vertex] = tuple((1-v)*bottom[k]+v*top[k]+(1-u)*left[k]+u*right[k]-bilinear[k]
                                       for k in range(3))
        return points


def patch_key(loop):
    """Directed boundary identity, independent of walk start and side grouping."""
    import json
    walk = tuple(h for side in loop for h in side)
    canonical = min(walk[i:]+walk[:i] for i in range(len(walk)))
    return json.dumps(canonical, separators=(',', ':'))
