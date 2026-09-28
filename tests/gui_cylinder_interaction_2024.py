"""Run camera redraw and actual context release on the disposable 2024 cylinder."""
import os,json,math,time,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session
from Aru_RetopoTool.tests import gui_point_drag
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==52504
 report={}
 try:
  before=cmds.getAttr('aruRetopoGuideShape1.outNetData')
  start=time.perf_counter()
  for i in range(48):
   angle=2*math.pi*i/48
   cmds.setAttr('persp.translate',20*math.sin(angle),8,20*math.cos(angle),type='double3')
   constraint=cmds.aimConstraint('occlusionCylinder','persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
   cmds.delete(constraint);cmds.refresh(force=True)
  report['camera_frames']=48;report['orbit_seconds']=time.perf_counter()-start
  report['camera_preserves_guides']=cmds.getAttr('aruRetopoGuideShape1.outNetData')==before
  cmds.setAttr('persp.translate',12,8,16,type='double3')
  constraint=cmds.aimConstraint('occlusionCylinder','persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
  cmds.delete(constraint);cmds.refresh(force=True)
  cn,_=relax._world_data('aruRetopoGuideShape1')
  # Cylinder EP 9 is on the camera-facing middle ring; do not suppress attachment.
  screen=edit._world_to_screen(cn.positions[9]);assert screen
  gui_point_drag.run(numeric=True,brush_start=screen,delta=(1,1))
  report['drag']=json.loads((ROOT/'gui_point_drag.json').read_text())
  assert report['drag'].get('restored') and not report['drag'].get('error'),report['drag']
  assert all('ERROR' not in s for s in report['drag']['plan_status'].values())
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'cylinder_interaction_2024.json').write_text(json.dumps(report,indent=2))
