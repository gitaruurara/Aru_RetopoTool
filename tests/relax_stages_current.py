"""Large continuous-stroke comparison; numeric update only, no viewport."""
import os,sys,json,time,statistics,traceback
import numpy as np
import inspect
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
root=Path(__file__).resolve().parents[1];status=1
refresh=relax.edit._dirty_shape_view
try:
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/'+cmds.about(version=True)+'/aru_retopo_mesh_buffer_numeric.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-numeric-isolated-20260918.ma',open=True,force=True,prompt=False)
    node='aruRetopoGuideShape1';native='aruRetopoNative1'
    before=cmds.getAttr(node+'.outNetData')
    weights={int(k):v for k,v in json.loads((root/'tests/relax_benchmark_weights.json').read_text()).items()}
    assert len(weights)==200
    selection=om.MSelectionList();selection.add(native)
    mesh=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outMesh',False)
    relax.edit._dirty_shape_view=lambda:None
    import cProfile,pstats,io
    from Aru_RetopoTool.editor.curvenet import maya_projector as projector
    buckets={};originals=[]
    def instrument(owner,name):
        original=getattr(owner,name);originals.append((owner,name,original))
        key=owner.__name__+'.'+name
        def measured(*args,**kwargs):
            start=time.perf_counter()
            try:return original(*args,**kwargs)
            finally:buckets[key]=buckets.get(key,0)+(time.perf_counter()-start)*1000
        setattr(owner,name,measured)
    for owner,names in ((relax,('_world_data','relax','_fit_relax_routes','_smooth_junctions','_fit_junction_lengths')),(projector,('surface_hits','normals_array','points_array','fit_routes'))):
        for name in names:
            if hasattr(owner,name):instrument(owner,name)
    rows=[]
    for repeat in range(3):
        cmds.undoInfo(openChunk=True);stroke=RelaxPreview(node)
        try:
            for i in range(8):
                buckets.clear();start=time.perf_counter();stroke.apply(weights)
                calc=(time.perf_counter()-start)*1000;mesh.asMObject()
                if repeat==2:rows.append(dict(calc_ms=calc,total_ms=(time.perf_counter()-start)*1000,stages=dict(buckets)))
            stroke.commit()
        finally:
            if not stroke.closed:stroke.cancel()
            cmds.undoInfo(closeChunk=True)
        cmds.undo();assert cmds.getAttr(node+'.outNetData')==before;mesh.asMObject()
    for owner,name,original in originals:setattr(owner,name,original)
    cmds.undoInfo(openChunk=True);stroke=RelaxPreview(node);profile=cProfile.Profile()
    try:
        for i in range(8):profile.runcall(stroke.apply,weights);mesh.asMObject()
        stroke.commit()
    finally:
        if not stroke.closed:stroke.cancel()
        cmds.undoInfo(closeChunk=True)
    cmds.undo();assert cmds.getAttr(node+'.outNetData')==before
    output=io.StringIO();pstats.Stats(profile,stream=output).sort_stats('cumtime').print_stats(35)
    (root/'tests/relax_stages_current.txt').write_text(output.getvalue())
    summary={key:statistics.median(row['stages'].get(key,0) for row in rows[1:]) for key in rows[-1]['stages']}
    summary['calc_ms']=statistics.median(row['calc_ms'] for row in rows[1:]);summary['total_ms']=statistics.median(row['total_ms'] for row in rows[1:])
    (root/'tests/relax_stages_current.json').write_text(json.dumps(dict(summary=summary,samples=rows),indent=2))
    print(json.dumps(summary));status=0
except BaseException:traceback.print_exc()
finally:
    relax.edit._dirty_shape_view=refresh
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
