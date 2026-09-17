"""Point preview: legacy final-data parity, lifecycle and Undo."""
import json, tempfile, os
from contextlib import ExitStack
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    mesh=cmds.polyPlane(w=20,h=20,sx=10,sy=10)[0]
    node=cmds.createNode('retopoGuideNode')
    cn=RetopoGuideData.from_dict({'positions':[[-2,0,0],[-1.3,0,0],[-.6,0,0],[0,0,0],[.6,0,0],[1.3,0,0],[2,0,0]],'splines':[(0,1,2,3),(3,4,5,6)]})
    cmds.setAttr(node+'.netData',cn.to_json(),type='string');cmds.setAttr(node+'.meshName',mesh,type='string')
    cmds.setAttr(node+'.controlPoints[0]',.0008,0,0,type='double3')
    original=cmds.getAttr(node+'.netData');before=cmds.getAttr(node+'.outNetData')
    had=cmds.optionVar(exists='retopoGuideContext_node');old=cmds.optionVar(q='retopoGuideContext_node') if had else None
    cmds.optionVar(sv=('retopoGuideContext_node',node))
    from Aru_RetopoTool.editor.curvenet.point_preview import PointPreview
    cached=RetopoGuideData.from_json_cached(original);snapshot=cached.to_json()
    preview=PointPreview(node);owned=preview.read()
    assert owned.to_json()==snapshot
    owned.positions[0][0]+=1
    owned.splines.pop();owned.manual_handles.add(1)
    owned.surface_binding[0]=(0,[(0,1.)])
    if owned.curves:owned.curves[0].clear()
    assert cached.to_json()==snapshot
    preview.cancel()
    assert cmds.getAttr(node+'.outNetData')==before
    results={}
    try:
        for ending in ('legacy','release','exit','cancel','error','save'):
            state=RetopoGuideState();ctx=context.RetopoGuideContext(state);point=[100,100,0]
            def press():
                state.drag_ep=3;state.drag_mirror_ep=None;state.drag_side=None
                state.drag_handle=None;state.ring_cut=None
            with ExitStack() as stack:
                stack.enter_context(patch.object(context,'_state_extra',{}))
                stack.enter_context(patch.object(context,'_ctx',state))
                stack.enter_context(patch.object(ctx,'_press_impl',side_effect=press))
                stack.enter_context(patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else point))
                stack.enter_context(patch.object(context,'_raycast_from_screen',side_effect=lambda x,y,m:[(x-100)*.01,0,.2]))
                stack.enter_context(patch.object(context,'_find_spline_under_screen',return_value=None))
                stack.enter_context(patch.object(edit,'_dirty_shape_view',return_value=None))
                if ending=='legacy':stack.enter_context(patch.object(ctx,'_point_preview_for',return_value=None))
                ctx.press()
                for step in range(3):
                    point[0]=102+step;ctx._drag_impl()
                if ending!='legacy':
                    assert cmds.getAttr(node+'.netData')==original
                    assert cmds.getAttr(node+'.editPreviewPositions')
                    assert ctx._point_save_callback is not None
                if ending=='legacy':results['legacy_draft']=cmds.getAttr(node+'.netData')
                if ending in ('legacy','release'):ctx.release()
                elif ending=='exit':ctx.exit()
                elif ending=='cancel':ctx._cancel_relax()
                elif ending=='error':
                    with patch.object(ctx,'_drag_impl',side_effect=RuntimeError('injected point preview error')):ctx.drag()
                else:
                    previous=cmds.file(q=True,sn=True)
                    with tempfile.TemporaryDirectory(prefix='retopo_point_save_') as folder:
                        cmds.file(rename=os.path.join(folder,'point.ma'))
                        try:cmds.file(save=True,type='mayaAscii',force=True)
                        finally:cmds.file(rename=previous)
                assert not ctx._undo_open
                assert getattr(ctx,'_point_save_callback',None) is None
                assert not cmds.getAttr(node+'.editPreviewPositions')
                if ending in ('legacy','release','exit'):results[ending]=cmds.getAttr(node+'.netData')
                else:assert cmds.getAttr(node+'.outNetData')==before
                finished=cmds.getAttr(node+'.outNetData')
                cmds.undo();assert cmds.getAttr(node+'.outNetData')==before
                cmds.redo();assert cmds.getAttr(node+'.outNetData')==finished,(ending,json.loads(finished)['positions'],json.loads(cmds.getAttr(node+'.outNetData'))['positions'],cmds.getAttr(node+'.editPreviewPositions'))
                assert not cmds.getAttr(node+'.editPreviewPositions')
                cmds.undo();assert cmds.getAttr(node+'.outNetData')==before
        assert results['legacy']==results['release']
        # Tool exit commits the last draft (legacy release additionally refines).
        assert results['exit']==results['legacy_draft']
        print('PASS point numeric preview: legacy release parity, exit, cancel, error, save and Undo')
    finally:
        if had:cmds.optionVar(sv=('retopoGuideContext_node',old))
        else:cmds.optionVar(remove='retopoGuideContext_node')
        cmds.delete(cmds.listRelatives(node,parent=True)[0],mesh)
