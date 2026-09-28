"""Real RelaxPreview stroke; independent processes select native mesh backend."""
import os,sys,json,time,statistics,traceback,hashlib,struct
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
root=Path(__file__).resolve().parents[1];status=1
version=os.environ['ARU_TEST_BUFFER_VERSION']
refresh=relax.edit._dirty_shape_view
try:
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/'+cmds.about(version=True)+'/aru_retopo_mesh_buffer_'+version+'.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-numeric-isolated-20260918.ma',open=True,force=True,prompt=False)
    owners=[p for p in cmds.pluginInfo(q=True,listPlugins=True) or [] if 'aruRetopoMeshBuffer' in (cmds.pluginInfo(p,q=True,dependNode=True) or [])]
    assert len(owners)==1,owners
    loaded=cmds.pluginInfo(owners[0],q=True,path=True)
    assert Path(loaded).name=='aru_retopo_mesh_buffer_'+version+'.mll',loaded
    node='aruRetopoGuideShape1';native='aruRetopoNative1'
    before=cmds.getAttr(node+'.outNetData')
    weights={int(k):v for k,v in json.loads((root/'tests/relax_benchmark_weights.json').read_text()).items()}
    assert len(weights)==200
    selection=om.MSelectionList();selection.add(native)
    mesh=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outMesh',False)
    relax.edit._dirty_shape_view=lambda:None
    report={'version':version,'maya':cmds.about(version=True),'loaded_plugin':loaded,'scope':'8 consecutive 200 EP dabs via actual RelaxPreview and native outMesh; no picking or viewport','trials':[]}
    for trial in range(3):
        cmds.undoInfo(openChunk=True,chunkName='Certificate stroke')
        stroke=RelaxPreview(node);assert stroke
        try:
            rows=[]
            for i in range(8):
                start=time.perf_counter();stroke.apply(weights)
                edit=(time.perf_counter()-start)*1000
                mesh.asMObject()
                rows.append({'edit_ms':edit,'total_ms':(time.perf_counter()-start)*1000})
            start=time.perf_counter();stroke.commit();mesh.asMObject()
            release=(time.perf_counter()-start)*1000
            guides=cmds.getAttr(node+'.netData')
            values=[v for point in om.MFnMesh(mesh.asMObject()).getPoints() for v in tuple(point)]
            row={'samples':rows,'median_ms':statistics.median(r['total_ms'] for r in rows[1:]),'release_ms':release,'guide_hash':hashlib.sha256(guides.encode()).hexdigest(),'mesh_hash':hashlib.sha256(struct.pack('='+str(len(values))+'d',*values)).hexdigest()}
            report['trials'].append(row)
        finally:
            if not stroke.closed:stroke.cancel()
            cmds.undoInfo(closeChunk=True)
        cmds.undo()
        assert cmds.getAttr(node+'.outNetData')==before
        assert not cmds.getAttr(node+'.editPreviewPositions')
        mesh.asMObject()
    report['restored']=True
    (root/'tests'/('projection_certificates_stroke_'+version+'_'+cmds.about(version=True)+'.json')).write_text(json.dumps(report,indent=2))
    print('CERTIFICATE STROKE PASSED',version,[r['median_ms'] for r in report['trials']]);status=0
except BaseException:traceback.print_exc()
finally:
    relax.edit._dirty_shape_view=refresh
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(20,repeat=False)
    print('CERTIFICATE CLEANUP scene clear',flush=True)
    cmds.file(new=True,force=True)
    print('CERTIFICATE CLEANUP uninitialize',flush=True)
    maya.standalone.uninitialize()
    print('CERTIFICATE CLEANUP complete',flush=True)
    faulthandler.cancel_dump_traceback_later()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
