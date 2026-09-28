"""Owned C++ halfedge walks with the existing Python return shape."""
import ctypes as C
from array import array
from collections import OrderedDict

_REGION_CACHE = OrderedDict()  # Exact evaluated inputs, at most four networks.
from .native import library
from .stencil_compiler import view

def spline_aliases(positions, splines):
    """Share coincident boundaries after endpoint welding, preserving source IDs.

    Equal endpoints alone are insufficient: distinct curved sides must survive.
    Compare all controls in a common direction with a local roundoff tolerance.
    """
    groups = {}
    aliases = {}
    for i, sp in enumerate(splines):
        direction = 1 if sp[0] < sp[3] else -1
        controls = sp if direction == 1 else tuple(reversed(sp))
        key = (controls[0], controls[3])
        points = [positions[v] for v in controls]
        candidates = groups.get(key, ())
        if candidates:
            extent = max(abs(points[3][k]-points[0][k]) for k in range(3))
            tol = max(1e-10, extent*1e-8)
        for prior, prior_direction, other in candidates:
            if all(abs(a-b) <= tol for p, q in zip(points, other) for a, b in zip(p, q)):
                aliases[i] = (prior, direction*prior_direction)
                break
        else:
            groups.setdefault(key, []).append((i, direction, points))
            aliases[i] = (i, 1)
    return aliases


def canonical_keys(positions, splines, keys):
    import json
    aliases = spline_aliases(positions, splines)
    if all(value == (i, 1) for i, value in aliases.items()):
        return set(keys)
    result = set()
    for key in keys:
        try:
            walk = tuple((aliases.get(i, (i, 1))[0], d*aliases.get(i, (i, 1))[1])
                         for i, d in json.loads(key))
        except (TypeError, ValueError):
            result.add(key)
            continue
        if walk:
            result.add(json.dumps(min(walk[i:]+walk[:i] for i in range(len(walk))),
                                  separators=(',', ':')))
    return result


def regions(positions,splines,normal_at):
    for sp in splines:
        if len(sp)!=4 or any(v<0 or v>=len(positions) for v in sp):raise ValueError('Invalid spline CV indices')
        if sp[0]==sp[3]:raise ValueError('Self-loop spline: insert at least three distinct corners')
    if any(len(p)!=3 for p in positions):raise ValueError('Position requires three coordinates')
    aliases = spline_aliases(positions, splines)
    source_ids = [i for i in range(len(splines)) if aliases[i][0] == i]
    splines = [splines[i] for i in source_ids]
    lib=library();I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
    for name,args,result in (
        ('aru_regions_create',[D,C.c_int,I,C.c_int,D],C.c_void_p),
        ('aru_regions_destroy',[C.c_void_p],None),
        ('aru_regions_size',[C.c_void_p,C.c_int],C.c_int),
        ('aru_regions_copy',[C.c_void_p,C.c_int,I,C.c_int],C.c_int)):
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    points=array('d',(v for p in positions for v in p));controls=array('i',(v for sp in splines for v in sp))
    normals=array('d',[0])*(len(positions)*3)
    for ep in dict.fromkeys(ep for sp in splines for ep in (sp[0],sp[3])):
        normal=array('d',normal_at(positions[ep]))
        if len(normal)!=3:raise ValueError('Normal requires three coordinates')
        normals[ep*3:ep*3+3]=normal
    key=(points.tobytes(), controls.tobytes(), normals.tobytes(), tuple(source_ids))
    cached=_REGION_CACHE.get(key)
    if cached is not None:
        _REGION_CACHE.move_to_end(key)
        return [list(loop) for loop in cached]
    handle=lib.aru_regions_create(view(points),len(positions),view(controls),len(splines),view(normals))
    if not handle:raise ValueError('Invalid curve network geometry')
    try:
        buffers=[]
        for which in range(3):
            size=lib.aru_regions_size(handle,which)
            if size<0:raise RuntimeError('Invalid region buffer')
            values=array('i',[0])*size
            if not lib.aru_regions_copy(handle,which,view(values),size):raise RuntimeError('Cannot copy regions')
            buffers.append(values)
        loops,sides,halfedges=buffers
        if len(loops)==1:raise ValueError('閉じた領域がありません。交点を接続し、3辺以上で領域を囲んでください。')
        result = [[tuple((source_ids[halfedges[k]//2],-1 if halfedges[k]%2 else 1) for k in range(sides[j],sides[j+1]))
                 for j in range(loops[i],loops[i+1])] for i in range(len(loops)-1)]
        _REGION_CACHE[key]=tuple(tuple(loop) for loop in result)
        _REGION_CACHE.move_to_end(key)
        while len(_REGION_CACHE)>4:_REGION_CACHE.popitem(last=False)
        return result
    finally:lib.aru_regions_destroy(handle)
