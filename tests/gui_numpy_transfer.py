"""ABBA owned array transfer comparison in disposable GUI only."""
import os,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from maya import cmds
 from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax,curve_net_edit as edit
 from Aru_RetopoTool.tests import gui_numeric_stroke
 from Aru_RetopoTool import viewport_session
 report={'trials':[]};original=mp._LIB
 from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw
 import ast
 tree=ast.parse(Path(draw.__file__).read_text(encoding='utf-8'))
 cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RetopoGuideGeometryOverride')
 method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='updateDG')
 source=ast.unparse(method)
 source=source.replace('values = list(om2.MFnDoubleArrayData(packed).array())','values = om2.MFnDoubleArrayData(packed).array()').replace('_np.array(values, dtype=_np.float64)','_np.fromiter(values, dtype=_np.float64, count=len(values))')
 assert '_np.fromiter' in source
 scope={};exec(compile(source,'<fromiter candidate>','exec'),draw.__dict__,scope)
 baseline=draw.RetopoGuideGeometryOverride.updateDG
 candidate=scope['updateDG']
 try:
  viewport_session.start('modelPanel4')
  cn,_=relax._world_data('aruRetopoGuideShape1')
  weights=json.loads((ROOT/'tests/relax_benchmark_weights.json').read_text())
  screen=edit._world_to_screen(cn.positions[int(max(weights,key=weights.get))]);assert screen
  report['brush_start']=list(screen)
  for count in ('list','fromiter','fromiter','list'):
   draw.RetopoGuideGeometryOverride.updateDG=baseline if count=='list' else candidate
   gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen)
   result=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
   assert not result.get('error'),result
   assert result['restored'] and result['exact_final_data']
   report['trials'].append({'transfer':count,**result})
  hashes=[(r['modes']['numeric']['guide_hash'],r['modes']['numeric']['mesh_hash']) for r in report['trials']]
  assert all(h==hashes[0] for h in hashes)
  report['exact_parity']=True
 except BaseException:report['error']=traceback.format_exc()
 finally:
  draw.RetopoGuideGeometryOverride.updateDG=baseline
  (ROOT/'tests/gui_numpy_transfer.json').write_text(json.dumps(report,indent=2))
