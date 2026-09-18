"""Disposable opt-in native graph integration regression."""
import json, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
if __name__ == "__main__":
    import maya.standalone
    maya.standalone.initialize(name="python")
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api, native_backend as backend
from Aru_RetopoTool.tests.typed_positions import plug
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.core import regions, patch_key
BUFFER_PLUGIN="aru_retopo_mesh_buffer_"+os.environ.get("ARU_TEST_BUFFER_VERSION","certified")

def points(output):
    node,attr=output.rsplit('.',1)
    obj=plug(node,attr).asMObject()
    try:return list(map(tuple,om.MFnMesh(obj).getPoints()))
    except RuntimeError:return []

def run():
    root=os.path.dirname(os.path.dirname(__file__))
    from maya import mel
    search=str(Path(root)/'bin'/cmds.about(version=True)).replace('\\','/')
    search+=os.pathsep+os.environ.get('MAYA_PLUG_IN_PATH','').replace('\\','/')
    mel.eval('putenv "MAYA_PLUG_IN_PATH" '+json.dumps(search)+';')
    cmds.loadPlugin(str(Path(root)/'bin'/cmds.about(version=True)/(BUFFER_PLUGIN+'.mll')),quiet=True)
    assert cmds.about(version=True) in cmds.pluginInfo(BUFFER_PLUGIN,q=True,path=True).replace('\\','/').split('/')
    cmds.loadPlugin(os.path.join(root,'editor/curvenet/aru_retopo_guide_plugin.py'),quiet=True)
    cmds.undoInfo(state=True)
    guide=cmds.createNode('retopoGuideNode')
    p,s=polygon(5,height=1)
    cmds.setAttr(guide+'.netData',json.dumps(dict(positions=p,splines=s)),type='string')
    ref=cmds.polyPlane(w=10,h=10,sx=8,sy=8)[0]
    output,node=api.create(guide,ref,subdivisions=2)
    native=backend.enable(node)
    assert not points(api.output_plug(node)),api.read_status(node)
    cmds.undo();assert not cmds.objExists(node)
    cmds.redo();assert backend.backend(node)==native
    keys=json.dumps([patch_key(r) for r in regions(p,s,lambda p:(0,1,0))])
    cmds.setAttr(node+'.selectedPatches',keys,type='string')
    def compare():
        assert not api.read_status(node).startswith('ERROR:'),api.read_status(node)
        # Status requests compute coordinates first; mesh must reuse that result.
        values=list(om.MFnDoubleArrayData(plug(native,'outPositions').asMObject()).array())
        a=points(api.output_plug(node));b=points(node+'.outMesh')
        # GPU positions and newly-created Maya mesh use float32; raw solver
        # coordinates remain double precision before that display conversion.
        import struct
        actual=[v for point in a for v in point[:3]]
        assert struct.pack('=%df'%len(values),*values)==struct.pack('=%df'%len(actual),*actual)
        if BUFFER_PLUGIN.endswith('_gpu'):
            # Independent GPU arithmetic can differ below double precision noise;
            # other backend and retained-data checks remain exact.
            error=max((max(abs(x-y) for x,y in zip(u,v)) for u,v in zip(a,b)),default=0)
            assert len(a)==len(b) and error<1.e-10,(len(a),len(b),error)
            import ctypes as C
            gpu_lib=C.CDLL(cmds.pluginInfo(BUFFER_PLUGIN,q=True,path=True))
            gpu_lib.aru_gpu_backend_stats.argtypes=[C.POINTER(C.c_ulonglong)]
            stats=(C.c_ulonglong*3)();gpu_lib.aru_gpu_backend_stats(stats)
            assert stats[0]>0 and stats[1]==0,list(stats)
        else:
            assert a==b,(len(a),len(b),max((max(abs(x-y) for x,y in zip(u,v)) for u,v in zip(a,b)),default=0))
    compare()
    retained=plug(native,'outPositions').asMObject()
    retained_values=list(om.MFnDoubleArrayData(retained).array())
    for mode in ('off','serial','parallel'):
        cmds.evaluationManager(mode=mode)
        for i in range(5):
            cmds.setAttr(guide+'.controlPoints[0]',i*.03,0,i*.01,type='double3');compare()
        for level in (1,2):
            cmds.setAttr(node+'.subdivisions',level);compare()
    assert list(om.MFnDoubleArrayData(retained).array())==retained_values
    for attr,values in [('guideWeight',[.25,1]),('relaxIterations',[0,5,3]),('subdivisions',[1,3,2])]:
        for value in values:cmds.setAttr(node+'.'+attr,value);compare()
    cmds.setAttr(node+'.selectedPatches','[]',type='string');compare()
    cmds.setAttr(node+'.selectedPatches',keys,type='string');compare()
    cmds.select(output);assert api.generator_from_selection()==node
    api.set_foreground(node,True)
    assert api.foreground_enabled(node)
    baked=api.bake(node)
    sh=api.shape(baked,'mesh')
    saved=points(sh+'.outMesh')
    assert saved==points(api.output_plug(node))
    cmds.setAttr(guide+'.controlPoints[0]',.4,0,.2,type='double3');compare()
    assert points(sh+'.outMesh')==saved
    # Exercise both plan parser paths, without dirtying the guide itself.
    from unittest.mock import patch
    from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
    plan_node=cmds.listConnections(node+'.nativePlan',s=True,d=False)[0]
    raw=cmds.getAttr(guide+'.netData')
    cached=RetopoGuideData.from_json_cached(raw)
    cached_before=cached.to_json()
    original_loads=json.loads
    counts=[];messages=[]
    for use_cache in (False,True):
        if use_cache:RetopoGuideData._PARSE_CACHE[raw]=cached
        else:RetopoGuideData._PARSE_CACHE.pop(raw,None)
        parses=[]
        def counted(value,*args,**kwargs):
            if value==raw:parses.append(value)
            return original_loads(value,*args,**kwargs)
        with patch.object(json,'loads',side_effect=counted):
            cmds.dgdirty(plan_node)
            messages.append(cmds.getAttr(plan_node+'.status'))
        counts.append(len(parses))
    assert counts==[1,0],counts
    assert messages[0]==messages[1] and not messages[0].startswith('ERROR:')
    assert cached.to_json()==cached_before
    compare()
    assert backend.enable(node)==native
    compare()
    print('PASS repeated native enable reuses the same graph')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='aru_retopo_native_scene_') as folder:
        scene=os.path.join(folder,'native.ma')
        cmds.file(rename=scene);cmds.file(save=True,type='mayaAscii')
        cmds.file(new=True,force=True)
        cmds.unloadPlugin(BUFFER_PLUGIN)
        cmds.file(scene,open=True,force=True)
        native=backend.backend(node)
        assert native and cmds.pluginInfo(BUFFER_PLUGIN,q=True,loaded=True)
        compare()
    print('PASS native scene reopen resolves version-specific plugin by name')

    print('PASS plan parsed-guide cache hit/miss, skipped decode and ownership')
    print('PASS native graph: empty selection, create Undo/Redo, patch edits, CP, solver settings, subdivisions, selection')

if __name__=='__main__':
    import maya.standalone
    import sys,traceback
    result=0
    try:run()
    except Exception:traceback.print_exc();result=1
    finally:
        cmds.file(new=True,force=True)
        for plugin in ('aru_retopo_draw_plugin',BUFFER_PLUGIN,'aru_retopo_plan_plugin','aru_retopo_plugin','aru_retopo_guide_plugin'):
            if cmds.pluginInfo(plugin,q=True,loaded=True):cmds.unloadPlugin(plugin,force=True)
        maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush()
    os._exit(result)
