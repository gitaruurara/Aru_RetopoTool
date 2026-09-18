"""Maya snapshots and transactional previews for local retopo edits."""
import json,math
from maya import cmds
import maya.api.OpenMaya as om
from . import core,density,local_fields,native,maya_api as api
from .editor.curvenet import curve_net_edit as edit,curve_net_symmetry as sym
from .editor.curvenet.curve_net_relax import _world_data


def read(node,name,default):return json.loads(cmds.getAttr(node+'.'+name) or default)


class PreviewValue:
    """Non-undoable in-flight value, then one command-based commit; cancel on save."""
    def __init__(self,node,attribute):
        self.node=node;self.attribute=attribute;self.closed=False
        self.plug=om.MSelectionList().add(node+'.'+attribute).getPlug(0)
        self.original=self.plug.asString();self.current=self.original
        self.callback=om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave,self._before_save)

    def _before_save(self,*unused):self.cancel()

    def write(self,value):
        if self.closed:raise RuntimeError('Local edit preview is closed')
        self.current=json.dumps(value,separators=(',',':'),sort_keys=True)
        self.plug.setString(self.current)

    def cancel(self):
        if self.closed:return
        self.closed=True
        om.MMessage.removeCallback(self.callback)
        if cmds.objExists(self.node+'.'+self.attribute):self.plug.setString(self.original)

    def commit(self,label):
        if self.closed:return
        value=self.current;self.cancel()
        default='[]' if self.attribute=='loopReductions' else '{}'
        if json.loads(value or default)!=json.loads(self.original or default):
            with api.undo_chunk(label):cmds.setAttr(self.node+'.'+self.attribute,value,type='string')


class Snapshot:
    def __init__(self,node,extra_keys=()):
        self.node=node;self.surface=None;self._plans={}
        self.guide=cmds.listConnections(node+'.guideData',s=True,d=False,shapes=True)[0]
        self.cn,_=_world_data(self.guide);self.mesh=edit.RetopoGuideAccessor(self.guide).mesh_name
        self.selected=set(read(node,'selectedPatches','[]'));keys=self.selected|set(extra_keys)
        from .symmetry_ops import patch_keys
        keys=patch_keys(self.cn,self.mesh,keys)
        dep=om.MFnDependencyNode(om.MSelectionList().add(node).getDependNode(0))
        fn=om.MFnMesh(dep.findPlug('referenceMesh',False).asMDataHandle().asMeshTransformed())
        _,tri=fn.getTriangles();self.surface=native.Surface([tuple(p)[:3] for p in fn.getPoints()],list(tri))
        try:
            eps=sorted(self.cn.endpoint_indices());points=[self.cn.positions[v] for v in eps]
            _,_,normals=self.surface.project(points,guard=False);lookup={tuple(p):n for p,n in zip(points,normals)}
            self.base=core.Plan(self.cn.positions,self.cn.splines,lambda p:lookup[tuple(p)],cmds.getAttr(node+'.subdivisions'),selected=keys)
            self.fields=read(node,'influenceField','{}');self.reductions=read(node,'loopReductions','[]')
            self.guide_weight=cmds.getAttr(node+'.guideWeight')
            self.iterations=cmds.getAttr(node+'.relaxIterations');self.strength=cmds.getAttr(node+'.relaxStrength')
            self.pairs=self.symmetry_pairs()
        except BaseException:self.close();raise

    def close(self):
        if self.surface:self.surface.close();self.surface=None

    def evaluate(self,reductions=None,fields=None):
        requests=self.reductions if reductions is None else reductions
        key=json.dumps(requests,sort_keys=True)
        if key not in self._plans:self._plans[key]=density.apply(self.base,requests)
        plan=self._plans[key]
        values=plan.evaluate(self.cn.positions,self.cn.splines,native.stencil)
        weights=local_fields.weights(plan,self.fields if fields is None else fields,self.guide_weight)
        values,_=self.surface.relax(values,plan,self.iterations,self.strength,guard=False,weights_override=weights)
        return plan,values,weights

    def symmetry_pairs(self,axis=None,space=None):
        axis=sym.get_axis() if axis is None else axis
        if not axis:return {}
        loops=self.base.region_loops;keys=self.base.region_keys
        corners=[[self.cn.splines[side[0][0]][0 if side[0][1]==1 else 3] for side in loop] for loop in loops]
        by_corners={frozenset(row):i for i,row in enumerate(corners)}
        tol=max(edit._snap_radius(self.mesh)*1e-4,1e-6)
        eps=set(v for row in corners for v in row);mirror={}
        for v in eps:
            point=sym.mirror_point(self.cn.positions[v],self.mesh,axis,space)
            mirror[v]=next((j for j in eps if sum((self.cn.positions[j][k]-point[k])**2 for k in range(3))<tol*tol),None)
        result={}
        def regular(n):return [(0,0),(1,0),(1,1),(0,1)] if n==4 else [(.5+.5*math.cos(2*math.pi*i/n),.5+.5*math.sin(2*math.pi*i/n)) for i in range(n)]
        for i,row in enumerate(corners):
            mapped=[mirror[v] for v in row];target=by_corners.get(frozenset(mapped))
            if target is None or len(row)!=len(corners[target]):continue
            source=regular(len(row));dest=[regular(len(row))[corners[target].index(v)] for v in mapped]
            a,b,c=source[:3];x,y,z=dest[:3]
            det=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            # Store affine transform, not closures tied to a live Maya object.
            m=[((y[k]-x[k])*(c[1]-a[1])-(z[k]-x[k])*(b[1]-a[1]))/det for k in range(2)]
            n=[((z[k]-x[k])*(b[0]-a[0])-(y[k]-x[k])*(c[0]-a[0]))/det for k in range(2)]
            offset=[x[k]-m[k]*a[0]-n[k]*a[1] for k in range(2)]
            result[keys[i]]=(keys[target],m,n,offset)
        return result

    def mirrored_uv(self,key,uv):
        pair=self.pairs.get(key)
        if pair is None:return None
        target,m,n,offset=pair
        return target,tuple(offset[k]+m[k]*uv[0]+n[k]*uv[1] for k in range(2))

    def mirrored_request(self,request):
        a=self.mirrored_uv(request['patch'],request['edge'][0]);b=self.mirrored_uv(request['patch'],request['edge'][1])
        if a is None or b is None:return None
        return {'patch':a[0],'edge':[list(a[1]),list(b[1])]}

    def paint_samples(self):
        base_values=self.base.evaluate(self.cn.positions,self.cn.splines,native.stencil)
        weights=local_fields.weights(self.base,self.fields,self.guide_weight)
        base_values,_=self.surface.relax(base_values,self.base,self.iterations,self.strength,guard=False,weights_override=weights)
        records=[];positions=[]
        for key,samples in local_fields.lattice(self.base).items():
            if key not in self.selected:continue
            for index,(vertices,bary,uv) in samples.items():
                records.append((key,uv))
                positions.append(tuple(sum(base_values[v][k]*w for v,w in zip(vertices,bary)) for k in range(3)))
        projected,_,_=self.surface.project(positions,guard=False)
        return records,projected


def mirror_saved(node,axis,space,source_sign,mode):
    fields=read(node,'influenceField','{}');requests=read(node,'loopReductions','[]')
    if not fields and not requests:return
    snapshot=Snapshot(node)
    try:
        snapshot.pairs=snapshot.symmetry_pairs(axis,space)
        lattice=local_fields.lattice(snapshot.base)
        positions=snapshot.base.evaluate(snapshot.cn.positions,snapshot.cn.splines,native.stencil)
        result=json.loads(json.dumps(fields))
        for key,samples in lattice.items():
            if key not in snapshot.pairs:continue
            target=result.setdefault(key,{})
            for index,(vertices,bary,uv) in samples.items():
                point=tuple(sum(positions[v][k]*w for v,w in zip(vertices,bary)) for k in range(3))
                if sym.plane_coord(point,snapshot.mesh,axis,space)*source_sign>=-1e-7:continue
                pair=snapshot.mirrored_uv(key,uv)
                if pair:
                    value,alpha=local_fields.sample(fields.get(pair[0],{}),*pair[1])
                    if alpha>1e-10:target[index]=(value,alpha)
                    else:target.pop(index,None)
        result={key:field for key,field in result.items() if field}
        # Requests are mirrored only if their source seed is on the chosen half.
        topology=density.Topology(snapshot.base.faces);sources=[];retained=[]
        for request in requests:
            try:
                seed=density.locate(snapshot.base,request,topology)
                point=tuple(sum(positions[v][k] for v in seed)*.5 for k in range(3))
                side=sym.plane_coord(point,snapshot.mesh,axis,space)*source_sign
            except ValueError:
                retained.append(request);continue
            if side>=-1e-7:sources.append(request)
            if mode=='add' or side>=-1e-7:retained.append(request)
        for request in sources:
            mirrored=snapshot.mirrored_request(request)
            if not mirrored:continue
            before=density.apply(snapshot.base,retained);after=density.apply(snapshot.base,retained+[mirrored])
            if len(getattr(after,'applied',()))>len(getattr(before,'applied',())):retained.append(mirrored)
        cmds.setAttr(node+'.influenceField',json.dumps(result),type='string')
        cmds.setAttr(node+'.loopReductions',json.dumps(retained),type='string')
    finally:snapshot.close()
