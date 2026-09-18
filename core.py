"""Maya-independent topology planning. Catmull-Clark masks, not OpenSubdiv bindings.

Plans depend on connectivity only; moving guides reuses face and vertex indices.
All coordinates passed to this module are in the same (world) space.
"""
import math
from array import array
from collections import defaultdict
from .regions_native import regions


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
        # A stable parameter origin is required by saved paint/reduction data.
        loops=[min((loop[i:]+loop[:i] for i in range(len(loop))),
                   key=lambda row:tuple(h for side in row for h in side)) for loop in loops]
        self.region_loops=loops
        self.levels=levels
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
        self._guide_sides=guide_sides
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

    def edit_coordinates(self):
        """Per-region vertex coordinates, including n-gons; independent of shape."""
        if not hasattr(self,'_edit_coordinates'):
            from .local_fields import coordinates
            self._edit_coordinates=coordinates(self)
        return self._edit_coordinates

    def compile_stencil(self,splines):
        return self.steps.compile(self.endpoints,splines,self._guide_sides)

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
