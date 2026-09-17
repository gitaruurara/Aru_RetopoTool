"""Continuous numeric relaxation vs ordinary writes, metadata and Undo."""
import json
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
from Aru_RetopoTool.tests.test_core import polygon


def run():
    mesh=cmds.polySphere(r=3,sx=32,sy=24,ch=False)[0]
    node=guides.create(mesh);parent=cmds.listRelatives(node,parent=True)[0]
    p,s=polygon(8,height=1)
    data=dict(positions=p,splines=s,manual_handles=[sp[1] for sp in s])
    cmds.setAttr(node+'.netData',json.dumps(data),type='string')
    cmds.setAttr(parent+'.translate',.1,.2,-.1,type='double3')
    cmds.setAttr(parent+'.rotateY',17.)
    cmds.setAttr(node+'.controlPoints[0]',.01,.02,.03,type='double3')
    original=cmds.getAttr(node+'.netData');evaluated=cmds.getAttr(node+'.outNetData')
    strokes=({0:.7,1:.2},{4:.8,5:.3},{2:.5,3:.6})
    affected=set().union(*strokes)
    try:
        with patch.object(relax.edit,'_dirty_shape_view',return_value=None):
            cmds.undoInfo(openChunk=True,chunkName='baseline relax stroke')
            try:
                for weights in strokes:relax.relax(node,weights)
                relax.relax(node,{ep:1. for ep in affected},draft=False,smooth=False)
                expected=json.loads(cmds.getAttr(node+'.netData'))
                expected_eval=cmds.getAttr(node+'.outNetData')
            finally:cmds.undoInfo(closeChunk=True)
            cmds.undo();assert cmds.getAttr(node+'.outNetData')==evaluated
            cmds.undoInfo(openChunk=True,chunkName='numeric relax stroke')
            try:
                stroke=RelaxPreview(node)
                for weights in strokes:
                    stroke.apply(weights)
                    pending_json=stroke.pending.to_json()
                    snapshot,_=stroke.world()
                    index=next(i for i,b in enumerate(snapshot.surface_binding) if b and b[1])
                    snapshot.surface_binding[index][1].clear()
                    snapshot.manual_handles.add(99999)
                    snapshot.positions[0][0]+=100
                    assert stroke.pending.to_json()==pending_json,'World snapshot changed pending metadata'
                    assert cmds.getAttr(node+'.netData')==original
                with patch.object(relax.edit,'_dirty_shape_view',return_value=None) as draw:
                    stroke.commit()
                    assert draw.call_count==1,'Commit drew intermediate preview states'
                assert json.loads(cmds.getAttr(node+'.netData'))==expected
                assert cmds.getAttr(node+'.outNetData')==expected_eval
                assert not cmds.getAttr(node+'.editPreviewPositions')
            finally:cmds.undoInfo(closeChunk=True)
            cmds.undo();assert cmds.getAttr(node+'.outNetData')==evaluated
            cmds.redo();assert cmds.getAttr(node+'.outNetData')==expected_eval
            assert not cmds.getAttr(node+'.editPreviewPositions')
            cmds.undo()
            cmds.undoInfo(openChunk=True,chunkName='cancel numeric relax')
            try:
                stroke=RelaxPreview(node);stroke.apply(strokes[0]);stroke.cancel();stroke.cancel()
                assert cmds.getAttr(node+'.outNetData')==evaluated
                assert cmds.getAttr(node+'.netData')==original
                assert tuple(cmds.getAttr(node+'.controlPoints[0]')[0])==(.01,.02,.03)
            finally:cmds.undoInfo(closeChunk=True)
        print('PASS continuous numeric relax, disjoint metadata, transformed CP, commit, cancel, single Undo/Redo')
        reuse_node=guides.create(mesh)
        cmds.setAttr(reuse_node+'.netData',json.dumps(data),type='string')
        reuse_before=cmds.getAttr(reuse_node+'.outNetData')
        outputs={}
        with patch.object(relax.edit,'_dirty_shape_view',return_value=None):
            for mode in ('ordinary','reuse'):
                cmds.undoInfo(openChunk=True,chunkName='identity '+mode)
                try:
                    preview=RelaxPreview(reuse_node) if mode=='reuse' else None
                    owners=[]
                    for weights in strokes:
                        if preview:
                            preview.apply(weights);owners.append(id(preview.pending))
                            saved=preview.pending.to_json()
                            snapshot,_=preview.world();snapshot.positions[0][0]+=10
                            assert preview.pending.to_json()==saved
                        else:relax.relax(reuse_node,weights)
                    if preview:
                        assert len(set(owners))==1,'Stroke did not reuse owned data'
                        saved=preview.pending.to_json()
                        with patch.object(relax,'brush_weights',return_value={}):
                            assert not preview.brush(0,0)
                        assert preview.pending.to_json()==saved
                        preview.commit()
                    else:relax.relax(reuse_node,{ep:1. for ep in affected},draft=False,smooth=False)
                    outputs[mode]=cmds.getAttr(reuse_node+'.outNetData')
                finally:cmds.undoInfo(closeChunk=True)
                cmds.undo();assert cmds.getAttr(reuse_node+'.outNetData')==reuse_before
            assert outputs['ordinary']==outputs['reuse']
            cmds.undoInfo(openChunk=True,chunkName='reuse error cancellation')
            try:
                preview=RelaxPreview(reuse_node);preview.apply(strokes[0])
                def fail(*args,**kwargs):
                    kwargs['_world'][0].positions[0][0]+=100
                    raise RuntimeError('injected partial owned-data edit')
                with patch.object(relax,'relax',side_effect=fail):
                    try:preview.apply(strokes[1])
                    except RuntimeError:pass
                    else:raise AssertionError('Injected error not raised')
                assert preview.closed and preview.pending is None
                assert not cmds.getAttr(reuse_node+'.editPreviewPositions')
                assert cmds.getAttr(reuse_node+'.outNetData')==reuse_before
            finally:cmds.undoInfo(closeChunk=True)
        print('PASS owned preview reuse, empty brush, isolated snapshot, failure cancellation, exact final data')
        from Aru_RetopoTool.editor.curvenet import curve_net_context as context
        from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
        import tempfile,os
        committed=None
        for ending in ('release','exit','save','cancel','error'):
            ctx=context.RetopoGuideContext(RetopoGuideState())
            def begin():
                context._state_set(ctx._s,'relax_stroke',dict(node=node,snapped=0,origin=(100,100),last=(100,100),moved=False,affected=set()))
            with patch.object(ctx,'_press_impl',side_effect=begin), patch.object(relax,'brush_weights',return_value=strokes[0]), patch.object(relax.edit,'_dirty_shape_view',return_value=None):
                ctx.press();ctx._relax_drag(110,100)
                assert ctx._undo_open and ctx._relax_save_callback is not None
                assert cmds.getAttr(node+'.netData')==original
                assert cmds.getAttr(node+'.editPreviewPositions')
                if ending=='release':ctx.release()
                elif ending=='exit':ctx.exit()
                elif ending=='save':
                    previous_name=cmds.file(q=True,sn=True)
                    target=os.path.join(tempfile.mkdtemp(prefix='retopo_preview_'),'saved.ma')
                    cmds.file(rename=target)
                    try:cmds.file(save=True,type='mayaAscii',force=True)
                    finally:cmds.file(rename=previous_name)
                elif ending=='cancel':ctx.stop_scriptjob()
                else:
                    with patch.object(ctx,'_drag_impl',side_effect=RuntimeError('injected preview drag error')):ctx.drag()
                assert not ctx._undo_open and ctx._relax_save_callback is None
                assert not cmds.getAttr(node+'.editPreviewPositions')
                if ending in ('cancel','error','save'):
                    assert cmds.getAttr(node+'.outNetData')==evaluated
                else:
                    current=cmds.getAttr(node+'.netData')
                    if committed is None:committed=current
                    assert current==committed
                finished=cmds.getAttr(node+'.outNetData')
                cmds.undo()
                actual=cmds.getAttr(node+'.outNetData')
                assert actual==evaluated,(ending,cmds.getAttr(node+'.netData')==original,cmds.getAttr(node+'.controlPoints[0]'),cmds.getAttr(node+'.editPreviewPositions'),json.loads(actual)['positions'][:2],json.loads(evaluated)['positions'][:2])
                cmds.redo();assert cmds.getAttr(node+'.outNetData')==finished
                assert not cmds.getAttr(node+'.editPreviewPositions')
                cmds.undo();assert cmds.getAttr(node+'.outNetData')==evaluated
        print('PASS preview context release, tool exit, actual save callback, cancel, injected error and Undo/Redo')
    finally:cmds.delete(parent,mesh)
