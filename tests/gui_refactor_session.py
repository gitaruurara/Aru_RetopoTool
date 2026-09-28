import importlib,json,os,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from maya import cmds
 from Aru_RetopoTool import viewport_session as session
 from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax
 from Aru_RetopoTool.tests import gui_numeric_stroke,gui_point_drag
 report={}
 try:
  session.stop();importlib.reload(session)
  # Existing diagnostic process owns this equivalent solver build; no plugin unload.
  session.BINARY='aru_retopo_mesh_buffer_certificates.mll'
  report['startup']=session.start('modelPanel4');assert session.active()
  report['libraries']={name:str(module.library()._name) for name,module in [('projector',session.maya_projector),('visibility',session.maya_visibility),('screen',session.maya_screen)]}
  cn,_=relax._world_data('aruRetopoGuideShape1')
  weights=json.loads((ROOT/'tests/relax_benchmark_weights.json').read_text())
  screen=edit._world_to_screen(cn.positions[int(max(weights,key=weights.get))]);assert screen
  gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen,instrument_stages=False)
  brush=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
  assert not brush.get('error'),brush
  assert brush['restored'] and brush['exact_final_data']
  report['brush']=brush
  session.ensure_display();cmds.refresh(force=True)
  gui_point_drag.run(numeric=True,brush_start=screen)
  point=json.loads((ROOT/'tests/gui_point_drag.json').read_text())
  assert not point.get('error'),point
  assert point['changed'] and point['restored']
  report['point']=point
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'tests/gui_refactor_session.json').write_text(json.dumps(report,indent=2))
