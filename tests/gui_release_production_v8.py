import os,json,traceback,importlib,sys
from pathlib import Path
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import core,viewport_session as session
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax,curve_net_context as context
from Aru_RetopoTool.tests import gui_point_drag
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==51456
 report={}
 try:
  from Aru_RetopoTool import native,subdivision,patch_transfer
  importlib.reload(native);importlib.reload(subdivision);importlib.reload(patch_transfer)
  importlib.reload(gui_point_drag)
  importlib.reload(core)
  assert native.library().aru_retopo_version()==8
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
  free=None
  mesh=edit.RetopoGuideAccessor('aruRetopoGuideShape1').mesh_name
  for radius in (16,24,32,48):
   for dx,dy in ((radius,radius),(-radius,radius),(radius,-radius),(-radius,-radius),(radius,0),(0,radius),(-radius,0),(0,-radius)):
    x,y=screen[0]+dx,screen[1]+dy
    if context._find_spline_under_screen(cn,x,y,exclude_eps={645},mesh_name=mesh) is None and context._find_ep_under_screen(cn,x,y,mesh_name=mesh) is None:
     free=(dx/8.,dy/8.);break
   if free:break
  assert free,'No free-space target found'
  report['free_delta_per_step']=free
  for name in ('attach','free_move'):
   gui_point_drag.run(numeric=True,brush_start=screen,delta=(2,0) if name=='attach' else free)
   point=json.loads((ROOT/'gui_point_drag.json').read_text());report[name]=point
   (ROOT/'release_production_v8.json').write_text(json.dumps(report,indent=2))
   assert point.get('restored') and not point.get('error'),point
   assert all(not value.startswith('ERROR') for value in point['plan_status'].values()),point
   assert point['buffers'],point
   if name=='free_move':
    assert point['hover_spline'] is None and point['merge_target'] is None,point
    assert point['topology_counts'][0]==point['topology_counts'][1],point
   if name=='attach':
    baseline=json.loads((ROOT/'release_native_regions.json').read_text())['before'][0]
    assert point['buffers']==baseline['buffers'],(point['buffers'],baseline['buffers'])
 except BaseException:
  report['error']=traceback.format_exc();(ROOT/'release_production_v8.json').write_text(json.dumps(report,indent=2))
