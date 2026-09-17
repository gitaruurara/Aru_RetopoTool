"""Bridge validation in an isolated Maya process."""
from maya import cmds
import maya.api.OpenMaya as om
from types import SimpleNamespace
from Aru_RetopoTool import construction as c, guides, maya_api as api
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def rejected(fn,text):
    try:fn()
    except ValueError as exc:assert text in str(exc),str(exc)
    else:raise AssertionError('Expected rejection: '+text)


def run():
    sphere=cmds.polySphere(r=3,sx=48,sy=32)[0]
    fn,dag=edit._get_mesh_fn(sphere)
    cn=RetopoGuideData();chains=[]
    for offset,phase in ((.3,0),(1.2,45)):
        points=context._compute_ring_by_plane(fn,dag,[0,0,0],[0,1,0],8,phase=phase,offset=offset)
        eps=[cn.add_cv(p) for p in points];edges=[]
        for a,b in zip(eps,eps[1:]+eps[:1]):edges.append((a,b,context._add_spline_to_cn(cn,sphere,a,b)))
        chains.append(edges)
    cn.classify_endpoints();original=cn.to_dict()
    first,second=chains
    shift,reverse=c.best_alignment(cn,first,second)
    assert shift!=0 or reverse
    keys=c.bridge(cn,sphere,first,second,shift,reverse)
    assert len(keys)==8 and len(cn.endpoint_indices())==16
    assert cn.positions[:len(original['positions'])]==original['positions']
    assert len(cn.splines)==24
    rejected(lambda:c.bridge(cn,sphere,first,second,shift,reverse),'既存カーブ')
    rejected(lambda:c.bridge_pairs(first,first),'共有')
    rejected(lambda:c.bridge_pairs(first,second[:-1]),'閉じたリング')
    guide=guides.create(sphere);acc=edit.RetopoGuideAccessor(guide);acc.write(RetopoGuideData.from_dict(original))
    output,node=api.create(guide,sphere)
    for with_faces in (False,True):
        fake=SimpleNamespace(guide=guide,node=node,pending=(cn,om.MMatrix(),keys,'test'),signature=lambda:'test',
                             faces=SimpleNamespace(isChecked=lambda:with_faces),cancel=lambda:None,status=SimpleNamespace(setText=lambda value:None))
        before=cmds.getAttr(guide+'.netData')
        c.ConstructionWindow.commit(fake)
        assert len(acc.read().splines)==24
        assert cmds.polyEvaluate(output,face=True)==(128 if with_faces else 0)
        cmds.undo();assert cmds.getAttr(guide+'.netData')==before
        assert cmds.polyEvaluate(output,face=True)==0
    cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],sphere)
    print('PASS ring bridge alignment, stable CVs, duplicate rejection, faces option, Undo')
    plane=cmds.polyPlane(w=10,h=10,sx=10,sy=10)[0]
    cn=RetopoGuideData();chains=[]
    for z in (0,1):
        eps=[cn.add_cv([x,0,z]) for x in (-1,0,1)];edges=[]
        for a,b in zip(eps,eps[1:]):edges.append((a,b,context._add_spline_to_cn(cn,plane,a,b)))
        chains.append(edges)
    cn.classify_endpoints()
    first,second=chains
    reversed_second=[(b,a,si) for a,b,si in reversed(second)]
    assert c.best_alignment(cn,first,reversed_second)==(0,True)
    rejected(lambda:c.bridge_pairs(first,second[:-1]),'ポイント数')
    rejected(lambda:c.bridge_pairs(first,second,1),'ずらし')
    keys=c.bridge(cn,plane,first,reversed_second,reverse=True)
    assert len(keys)==2 and len(cn.endpoint_indices())==6
    cmds.delete(plane)
    print('PASS open bridge direction reversal and unequal-count rejection')
