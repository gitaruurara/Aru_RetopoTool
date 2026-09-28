"""Persistent scalar paint in stable patch coordinates (no Maya dependency)."""
import math
from collections import defaultdict

RESOLUTION=16


from functools import lru_cache


@lru_cache(maxsize=4)
def decoded(raw):
    """Shared read-only paint payload for transfer and native plan evaluation."""
    import json
    return json.loads(raw or '{}')


@lru_cache(maxsize=64)
def _coordinate_faces(n,levels):
    uv=((0.,0.),(1.,0.),(1.,1.),(0.,1.)) if n==4 else tuple(
        (.5+.5*math.cos(2*math.pi*i/n),.5+.5*math.sin(2*math.pi*i/n)) for i in range(n))
    rows=(uv,)
    for _ in range(levels):
        next_rows=[]
        for uv in rows:
            center=(sum(p[0] for p in uv)/len(uv),sum(p[1] for p in uv)/len(uv))
            for i,p in enumerate(uv):
                after=uv[(i+1)%len(uv)];before=uv[i-1]
                next_rows.append((p,((p[0]+after[0])*.5,(p[1]+after[1])*.5),center,
                                  ((p[0]+before[0])*.5,(p[1]+before[1])*.5)))
        rows=tuple(next_rows)
    return rows


def coordinates(plan, keys=None):
    """Follow native face order using shared immutable parameter templates."""
    result={};offset=0
    for key,loop in zip(plan.region_keys,plan.region_loops):
        # Quad subdivision produces n * 4**(levels-1) faces per region.
        # Retain offsets even when this patch carries no paint.
        count = len(loop) * 4**(plan.levels-1)
        if keys is not None and key not in keys:
            offset += count
            continue
        rows=_coordinate_faces(len(loop),plan.levels);values={}
        for face,uv in zip(plan.faces[offset:offset+len(rows)],rows):
            for v,p in zip(face,uv):
                old=values.get(v)
                if old is not None and old!=p and max(abs(old[k]-p[k]) for k in range(2))>1e-10:
                    raise ValueError('Inconsistent patch coordinates')
                values[v]=p
        result[key]=values;offset+=len(rows)
    if offset!=len(plan.faces):raise ValueError('Patch coordinate/face count mismatch')
    return result


def cells(u,v):
    x=max(0.,min(1.,u))*RESOLUTION;y=max(0.,min(1.,v))*RESOLUTION
    a=min(int(x),RESOLUTION-1);b=min(int(y),RESOLUTION-1)
    dx=x-a;dy=y-b
    return [(str((b+j)*(RESOLUTION+1)+a+i),w) for i,j,w in
            ((0,0,(1-dx)*(1-dy)),(1,0,dx*(1-dy)),(1,1,dx*dy),(0,1,(1-dx)*dy)) if w>1e-12]


def sample(field,u,v):
    """Return premultiplied target and coverage; zero coverage inherits defaults."""
    value=coverage=0.
    for index,w in cells(u,v):
        p,a=field.get(index,(0.,0.));value+=w*p;coverage+=w*a
    return value,coverage


def paint(field,u,v,target,opacity):
    target=max(0.,min(1.,float(target)));opacity=max(0.,min(1.,float(opacity)))
    for index,weight in cells(u,v):
        alpha=opacity*weight
        p,a=field.get(index,(0.,0.))
        field[index]=(p*(1-alpha)+target*alpha,a*(1-alpha)+alpha)


def weights(plan,fields,guide_weight=1.):
    base=[guide_weight if i in plan.guide_vertices else 0. for i in range(plan.count)]
    if not fields:return base
    values=defaultdict(list)
    for key,uv in plan.edit_coordinates(fields).items():
        field=fields.get(key)
        if not field:continue
        for v,(u,w) in uv.items():
            value,coverage=sample(field,u,w)
            if coverage>0:values[v].append((value,coverage))
    for v,entries in values.items():
        # Shared seam vertices get one value, independent of face traversal order.
        value=sum(p for p,a in entries)/len(entries);alpha=sum(a for p,a in entries)/len(entries)
        base[v]=max(0.,min(1.,base[v]*(1-alpha)+value))
    return base


def lattice(plan):
    """Sparse bilinear-grid samples anchored to the current patch triangles."""
    result={};coords=plan.edit_coordinates()
    membership=defaultdict(set)
    for key,uv in coords.items():
        for v in uv:membership[v].add(key)
    for face in plan.faces:
        keys=set.intersection(*(membership[v] for v in face))
        for key in keys:
            samples=result.setdefault(key,{})
            for tri in ((face[0],face[1],face[2]),(face[0],face[2],face[3])):
                a,b,c=[coords[key][v] for v in tri]
                det=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1])
                if abs(det)<1e-12:continue
                lo=[max(0,math.ceil(min(p[k] for p in (a,b,c))*RESOLUTION-1e-8)) for k in range(2)]
                hi=[min(RESOLUTION,math.floor(max(p[k] for p in (a,b,c))*RESOLUTION+1e-8)) for k in range(2)]
                for y in range(lo[1],hi[1]+1):
                    for x in range(lo[0],hi[0]+1):
                        index=str(y*(RESOLUTION+1)+x)
                        if index in samples:continue
                        u=x/RESOLUTION;v=y/RESOLUTION;dx=u-a[0];dy=v-a[1]
                        t=(dx*(c[1]-a[1])-dy*(c[0]-a[0]))/det
                        w=((b[0]-a[0])*dy-(b[1]-a[1])*dx)/det
                        if min(t,w,1-t-w)>=-1e-8:samples[index]=(tri,(1-t-w,t,w),(u,v))
    return result
