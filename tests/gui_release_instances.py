import os,json,traceback,importlib,sys
from pathlib import Path
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import core,viewport_session as session
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax,curve_net_context as context
from Aru_RetopoTool.tests import gui_point_drag
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==42912
 report={}
 try:
  root=ROOT.parent
  for plugin in (root/'editor/curvenet/aru_retopo_guide_plugin.py',root/'aru_retopo_plugin.py',root/'aru_retopo_plan_plugin.py',root/'aru_retopo_draw_plugin.py',root/'bin/2027/aru_retopo_mesh_buffer_certified.mll'):
   cmds.loadPlugin(str(plugin),quiet=True)
  session.stop()
  cmds.file(str(ROOT/'instances_benchmark.ma'),open=True,force=True)
  session.start('modelPanel4')
  cmds.setFocus('modelPanel4')
  from Aru_RetopoTool import native,subdivision,patch_transfer
  importlib.reload(native);importlib.reload(subdivision);importlib.reload(patch_transfer)
  importlib.reload(gui_point_drag)
  importlib.reload(core)
  for module in list(sys.modules.values()):
   if str(getattr(module,'__file__','')).endswith('aru_retopo_plan_plugin.py'):module.Plan=core.Plan
  import maya.api.OpenMaya as om
  for name in cmds.ls(type='aruRetopoPlan') or []:
   selection=om.MSelectionList();selection.add(name)
   node=om.MFnDependencyNode(selection.getDependNode(0)).userNode()
   node.compute.__func__.__globals__['Plan']=core.Plan
  cn,_=relax._world_data('aruRetopoGuideShape1')
  weights=json.loads((ROOT/'relax_benchmark_weights.json').read_text())
  screen=edit._world_to_screen(cn.positions[int(max(weights,key=weights.get))]);assert screen
  for name in ('attach','no_attach_diagnostic'):
   if name=='attach':gui_point_drag.run(numeric=True,brush_start=screen)
   else:
    with patch.object(context,'_find_spline_under_screen',return_value=None):
     gui_point_drag.run(numeric=True,brush_start=screen)
   point=json.loads((ROOT/'gui_point_drag.json').read_text());report[name]=point
   (ROOT/'release_instances.json').write_text(json.dumps(report,indent=2))
   assert point.get('restored') and not point.get('error'),point
   assert all(not value.startswith('ERROR') for value in point['plan_status'].values()),point
 except BaseException:
  report['error']=traceback.format_exc();(ROOT/'release_instances.json').write_text(json.dumps(report,indent=2))
