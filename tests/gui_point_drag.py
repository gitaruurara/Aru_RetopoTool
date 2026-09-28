"""Scripted screen-coordinate MMB drag through the real context handler."""
import json, time, statistics, traceback, hashlib
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_context as context, curve_net_edit as edit, curve_net_draw as draw, curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState


def run(numeric=True, brush_start=(1546,1145), delta=(2,0)):
    node='aruRetopoGuideShape1'
    before=cmds.getAttr(node+'.outNetData')
    exists=cmds.optionVar(exists='retopoGuideContext_node')
    previous=cmds.optionVar(q='retopoGuideContext_node') if exists else None
    report={'scope':'real MMB context drag/release with scripted draggerContext queries; current viewport display, not physical mouse input'}
    opened=False;pending=False;handler=None
    try:
        cn,_=relax._world_data(node)
        weights=relax.brush_weights(node,*brush_start)
        assert weights,'No visible EP at test screen location'
        ep=max(weights,key=weights.get)
        screen=edit._world_to_screen(cn.positions[ep]);assert screen
        report['ep']=ep;report['start_screen']=list(screen)
        state=RetopoGuideState();state.drag_ep=ep;state.drag_mirror_ep=None;state.drag_side=None
        state.drag_handle=None;state.ring_cut=None
        handler=context.RetopoGuideContext(state)
        position=[screen[0],screen[1],0.]
        original_query=cmds.draggerContext
        def query(*args,**kwargs):
            if kwargs.get('q') and kwargs.get('button'):return 2
            if kwargs.get('q') and kwargs.get('dragPoint'):return position
            return original_query(*args,**kwargs)
        current=[];rows=[]
        def timed(fn,name):
            def call(*args,**kwargs):
                start=time.perf_counter()
                try:return fn(*args,**kwargs)
                finally:current.append((name,(time.perf_counter()-start)*1000))
            return call
        cmds.optionVar(sv=('retopoGuideContext_node',node))
        cmds.undoInfo(openChunk=True,chunkName='Retopo point drag diagnostic');opened=True;pending=True
        with ExitStack() as stack:
            if not numeric:stack.enter_context(patch.object(handler,'_point_preview_for',return_value=None))
            stack.enter_context(patch.object(cmds,'draggerContext',query))
            stack.enter_context(patch.object(context,'_ctx',state))
            stack.enter_context(patch.object(context,'_state_extra',{}))
            stack.enter_context(patch.object(context,'_DRAG_CN_CACHE',{}))
            stack.enter_context(patch.object(draw,'_ctx',state))
            for name in ('_find_spline_under_screen','_recompute_handles_for_ep','_smooth_moved_ep_routes','_commit_net_data','_attach_ep_to_spline'):
                stack.enter_context(patch.object(context,name,timed(getattr(context,name),name)))
            from Aru_RetopoTool import patch_transfer
            stack.enter_context(patch.object(patch_transfer,'prepare',timed(patch_transfer.prepare,'patch_transfer')))
            for name in ('_dirty_shape_view','_reset_control_points'):
                stack.enter_context(patch.object(edit,name,timed(getattr(edit,name),name)))
            for i in range(8):
                position[:]=[screen[0]+delta[0]*(i+1),screen[1]+delta[1]*(i+1),0.]
                current.clear();start=time.perf_counter();handler._drag_impl()
                rows.append({'ms':(time.perf_counter()-start)*1000,'stages':list(current)})
            report['merge_target']=state.merge_target
            report['hover_spline']=context._state_get(state,'hover_spline')
            current.clear();start=time.perf_counter();handler._release_impl()
            report['release_ms']=(time.perf_counter()-start)*1000
            report['release_stages']=list(current)
        cmds.undoInfo(closeChunk=True);opened=False
        report['samples']=rows;report['median_ms']=statistics.median(r['ms'] for r in rows)
        final=cmds.getAttr(node+'.outNetData')
        report['mesh_status']={name:cmds.getAttr(name+'.status') for name in cmds.ls(type='aruRetopoMesh') or []}
        report['plan_status']={name:cmds.getAttr(name+'.status') for name in cmds.ls(type='aruRetopoPlan') or []}
        import math
        from array import array
        import maya.api.OpenMaya as om
        report['buffers']={}
        for name in cmds.ls(type='aruRetopoMeshBuffer') or []:
            selection=om.MSelectionList();selection.add(name)
            fn=om.MFnDependencyNode(selection.getDependNode(0))
            coords=om.MFnDoubleArrayData(fn.findPlug('outPositions',False).asMObject()).array()
            counts=om.MFnIntArrayData(fn.findPlug('faceCounts',False).asMObject()).array()
            indices=om.MFnIntArrayData(fn.findPlug('faceIndices',False).asMObject()).array()
            assert len(coords)>0 and len(coords)%3==0 and all(math.isfinite(v) for v in coords)
            assert sum(counts)==len(indices) and all(0<=v<len(coords)//3 for v in indices)
            report['buffers'][name]={'vertices':len(coords)//3,'faces':len(counts),
                'positions_hash':hashlib.sha256(array('d',coords).tobytes()).hexdigest(),
                'topology_hash':hashlib.sha256(array('i',indices).tobytes()).hexdigest()}
        report['changed']=final!=before
        report['final_hash']=hashlib.sha256(final.encode('utf-8')).hexdigest()
        Path(__file__).with_name('gui_point_drag_final_'+('numeric' if numeric else 'legacy')+'.json').write_text(final)
        report['topology_counts']=[{key:len(json.loads(raw)[key]) for key in ('positions','splines')} for raw in (before,final)]
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if handler is not None:handler._finish_point(False)
        if opened:cmds.undoInfo(closeChunk=True)
        if pending:cmds.undo()
        if exists:cmds.optionVar(sv=('retopoGuideContext_node',previous))
        else:cmds.optionVar(remove='retopoGuideContext_node')
        cmds.refresh(force=True)
        report['restored']=cmds.getAttr(node+'.outNetData')==before
        report['numeric_preview']=numeric
        path=Path(__file__).with_suffix('.json')
        if not numeric:path=path.with_name(path.stem+'_legacy.json')
        path.write_text(json.dumps(report,indent=2))
