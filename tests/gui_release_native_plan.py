import os,json,traceback,statistics,ctypes
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==44048
 report={'before':[],'after':[]}
 try:
  from Aru_RetopoTool import native,core,viewport_session as session
  candidate=ctypes.CDLL(str(ROOT.parent/'bin/plan_compile_candidate/aru_retopo_core_v6.dll'))
  assert native._lib is None,'Run in a fresh diagnostic process'
  with patch.object(native.C,'CDLL',return_value=candidate):native.library()
  from Aru_RetopoTool.tests import core_compiled_candidate,gui_point_drag
  root=ROOT.parent
  for plugin in (root/'editor/curvenet/aru_retopo_guide_plugin.py',root/'aru_retopo_plugin.py',root/'aru_retopo_plan_plugin.py',root/'aru_retopo_draw_plugin.py',root/'bin/2027/aru_retopo_mesh_buffer_certified.mll'):
   cmds.loadPlugin(str(plugin),quiet=True)
  cmds.file(str(ROOT/'instances_benchmark.ma'),open=True,force=True)
  session.start('modelPanel4');cmds.setFocus('modelPanel4')
  selection=om.MSelectionList();selection.add('aruRetopoPlan1')
  node=om.MFnDependencyNode(selection.getDependNode(0)).userNode()
  compute_globals=node.compute.__func__.__globals__
  from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax
  cn,_=relax._world_data('aruRetopoGuideShape1');screen=edit._world_to_screen(cn.positions[645])
  for i in range(4):
   for name,cls in (('before',core.Plan),('after',core_compiled_candidate.Plan)):
    compute_globals['Plan']=cls
    gui_point_drag.run(numeric=True,brush_start=screen)
    result=json.loads((ROOT/'gui_point_drag.json').read_text())
    assert not result.get('error') and result['restored'],result
    assert result['buffers']
    assert all('ERROR' not in s for s in result['plan_status'].values())
    report[name].append(result)
    (ROOT/'release_native_plan_comparison.json').write_text(json.dumps(report,indent=2))
  for a,b in zip(report['before'],report['after']):assert a['buffers']==b['buffers'],(a['buffers'],b['buffers'])
  report['median_ms']={name:statistics.median(r['release_ms'] for r in report[name][1:]) for name in ('before','after')}
  report['identical_output']=True
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'release_native_plan_comparison.json').write_text(json.dumps(report,indent=2))
