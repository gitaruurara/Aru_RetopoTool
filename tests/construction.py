"""Run in disposable mayapy; validates ring sampling and extrusion topology."""
import math
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_context as context, curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool import construction,core


def run():
    sphere=cmds.polySphere(r=3,sx=48,sy=32)[0]
    fn,dag=edit._get_mesh_fn(sphere)
    equator=context._compute_ring_by_plane(fn,dag,[0,0,0],[0,1,0],8,phase=0,offset=0)
    assert len(equator)==8
    for count in (3,8,12,24):
        pts=context._compute_ring_by_plane(fn,dag,[0,0,0],[0,1,0],count,phase=0,offset=.23)
        assert len(pts)==count,(count,len(pts))
        assert max(abs(p[1]-.23) for p in pts)<1e-5
    shifted=context._compute_ring_by_plane(fn,dag,[0,0,0],[0,1,0],12,phase=30,offset=.23)
    original=context._compute_ring_by_plane(fn,dag,[0,0,0],[0,1,0],12,phase=0,offset=.23)
    assert max(abs(a-b) for a,b in zip(shifted[0],original[1]))<1e-5
    print('PASS ring counts, cut offset, phase rotation')
    cn=RetopoGuideData()
    for p in original:cn.add_cv(p)
    for i in range(12):context._add_spline_to_cn(cn,sphere,i,(i+1)%12)
    cn.classify_endpoints()
    snapshot=[list(p) for p in cn.positions]
    edges=construction.boundary_edges(cn,{0},set(),lambda p:edit._get_normal_at_point(fn,p))
    keys=construction.extrude(cn,sphere,edges,[0,.5,0])
    assert len(keys)==12
    assert cn.positions[:len(snapshot)]==snapshot
    assert len(cn.endpoint_indices())==24
    plan=core.Plan(cn.positions,cn.splines,lambda p:edit._get_normal_at_point(fn,p),2,selected=keys)
    assert plan.region_count==12 and len(plan.faces)==192
    print('PASS closed boundary extrusion, 12 quads bands, original CVs retained')
    plane=cmds.polyPlane(w=10,h=10,sx=10,sy=10)[0]
    cn=RetopoGuideData()
    for p in [(-1,0,0),(0,0,0),(1,0,0)]:cn.add_cv(p)
    for a,b in [(0,1),(1,2)]:context._add_spline_to_cn(cn,plane,a,b)
    cn.classify_endpoints()
    base=cn.to_dict()
    edges=construction.boundary_edges(cn,{0,1,2},set(),lambda p:(0,1,0))
    keys=construction.extrude(cn,plane,edges,[0,0,1])
    assert len(keys)==2
    assert len(cn.endpoint_indices())==6
    print('PASS open boundary extrusion')
    from Aru_RetopoTool import guides,maya_api as api
    import maya.api.OpenMaya as om
    from types import SimpleNamespace
    guide=guides.create(plane)
    accessor=edit.RetopoGuideAccessor(guide);accessor.write(RetopoGuideData.from_dict(base))
    output,node=api.create(guide,plane)
    initial=cmds.getAttr(guide+'.netData')
    fake=SimpleNamespace(guide=guide,node=node,pending=(cn,om.MMatrix(),keys,'test'),
                         signature=lambda:'test',faces=SimpleNamespace(isChecked=lambda:True),
                         cancel=lambda:None,status=SimpleNamespace(setText=lambda value:None))
    construction.ConstructionWindow.commit(fake)
    assert cmds.polyEvaluate(output,face=True)==32
    cmds.undo()
    assert cmds.getAttr(guide+'.netData')==initial
    assert cmds.polyEvaluate(output,face=True)==0
    fake.faces=SimpleNamespace(isChecked=lambda:False)
    construction.ConstructionWindow.commit(fake)
    assert len(accessor.read().endpoint_indices())==6
    assert cmds.polyEvaluate(output,face=True)==0
    cmds.undo()
    assert cmds.getAttr(guide+'.netData')==initial
    cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0])
    print('PASS extrusion commit with/without faces and single-step Undo')
    cmds.delete(sphere,plane)
