"""ABBA endpoint kernel comparison in disposable GUI only."""
import os,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from maya import cmds
 from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax,curve_net_edit as edit
 from Aru_RetopoTool.tests import gui_numeric_stroke
 from Aru_RetopoTool import viewport_session
 report={'trials':[]};original=mp._LIB;restore=None
 from Aru_RetopoTool.tests import endpoint_candidate
 try:
  viewport_session.start('modelPanel4')
  cn,_=relax._world_data('aruRetopoGuideShape1')
  weights=json.loads((ROOT/'tests/relax_benchmark_weights.json').read_text())
  screen=edit._world_to_screen(cn.positions[int(max(weights,key=weights.get))]);assert screen
  report['brush_start']=list(screen)
  libraries={n:mp._load_library(ROOT/'bin'/cmds.about(version=True)/(('aru_retopo_maya_endpoint_candidate.dll' if name=='endpoint_candidate' else 'aru_retopo_maya_projector_'+name+'.dll'))) for n,name in [(4,'tangents'),(8,'endpoint_candidate')]}
  for count in (8,4,4,8):
   if restore:restore();restore=None
   if count==8:restore=endpoint_candidate.install()
   mp.clear();mp._LIB=libraries[count]
   gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen)
   result=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
   assert not result.get('error'),result
   assert result['restored'] and result['exact_final_data']
   report['trials'].append({'workers':count,**result})
  hashes=[(r['modes']['numeric']['guide_hash'],r['modes']['numeric']['mesh_hash']) for r in report['trials']]
  assert all(h==hashes[0] for h in hashes)
  report['exact_parity']=True
 except BaseException:report['error']=traceback.format_exc()
 finally:
  if restore:restore()
  mp.clear();mp._LIB=original
  (ROOT/'tests/gui_endpoint_kernel_reverse.json').write_text(json.dumps(report,indent=2))
