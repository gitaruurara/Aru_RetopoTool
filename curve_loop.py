"""Preview and insert a guide loop through opposite sides of quad patches."""
from collections import defaultdict
from maya import cmds
from . import core,construction,drag_extrude,maya_api as api
from .editor.curvenet import curve_net_context as context,curve_net_edit as edit
from .editor.curvenet.curve_net_data import RetopoGuideData


def trace(points,splines,normal,seed,t):
    loops=core.regions(points,splines,normal)
    owners=defaultdict(list)
    for li,loop in enumerate(loops):
        if len(loop)!=4:continue
        for side_i,side in enumerate(loop):
            for k,(si,d) in enumerate(side):owners[si].append((li,side_i,k,d))
    cuts={seed:max(.001,min(.999,t))};pending=[seed];visited=set();links=[]
    while pending:
        si=pending.pop()
        for li,side_i,k,d in owners[si]:
            if li in visited:continue
            visited.add(li);loop=loops[li];side=loop[side_i]
            fraction=(k+(cuts[si] if d==1 else 1-cuts[si]))/len(side)
            opposite=loop[(side_i+2)%4];x=(1-fraction)*len(opposite)
            j=min(int(x),len(opposite)-1);other,direction=opposite[j]
            ot=x-j if direction==1 else 1-(x-j)
            ot=max(.001,min(.999,ot))
            if other in cuts and abs(cuts[other]-ot)>1e-5:
                raise ValueError('Loop returns to its start at a different position')
            if other not in cuts:cuts[other]=ot;pending.append(other)
            links.append((si,other))
    if not links:raise ValueError('このカーブに接する四辺パッチがありません。')
    return cuts,links


def build(cn,mesh,seed,t):
    fn,_=edit._get_mesh_fn(mesh);normal=lambda p:edit._get_normal_at_point(fn,p)
    cuts,links=trace(cn.positions,cn.splines,normal,seed,t)
    paths=[(cuts,links)]
    # Resolve both paths first, including two cuts on a self-mirrored boundary.
    from .symmetry_ops import mirrored_splines
    from .editor.curvenet import curve_net_symmetry as sym
    mapping=mirrored_splines(cn,mesh,[seed])
    partner=mapping.get(seed)
    if partner is not None:
        source=cn.splines[seed];target=cn.splines[partner]
        mirrored=sym.mirror_point(cn.positions[source[0]],mesh)
        same=sum((mirrored[k]-cn.positions[target[0]][k])**2 for k in range(3))<1e-8
        paths.append(trace(cn.positions,cn.splines,normal,partner,t if same else 1-t))
    parameters=defaultdict(set);connections=set()
    for cuts,links in paths:
        for si,value in cuts.items():parameters[si].add(round(value,9))
        for a,b in links:connections.add(tuple(sorted(((a,round(cuts[a],9)),(b,round(cuts[b],9))))))
    endpoints={}
    for si,values in sorted(parameters.items()):
        current=si;previous=0.
        for value in sorted(values):
            tail=len(cn.splines)
            endpoints[(si,value)]=context._split_spline_at(cn,current,(value-previous)/(1-previous),mesh)
            previous=value;current=tail
    added=[]
    for a,b in sorted(connections):
        if not context._spline_exists(cn,endpoints[a],endpoints[b]):
            added.append(context._add_spline_to_cn(cn,mesh,endpoints[a],endpoints[b]))
    cn.classify_endpoints()
    return added


class Preview:
    def __init__(self,node):self.node=node;self.pending=None;self.key=None
    def clear(self):
        for path in drag_extrude.overlays(self.node):
            construction.preview_lines.pop(path,None);construction.preview_points.pop(path,None)
        self.pending=None;self.key=None
    def update(self):
        xy=drag_extrude.mouse()
        if xy is None:self.clear();return
        guide,cn,matrix,_=drag_extrude.selection(self.node)
        mesh=edit.RetopoGuideAccessor(guide).mesh_name
        hit=context._find_spline_under_screen(cn,*xy,mesh_name=mesh)
        if hit is None:self.clear();return
        raw=cmds.getAttr(guide+'.outNetData');key=(raw,hit[0],round(hit[1],4))
        if key==self.key:return
        self.clear()
        added=build(cn,mesh,hit[0],hit[1])
        lines=[]
        for si in added:
            pts=[core.bezier(cn.positions,cn.splines[si],i/24.) for i in range(25)]
            for a,b in zip(pts,pts[1:]):lines.extend((a,b))
        for path in drag_extrude.overlays(self.node):construction.preview_lines[path]=lines
        self.pending=(guide,cn,matrix,raw);self.key=key
        cmds.refresh(force=True)
    def commit(self):
        self.update()
        if self.pending is None:return
        import maya.api.OpenMaya as om
        guide,cn,matrix,raw=self.pending
        if cmds.getAttr(guide+'.outNetData')!=raw:raise ValueError('Guide changed during loop preview')
        inverse=matrix.inverse()
        cn.positions=[list(om.MPoint(*p)*inverse)[:3] for p in cn.positions]
        with api.undo_chunk('Aru Retopo: insert guide loop'):context._commit_net_data(guide,cn)
        self.clear()
