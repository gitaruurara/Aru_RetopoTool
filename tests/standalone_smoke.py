"""Run with mayapy to check operation without the studio packages."""
import os
import sys
import importlib.abc
sys.path.insert(0,os.path.abspath(os.path.join(os.path.dirname(__file__),'../..')))
import maya.standalone
maya.standalone.initialize(name='python')


class NoStudio(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('Aru_lib','Aru_CurveNetRig','Aru_Menu'):
            raise ModuleNotFoundError(fullname)


sys.meta_path.insert(0,NoStudio())
try:
    from maya import cmds
    from Aru_RetopoTool import qt,guides,maya_api,construction
    assert qt.AruMainWindow.__module__=='Aru_RetopoTool.qt'
    reference=cmds.polySphere()[0]
    guide=guides.create(reference)
    output,node=maya_api.create(guide,reference)
    assert cmds.polyEvaluate(output,face=True)==0
    assert not cmds.getAttr(node+'.status').startswith('ERROR:')
    from Aru_RetopoTool.native import library
    if str(cmds.about(apiVersion=True)).startswith('2024'):
        assert os.path.basename(os.path.dirname(library()._name))=='2024'
    print('Native library:',library()._name)
    print('PASS standalone Qt, owned guide plugin, native DLL, empty generator')
finally:
    cmds.file(new=True,force=True)
    for plugin in ('aru_retopo_draw_plugin','aru_retopo_plugin','aru_retopo_guide_plugin'):
        if cmds.pluginInfo(plugin,q=True,loaded=True):cmds.unloadPlugin(plugin,force=True)
    maya.standalone.uninitialize()
