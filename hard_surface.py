"""Feature guides and corner preservation for faceted reference meshes."""
import math
from maya import cmds
import maya.api.OpenMaya as om
from . import core

OPTION='aruRetopoHardSurface'

def enabled():
    return cmds.optionVar(exists=OPTION) and bool(cmds.optionVar(q=OPTION))


def mesh_fn(mesh):
    s=om.MSelectionList();s.add(mesh);p=s.getDagPath(0)
    if p.node().hasFn(om.MFn.kTransform):p.extendToShape()
    return om.MFnMesh(p)


def features(mesh,angle=35.):
    fn=mesh_fn(mesh);points=[tuple(p)[:3] for p in fn.getPoints(om.MSpace.kWorld)]
    normals=[fn.getPolygonNormal(i,om.MSpace.kWorld).normal() for i in range(fn.numPolygons)]
    it=om.MItMeshEdge(fn.dagPath());edges=[]
    while not it.isDone():
        faces=it.getConnectedFaces()
        if len(faces)==1 or (len(faces)==2 and normals[faces[0]]*normals[faces[1]]<math.cos(math.radians(angle))):
            edges.append((it.vertexId(0),it.vertexId(1)))
        it.next()
    return points,edges


def constrain(point,target,data):
    points,edges=data
    if not edges:return target
    scale=max(math.dist(points[a],points[b]) for a,b in edges)
    tol=max(scale*1e-4,1e-6)
    incident={}
    for a,b in edges:
        incident.setdefault(a,[]).append(b);incident.setdefault(b,[]).append(a)
    for v,neighbors in incident.items():
        if math.dist(point,points[v])<=tol:
            # Junctions and corners stay pinned. Collinear edge subdivisions slide.
            if len(neighbors)!=2:return list(points[v])
            a=core.unit(core.sub(points[neighbors[0]],points[v]));b=core.unit(core.sub(points[neighbors[1]],points[v]))
            if core.dot(a,b)>-.999:return list(points[v])
    def closest(p,a,b):
        vec=core.sub(b,a);t=max(0.,min(1.,core.dot(core.sub(p,a),vec)/max(core.dot(vec,vec),1e-20)))
        return core.add(a,core.mul(vec,t))
    hits=[(math.dist(point,closest(point,points[a],points[b])),a,b) for a,b in edges]
    distance,a,b=min(hits)
    if distance<=tol:return list(closest(target,points[a],points[b]))
    return target


def straight_fit(cn,si,mesh):
    if not enabled():return False
    sp=cn.splines[si]
    if any(i in cn.manual_handles for i in sp[1:3]):return False
    fn=mesh_fn(mesh);a,b=cn.positions[sp[0]],cn.positions[sp[3]]
    length=math.dist(a,b);tol=max(length*1e-5,1e-7)
    for t in (.2,.4,.5,.6,.8):
        p=core.add(core.mul(a,1-t),core.mul(b,t));q,_=fn.getClosestPoint(om.MPoint(*p),om.MSpace.kWorld)
        if math.dist(p,tuple(q)[:3])>tol:return False
    cn.positions[sp[1]]=list(core.add(core.mul(a,2/3),core.mul(b,1/3)))
    cn.positions[sp[2]]=list(core.add(core.mul(a,1/3),core.mul(b,2/3)))
    return True


def corner_samples(loop,sampled,order_only=False):
    """Keep arc-length samples and insert geometric corners in cyclic order."""
    if not enabled() and not order_only:return sampled
    lengths=[math.dist(a,b) for a,b in zip(loop,loop[1:]+loop[:1])]
    offsets=[0.]
    for length in lengths:offsets.append(offsets[-1]+length)
    items=[]
    for p in sampled:
        best=None
        for i,a in enumerate(loop):
            b=loop[(i+1)%len(loop)];v=core.sub(b,a)
            t=max(0.,min(1.,core.dot(core.sub(p,a),v)/max(core.dot(v,v),1e-20)))
            q=core.add(a,core.mul(v,t));entry=(math.dist(p,q),offsets[i]+t*lengths[i],p)
            if best is None or entry[0]<best[0]:best=entry
        items.append((best[1],p))
    for i,p in enumerate(loop):
        a=core.unit(core.sub(p,loop[i-1]));b=core.unit(core.sub(loop[(i+1)%len(loop)],p))
        if enabled() and core.dot(a,b)<math.cos(math.radians(35)):
            if not any(math.dist(p,q)<1e-6 for _,q in items):items.append((offsets[i],p))
    return [list(p) for _,p in sorted(items,key=lambda item:item[0])]


def create_guides(node):
    from .drag_extrude import selection
    from .editor.curvenet import curve_net_edit as edit
    from . import maya_api as api
    guide,cn,matrix,_=selection(node);mesh=edit.RetopoGuideAccessor(guide).mesh_name
    points,edges=features(mesh)
    if not edges:raise ValueError('35度以上の稜線または開いた境界がありません。')
    mapping={};eps=set(cn.endpoint_indices());count=0
    for a,b in edges:
        for v in (a,b):
            if v not in mapping:
                found=next((i for i in eps if math.dist(cn.positions[i],points[v])<1e-6),None)
                mapping[v]=cn.add_cv(points[v]) if found is None else found
                eps.add(mapping[v])
        a,b=mapping[a],mapping[b]
        if any({sp[0],sp[3]}=={a,b} for sp in cn.splines):continue
        si=cn.add_spline_two_endpoints(a,b)
        count+=1
    cn.classify_endpoints();inv=matrix.inverse()
    for i,p in enumerate(cn.positions):
        q=om.MPoint(*p)*inv;cn.positions[i]=[q.x,q.y,q.z]
    with api.undo_chunk('Aru Retopo: feature guides'):edit.RetopoGuideAccessor(guide).write(cn)
    return count
