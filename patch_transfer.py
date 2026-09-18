"""Transfer confirmed regions across guide splits without filling unselected space."""
import json
from collections import defaultdict
from . import core


def transfer(old,new,keys,normal):
    if not keys:return set()
    try: loops=core.regions(new.positions,new.splines,normal)
    except ValueError:return set()
    parents=getattr(new,'_retopo_parents',None)
    mapping={}
    def close(a,b):return sum((x-y)**2 for x,y in zip(a,b))<1e-12
    for i,sp in enumerate(new.splines):
        if parents is not None and i in parents and parents[i] is not None:
            if parents[i]<len(old.splines):mapping[i]=(parents[i],1)
            continue
        for j,prior in enumerate(old.splines):
            a,b=old.positions[prior[0]],old.positions[prior[3]]
            p,q=new.positions[sp[0]],new.positions[sp[3]]
            if close(a,p) and close(b,q):mapping[i]=(j,1);break
            if close(a,q) and close(b,p):mapping[i]=(j,-1);break
    children=defaultdict(set)
    for i,(parent,_) in mapping.items():children[parent].add(i)
    loop_keys=[core.patch_key(loop) for loop in loops]
    owners=defaultdict(list)
    for li,loop in enumerate(loops):
        for side in loop:
            for si,d in side:owners[si].append((li,d))
    result=set()
    for key in keys:
        boundary=dict(json.loads(key))
        if any(parent not in children for parent in boundary):continue
        walls=set().union(*(children[parent] for parent in boundary))
        seeds={li for i in walls for li,d in owners[i] if d*mapping[i][1]==boundary[mapping[i][0]]}
        visited=set(seeds);pending=list(seeds)
        while pending:
            li=pending.pop()
            for side in loops[li]:
                for si,_ in side:
                    if si in walls:continue
                    for neighbor,_ in owners[si]:
                        if neighbor not in visited:visited.add(neighbor);pending.append(neighbor)
        result.update(loop_keys[i] for i in visited)
    return result


def prepare(guide,new):
    from maya import cmds
    import maya.api.OpenMaya as om
    from .editor.curvenet.curve_net_data import RetopoGuideData
    from .editor.curvenet import curve_net_edit as edit
    nodes=cmds.listConnections(guide+'.outNetData',s=False,d=True,type='aruRetopoMesh') or []
    if not nodes:return []
    # Position-only edits cannot alter the confirmed patch identifiers.
    base=RetopoGuideData.from_json_cached(cmds.getAttr(guide+'.netData'))
    if base.splines==new.splines:return []
    old=RetopoGuideData.from_json(cmds.getAttr(guide+'.outNetData'))
    if old.splines==new.splines:return []
    mesh=edit.RetopoGuideAccessor(guide).mesh_name
    fn,_=edit._get_mesh_fn(mesh)
    sel=om.MSelectionList();sel.add(guide);matrix=sel.getDagPath(0).inclusiveMatrix()
    # Region orientation is evaluated in world space, including rotated guides.
    before=RetopoGuideData.from_dict(old.to_dict());after=RetopoGuideData.from_dict(new.to_dict())
    if hasattr(new,'_retopo_parents'):after._retopo_parents=dict(new._retopo_parents)
    for cn in (before,after):
        for i,p in enumerate(cn.positions):
            q=om.MPoint(*p)*matrix;cn.positions[i]=[q.x,q.y,q.z]
    normal=lambda p:edit._get_normal_at_point(fn,p)
    updates=[]
    for node in set(nodes):
        keys=set(json.loads(cmds.getAttr(node+'.selectedPatches') or '[]'))
        if keys:updates.append((node,transfer(before,after,keys,normal)))
    return updates
