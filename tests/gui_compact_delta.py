import os,json,traceback,importlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from maya import cmds
 from Aru_RetopoTool import viewport_session
 from Aru_RetopoTool.editor.curvenet import maya_projector as mp
 from Aru_RetopoTool.tests import gui_numeric_stroke
 importlib.reload(gui_numeric_stroke)
 original=mp._LIB;report={};results=[]
 try:
  viewport_session.start('modelPanel4')
  for mode in ('endpoints','compact'):
   mp.clear();mp._LIB=mp._load_library(ROOT/'bin'/cmds.about(version=True)/('aru_retopo_maya_projector_'+mode+'.dll'))
   capture={};gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=(841,688),capture=capture)
   result=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text());assert not result.get('error'),result
   assert result['restored'] and result['exact_final_data'];results.append(capture['numeric'])
  a,b=[np.asarray(x['mesh']) for x in results]
  report['mesh_max_error']=float(np.max(np.abs(a-b)));report['float32_mesh_exact']=bool(np.array_equal(a.astype(np.float32),b.astype(np.float32)))
  ga,gb=[json.loads(x['guide']) for x in results]
  report['guide_max_error']=float(np.max(np.abs(np.asarray(ga['positions'])-np.asarray(gb['positions']))))
  report['topology_exact']=ga['splines']==gb['splines'];report['restored']=True
  assert report['mesh_max_error']<1e-9 and report['guide_max_error']<1e-9 and report['topology_exact']
 except BaseException:report['error']=traceback.format_exc()
 finally:
  mp.clear();mp._LIB=original
  (ROOT/'tests/gui_compact_delta.json').write_text(json.dumps(report,indent=2))
