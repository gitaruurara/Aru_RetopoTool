"""Gesture tests in disposable Maya; pointer projection is deterministic."""
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import drag_extrude as d, guides, maya_api as api
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    plane=cmds.polyPlane(w=10,h=10,sx=10,sy=10)[0]
    cn=RetopoGuideData()
    for p in [(-1,0,0),(0,0,0),(1,0,0)]:cn.add_cv(p)
    for a,b in [(0,1),(1,2)]:d.context._add_spline_to_cn(cn,plane,a,b)
    cn.classify_endpoints()
    guide=guides.create(plane);accessor=d.edit.RetopoGuideAccessor(guide);accessor.write(cn)
    output,node=api.create(guide,plane)
    cmds.select(guide)
    d._ctx.sel_ep=None
    initial=cmds.getAttr(guide+'.netData')
    xy=[100,100]
    with patch.object(d,'mouse',side_effect=lambda:tuple(xy)), patch.object(d.edit,'make_visibility_test',return_value=None), patch.object(d.edit,'_world_to_screen',side_effect=lambda p:(100+p[0]*30,100)), patch.object(d.context,'_screen_to_view_plane',side_effect=lambda x,y,a:[0,0,(y-100)/30.]):
        gesture=d.Gesture(node)
        gesture.finish();assert cmds.getAttr(guide+'.netData')==initial
        xy[1]=130;gesture.update(force=True)
        assert gesture.pending and cmds.getAttr(guide+'.netData')==initial
        xy[1]=100;gesture.finish();assert gesture.pending is None
        assert cmds.getAttr(guide+'.netData')==initial
        xy[1]=130;gesture.update(force=True);gesture.clear()
        assert cmds.getAttr(guide+'.netData')==initial
        gesture.finish()
        assert len(accessor.read().endpoint_indices())==6
        assert cmds.polyEvaluate(output,face=True)==32
        cmds.undo()
        assert cmds.getAttr(guide+'.netData')==initial
        assert cmds.polyEvaluate(output,face=True)==0
        gesture.clear()
    cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],plane)
    d.selected_points.clear()
    print('PASS drag preview, click without motion, return to origin, cancel, commit and single Undo')
