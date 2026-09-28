import os,json,traceback,importlib
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session as session
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax,gpu_guides
from Aru_RetopoTool.tests import gui_point_drag
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 report={}
 try:
  session.stop();cmds.file(str(ROOT/'occlusion_before_test.ma'),open=True,force=True)
  importlib.reload(gpu_guides);importlib.reload(gui_point_drag)
  session.start('modelPanel4')
  cn,_=relax._world_data('aruRetopoGuideShape1')
  weights=json.loads((ROOT/'relax_benchmark_weights.json').read_text())
  screen=edit._world_to_screen(cn.positions[int(max(weights,key=weights.get))]);assert screen
  for name,delta in [('right',(2,0)),('up',(0,2)),('left',(-2,0))]:
   gui_point_drag.run(numeric=True,brush_start=screen,delta=delta)
   point=json.loads((ROOT/'gui_point_drag.json').read_text())
   report[name]=point
   (ROOT/'release_directions.json').write_text(json.dumps(report,indent=2))
   assert point.get('restored') and not point.get('error'),point
 except BaseException:
  report['error']=traceback.format_exc();(ROOT/'release_directions.json').write_text(json.dumps(report,indent=2))
