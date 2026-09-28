"""Resample saved local edits when guide topology changes; never reuse stale ids."""
import json,math
from maya import cmds
import maya.api.OpenMaya as om
from . import core,local_fields,native,patch_transfer


def barycentric(point,a,b,c):
    u=[b[k]-a[k] for k in range(len(a))];v=[c[k]-a[k] for k in range(len(a))];w=[point[k]-a[k] for k in range(len(a))]
    dot=lambda x,y:sum(a*b for a,b in zip(x,y))
    uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
    det=uu*vv-uv*uv
    if abs(det)<1e-20:return None
    x=(wu*vv-wv*uv)/det;y=(wv*uu-wu*uv)/det
    return (1-x-y,x,y)


def parameter_boundary(cn,loop):
    """Exact directed controls in the same parameter origin used by Plan."""
    if loop is None:return None
    loop=min((loop[i:]+loop[:i] for i in range(len(loop))),
             key=lambda row:tuple(h for side in row for h in side))
    return tuple(tuple(tuple(tuple(cn.positions[v]) for v in
                             (cn.splines[si] if direction==1 else reversed(cn.splines[si])))
                       for si,direction in side) for side in loop)


class Atlas:
    def __init__(self,cn,key,normal,surface,loop=None):
        loops=None
        if loop is not None:
            loops=[min((loop[i:]+loop[:i] for i in range(len(loop))),
                       key=lambda row:tuple(h for side in row for h in side))]
        self.plan=core.Plan(cn.positions,cn.splines,normal,4,selected={key},region_loops=loops)
        if not self.plan.count:raise ValueError('Missing patch atlas')
        values=self.plan.evaluate(cn.positions,cn.splines,native.stencil)
        self.points,_,_=surface.project(values,guard=False)
        self.uv=self.plan.edit_coordinates()[key]
        self.data=om.MFnMeshData().create()
        obj=om.MFnMesh().create([om.MPoint(*p) for p in self.points],[4]*len(self.plan.faces),[v for f in self.plan.faces for v in f],parent=self.data)
        self.fn=om.MFnMesh(obj);counts,ids=self.fn.getTriangles();self.triangles=[];offset=0
        for count in counts:
            self.triangles.append([tuple(ids[offset+j:offset+j+3]) for j in range(0,count*3,3)]);offset+=count*3

    def closest(self,point):
        closest,face=self.fn.getClosestPoint(om.MPoint(*point),om.MSpace.kObject)
        q=tuple(closest)[:3];candidates=[]
        for tri in self.triangles[face]:
            bary=barycentric(q,*[self.points[v] for v in tri])
            if bary is None:continue
            clamped=[max(0.,w) for w in bary];total=sum(clamped);clamped=[w/total for w in clamped]
            reconstructed=[sum(self.points[v][k]*w for v,w in zip(tri,clamped)) for k in range(3)]
            distance=sum((q[k]-reconstructed[k])**2 for k in range(3))
            uv=tuple(sum(self.uv[v][k]*w for v,w in zip(tri,clamped)) for k in range(2))
            candidates.append((distance,uv))
        if not candidates:raise ValueError('Degenerate patch atlas')
        return min(candidates)[1],sum((q[k]-point[k])**2 for k in range(3))

    def closest_many(self,points):
        """Keep Maya's closest-face choice; batch the triangle/UV arithmetic."""
        import numpy as np
        if not points:return [],[]
        if any(len(triangles)!=2 for triangles in self.triangles):
            rows=[self.closest(point) for point in points]
            return [row[0] for row in rows],[row[1] for row in rows]
        if not hasattr(self,'_triangle_array'):
            self._triangle_array=np.asarray(self.triangles,dtype=np.intp)
            self._point_array=np.asarray(self.points,dtype=float)
            self._uv_array=np.asarray([self.uv[i] for i in range(self.plan.count)],dtype=float)
        hits=[self.fn.getClosestPoint(om.MPoint(*point),om.MSpace.kObject) for point in points]
        q=np.asarray([tuple(point)[:3] for point,_ in hits])
        triangles=self._triangle_array[[face for _,face in hits]]
        vertices=self._point_array[triangles]
        a=vertices[:,:,0];u=vertices[:,:,1]-a;v=vertices[:,:,2]-a;w=q[:,None,:]-a
        dot=lambda x,y:np.sum(x*y,axis=2)
        uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
        det=uu*vv-uv*uv;valid=np.abs(det)>=1e-20
        if np.any(~np.any(valid,axis=1)):raise ValueError('Degenerate patch atlas')
        safe=np.where(valid,det,1.)
        x=(wu*vv-wv*uv)/safe;y=(wv*uu-wu*uv)/safe
        bary=np.maximum(np.stack((1-x-y,x,y),axis=2),0.)
        bary/=np.sum(bary,axis=2)[:,:,None]
        reconstructed=np.sum(vertices*bary[:,:,:,None],axis=2)
        distance=np.sum((q[:,None,:]-reconstructed)**2,axis=2)
        distance=np.where(valid,distance,np.inf)
        coordinates=np.sum(self._uv_array[triangles]*bary[:,:,:,None],axis=2)
        # Match min((distance, (u,v)), ...) including equal-distance ties.
        uv_less=(coordinates[:,1,0]<coordinates[:,0,0])|((coordinates[:,1,0]==coordinates[:,0,0])&(coordinates[:,1,1]<coordinates[:,0,1]))
        second=(distance[:,1]<distance[:,0])|((distance[:,1]==distance[:,0])&uv_less)
        chosen=coordinates[np.arange(len(points)),second.astype(np.intp)]
        squared=np.sum((q-np.asarray(points))**2,axis=1)
        return chosen.tolist(),squared.tolist()

    def point(self,uv):
        for triangles in self.triangles:
            for tri in triangles:
                bary=barycentric(uv,*[self.uv[v] for v in tri])
                if bary is not None and min(bary)>-1e-8:
                    return tuple(sum(self.points[v][k]*w for v,w in zip(tri,bary)) for k in range(3))
        raise ValueError('Parameter outside patch')


def prepare(guide,new,context=None):
    context=patch_transfer.SceneTransfer(guide,new) if context is None else context
    payload=[]
    for node in set(context.nodes):
        field=local_fields.decoded(cmds.getAttr(node+'.influenceField') or '{}')
        reductions=json.loads(cmds.getAttr(node+'.loopReductions') or '[]')
        if field or reductions:payload.append((node,field,reductions))
    if not payload:return []
    before,after=context.before,context.after
    mesh,normal=context.mesh,context.normal
    surface=None
    transfer=context.analysis()
    def get_surface():
        nonlocal surface
        if surface is None:
            mesh_path=om.MSelectionList().add(mesh).getDagPath(0)
            if mesh_path.node().hasFn(om.MFn.kTransform):mesh_path.extendToShape()
            ref=om.MFnMesh(mesh_path);_,tri=ref.getTriangles()
            surface=native.Surface([tuple(p)[:3] for p in ref.getPoints(om.MSpace.kWorld)],list(tri))
        return surface
    old_atlas={};new_atlas={};mapping={};updates=[]
    old_loops=None
    new_loops=dict(zip(transfer.loop_keys,transfer.loops))
    def children(key):
        if key not in mapping:mapping[key]=transfer.targets(key)
        return mapping[key]
    def previous_loops():
        nonlocal old_loops
        if old_loops is None:
            old_loops={core.patch_key(loop):loop for loop in core.regions(before.positions,before.splines,normal)}
        return old_loops
    def same_parameters(key,target):
        old_loop=previous_loops().get(key);new_loop=new_loops.get(target)
        return old_loop is not None and new_loop is not None and parameter_boundary(before,old_loop)==parameter_boundary(after,new_loop)
    def source(key):
        if key not in old_atlas:
            old_atlas[key]=Atlas(before,key,normal,get_surface(),previous_loops().get(key))
        return old_atlas[key]
    def destination(key):
        if key not in new_atlas:new_atlas[key]=Atlas(after,key,normal,get_surface(),new_loops.get(key))
        return new_atlas[key]
    try:
        for node,fields,reductions in payload:
            new_fields={};new_reductions=[]
            for key,field in fields.items():
                targets=children(key)
                if targets=={key}:new_fields[key]=field;continue
                for target in targets:
                    if same_parameters(key,target):
                        new_fields[target]=field;continue
                    atlas=destination(target);samples=local_fields.lattice(atlas.plan)[target];result={}
                    points=[tuple(sum(atlas.points[v][k]*w for v,w in zip(tri,bary)) for k in range(3)) for tri,bary,uv in samples.values()]
                    points,_,_=surface.project(points,guard=False)
                    coordinates,_=source(key).closest_many(points)
                    for index,uv in zip(samples,coordinates):
                        value,alpha=local_fields.sample(field,*uv)
                        if alpha>1e-10:result[index]=(value,alpha)
                    if result:new_fields[target]=result
            for request in reductions:
                key=request['patch'];targets=children(key)
                if targets=={key}:new_reductions.append(request);continue
                if not targets:continue
                if len(targets)==1:
                    target=next(iter(targets))
                    if same_parameters(key,target):
                        new_reductions.append(dict(request,patch=target));continue
                atlas=source(key);points=[atlas.point(uv) for uv in request['edge']]
                center=tuple((points[0][k]+points[1][k])*.5 for k in range(3))
                target=min(targets,key=lambda name:destination(name).closest(center)[1])
                uv=[destination(target).closest(point)[0] for point in points]
                new_reductions.append({'patch':target,'edge':uv})
            if new_fields!=fields or new_reductions!=reductions:
                updates.append((node,new_fields,new_reductions))
    finally:
        if surface is not None:surface.close()
    return updates
