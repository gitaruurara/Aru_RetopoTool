import os,json,traceback,importlib,statistics
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import core,stencil_compiler
from Aru_RetopoTool.tests import gui_point_drag
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==42912
 report={'before':[],'after':[]}
 try:
  importlib.reload(stencil_compiler);importlib.reload(core);importlib.reload(gui_point_drag)
  selection=om.MSelectionList();selection.add('aruRetopoPlan1')
  node=om.MFnDependencyNode(selection.getDependNode(0)).userNode();node.compute.__func__.__globals__['Plan']=core.Plan
  packed=stencil_compiler.Composer.packed
  def listed(self):return tuple(a.tolist() for a in packed(self))
  for i in range(4):
   for name,fn in (('before',listed),('after',packed)):
    with patch.object(stencil_compiler.Composer,'packed',fn):
     gui_point_drag.run(numeric=True,brush_start=(1546,1145))
    result=json.loads((ROOT/'gui_point_drag.json').read_text())
    assert not result.get('error') and result['restored'],result
    assert result['buffers']
    assert all('ERROR' not in s for s in result['plan_status'].values())
    report[name].append(result)
    (ROOT/'release_arrays_comparison.json').write_text(json.dumps(report,indent=2))
  for a,b in zip(report['before'],report['after']):assert a['buffers']==b['buffers']
  report['median_ms']={name:statistics.median(r['release_ms'] for r in report[name][1:]) for name in ('before','after')}
  report['identical_output']=True
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'release_arrays_comparison.json').write_text(json.dumps(report,indent=2))
