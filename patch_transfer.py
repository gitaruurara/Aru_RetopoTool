"""Transfer confirmed regions across guide splits without filling unselected space."""
import json
from collections import defaultdict
from . import core


def _python_endpoint_matches(old,new):
    from itertools import product
    import math
    # A spatial endpoint index preserves the original first-match and
    # strict distance semantics, including reversed and duplicate edges.
    cell=lambda p:tuple(math.floor(x/1e-6) for x in p)
    buckets=defaultdict(set)
    for j,sp in enumerate(old.splines):
        for ep in (sp[0],sp[3]):buckets[cell(old.positions[ep])].add(j)
    offsets=tuple(product((-1,0,1),repeat=3))
    def close(a,b):return sum((x-y)**2 for x,y in zip(a,b))<1e-12
    candidate_cache={}
    mapping={}
    for i,sp in enumerate(new.splines):
        p,q=new.positions[sp[0]],new.positions[sp[3]]
        base=cell(p)
        if base not in candidate_cache:
            candidates=set()
            for dx,dy,dz in offsets:
                candidates.update(buckets.get((base[0]+dx,base[1]+dy,base[2]+dz),()))
            candidate_cache[base]=sorted(candidates)
        for j in candidate_cache[base]:
            prior=old.splines[j];a,b=old.positions[prior[0]],old.positions[prior[3]]
            if close(a,p) and close(b,q):mapping[i]=((j,1),);break
            if close(a,q) and close(b,p):mapping[i]=((j,-1),);break
    return mapping


class Transfer:
    """One topology analysis shared by every saved patch in a commit."""
    def __init__(self,old,new,normal):
        from .regions_native import spline_aliases
        self.aliases=spline_aliases(old.positions,old.splines)
        try:self.loops=core.regions(new.positions,new.splines,normal)
        except ValueError:self.loops=[]
        parents=getattr(new,'_retopo_parents',None)
        sources=getattr(new,'_retopo_spline_sources',None)
        from .transfer_native import matches
        mapping=matches(old,new)
        if mapping is None:mapping=_python_endpoint_matches(old,new)
        for i in range(len(new.splines)):
            if sources is not None and i in sources:
                mapping[i]=sources[i]
            elif parents is not None and i in parents and parents[i] is not None:
                mapping.pop(i,None)
                if parents[i]<len(old.splines):mapping[i]=((parents[i],1),)
        self.mapping=mapping
        self.children=defaultdict(set)
        for i,ancestors in mapping.items():
            for parent,_ in ancestors:self.children[parent].add(i)
        self.loop_keys=[core.patch_key(loop) for loop in self.loops]
        self.owners=defaultdict(list)
        for li,loop in enumerate(self.loops):
            for side in loop:
                for si,d in side:self.owners[si].append((li,d))
        self.cache={}

    def targets(self,key):
        if key in self.cache:return self.cache[key]
        walk=tuple((self.aliases.get(i,(i,1))[0],d*self.aliases.get(i,(i,1))[1]) for i,d in json.loads(key))
        boundary=dict(walk)
        children=self.children;owners=self.owners;mapping=self.mapping
        if any(parent not in children for parent in boundary):result=set()
        else:
            walls=set().union(*(children[parent] for parent in boundary))
            seeds={li for i in walls for li,d in owners[i] if any(parent in boundary and d*sign==boundary[parent] for parent,sign in mapping[i])}
            visited=set(seeds);pending=list(seeds)
            while pending:
                li=pending.pop()
                for side in self.loops[li]:
                    for si,_ in side:
                        if si in walls:continue
                        for neighbor,_ in owners[si]:
                            if neighbor not in visited:visited.add(neighbor);pending.append(neighbor)
            result={self.loop_keys[i] for i in visited}
        self.cache[key]=result
        return result

    def transfer(self,keys):
        result=set()
        for key in keys:result.update(self.targets(key))
        return result


def transfer(old,new,keys,normal):
    if not keys:return set()
    return Transfer(old,new,normal).transfer(keys)


class SceneTransfer:
    def __init__(self,guide,new):
        from maya import cmds
        import maya.api.OpenMaya as om
        from .editor.curvenet.curve_net_data import RetopoGuideData
        from .editor.curvenet import curve_net_edit as edit
        self.nodes=cmds.listConnections(guide+'.outNetData',s=False,d=True,type='aruRetopoMesh') or []
        self.index=None
        if not self.nodes:return
        base=RetopoGuideData.from_json_cached(cmds.getAttr(guide+'.netData'))
        if base.splines==new.splines:self.nodes=[];return
        old=RetopoGuideData.from_json_cached(cmds.getAttr(guide+'.outNetData'))
        if old.splines==new.splines:self.nodes=[];return
        self.mesh=edit.RetopoGuideAccessor(guide).mesh_name
        fn,_=edit._get_mesh_fn(self.mesh)
        matrix=om.MSelectionList().add(guide).getDagPath(0).inclusiveMatrix()
        from types import SimpleNamespace
        self.before=SimpleNamespace(positions=old.positions,splines=old.splines)
        self.after=SimpleNamespace(positions=new.positions,splines=new.splines)
        for name in ('_retopo_parents','_retopo_spline_sources'):
            if hasattr(new,name):setattr(self.after,name,dict(getattr(new,name)))
        if matrix!=om.MMatrix():
            for cn in (self.before,self.after):
                cn.positions=[list(om.MPoint(*p)*matrix)[:3] for p in cn.positions]
        # Batch identical intersector normal queries once for both topologies.
        from .editor.curvenet.maya_projector import normals_array
        points=list(dict.fromkeys(tuple(cn.positions[ep]) for cn in (self.before,self.after) for sp in cn.splines for ep in (sp[0],sp[3])))
        normals=dict(zip(points,normals_array(fn,points).tolist()))
        def normal(p):
            key=tuple(p)
            if key not in normals:normals[key]=edit._get_normal_at_point(fn,p)
            return normals[key]
        self.normal=normal

    def analysis(self):
        if self.index is None:self.index=Transfer(self.before,self.after,self.normal)
        return self.index


def prepare(guide,new,context=None):
    from maya import cmds
    context=SceneTransfer(guide,new) if context is None else context
    updates=[]
    for node in set(context.nodes):
        keys=set(json.loads(cmds.getAttr(node+'.selectedPatches') or '[]'))
        if keys:
            transferred=context.analysis().transfer(keys)
            if transferred!=keys:updates.append((node,transferred))
    return updates


def prepare_all(guide,new):
    from . import local_edit_transfer
    context=SceneTransfer(guide,new)
    return prepare(guide,new,context),local_edit_transfer.prepare(guide,new,context)
