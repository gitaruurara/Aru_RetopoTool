import os,sys,traceback,json
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
root=Path(__file__).resolve().parents[1]
status=1
try:
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/2027/aru_retopo_mesh_buffer_v4.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-v4-restore-16732.ma',open=True,force=True,prompt=False)
    native=cmds.ls(type='aruRetopoMeshBuffer');assert len(native)==1
    meshes=cmds.listConnections(native[0]+'.outMesh',s=False,d=True,type='mesh');assert meshes
    count=cmds.polyEvaluate(meshes[0],face=True);assert count==46528,count
    assert cmds.pluginInfo('aru_retopo_mesh_buffer_v4',q=True,loaded=True)
    print('V4 RESTORE PASSED',count,'quads',cmds.getAttr(native[0]+'.status'));status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
