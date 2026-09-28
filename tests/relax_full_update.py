"""Fresh-process actual guide write + native mesh evaluation, without a viewport."""
import os,sys,json,time,statistics,traceback,gc
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
root=Path(__file__).resolve().parents[1]
status=1
preview_mode=os.environ.get('ARU_RETOPO_PREVIEW_BENCH')=='1'
original_write=relax.edit.RetopoGuideAccessor.write
if preview_mode:
    def preview_write(self,cn):
        preview_write.last=cn
        cmds.setAttr(self._node+'.editPreviewPositions',[v for p in cn.positions for v in p],type='doubleArray')
    relax.edit.RetopoGuideAccessor.write=preview_write
report_name='relax_numeric_preview' if preview_mode else 'relax_full_update'
try:
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/2027/aru_retopo_mesh_buffer_v4.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-v4-restore-16732.ma',open=True,force=True,prompt=False)
    cmds.undoInfo(state=True)
    node='aruRetopoGuideShape1';native='aruRetopoNative1'
    before=cmds.getAttr(node+'.outNetData')
    weights={int(k):v for k,v in json.loads((root/'tests/relax_benchmark_weights.json').read_text()).items()}
    assert len(weights)==200
    sel=om.MSelectionList();sel.add(native)
    dep=om.MFnDependencyNode(sel.getDependNode(0))
    out=dep.findPlug('outPositions',False)
    mesh=dep.findPlug('outMesh',False)
    rows=[];original=relax.edit._dirty_shape_view
    relax.edit._dirty_shape_view=lambda:None
    def elapsed():return (time.perf_counter()-start)*1000
    gc_events=[]
    def observe(phase,info):gc_events.append((phase,info['generation'],time.perf_counter()))
    gc.callbacks.append(observe)
    try:
        for i in range(16):
            gc_events.clear()
            cmds.undoInfo(openChunk=True,chunkName='Relax full update benchmark')
            try:
                start=time.perf_counter();relax.relax(node,weights)
                write=elapsed();out.asMObject();coordinates=elapsed()
                native_times=cmds.getAttr(native+'.computeMilliseconds')
                mesh.asMObject();total=elapsed()
                rows.append(dict(write_ms=write,coordinate_ms=coordinates-write,mesh_ms=total-coordinates,total_ms=total,native_ms=native_times,gc=[(p,g,(t-start)*1000) for p,g,t in gc_events]))
                if preview_mode and i==15:
                    # Verify final full-data commit produces the same native
                    # mesh as the numeric preview, outside the measured span.
                    preview_points=list(map(tuple,om.MFnMesh(mesh.asMObject()).getPoints()))
                    expected=json.loads(preview_write.last.to_json())
                    original_write(relax.edit.RetopoGuideAccessor(node),preview_write.last)
                    cmds.setAttr(node+'.editPreviewPositions',[],type='doubleArray')
                    assert json.loads(cmds.getAttr(node+'.netData'))==expected
                    assert list(map(tuple,om.MFnMesh(mesh.asMObject()).getPoints()))==preview_points
                    print('NUMERIC PREVIEW / FULL COMMIT EXACT MESH PARITY PASSED')
            finally:cmds.undoInfo(closeChunk=True)
            cmds.undo()
            assert cmds.getAttr(node+'.outNetData')==before
            mesh.asMObject()
    finally:
        relax.edit._dirty_shape_view=original
        gc.callbacks.remove(observe)
    result={'scope':('200 EP relax + numeric preview write + native coordinates + outMesh, no brush or viewport' if preview_mode else '200 EP relax + actual guide write + native coordinates + outMesh, no brush or viewport'),'samples':rows,'median_ms':{k:statistics.median(row[k] for row in rows[2:]) for k in ('write_ms','coordinate_ms','mesh_ms','total_ms')},'restored':True}
    (root/'tests/relax_full_update_2027.json').write_text(json.dumps(result,indent=2))
    # Profile one additional real write separately from the timed samples.
    import cProfile,pstats,io
    profiler=cProfile.Profile()
    original=relax.edit._dirty_shape_view
    relax.edit._dirty_shape_view=lambda:None
    cmds.undoInfo(openChunk=True,chunkName='Relax write profile')
    try:
        profiler.enable();relax.relax(node,weights);profiler.disable()
    finally:
        profiler.disable();relax.edit._dirty_shape_view=original
        cmds.undoInfo(closeChunk=True);cmds.undo()
    assert cmds.getAttr(node+'.outNetData')==before
    text=io.StringIO();pstats.Stats(profiler,stream=text).sort_stats('cumulative').print_stats(45)
    (root/'tests/relax_full_write_profile.txt').write_text(text.getvalue())
    print('FULL UPDATE BENCHMARK',result['median_ms']);status=0
except BaseException:traceback.print_exc()
finally:
    relax.edit.RetopoGuideAccessor.write=original_write
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
