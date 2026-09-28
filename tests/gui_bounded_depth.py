import os,importlib,json,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session as session,gpu_preview,guides
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 report={}
 try:
  session.stop();cmds.file(str(ROOT/'occlusion_cylinder_test.ma'),open=True,force=True)
  from Aru_RetopoTool.editor.curvenet import gpu_guides
  importlib.reload(gpu_guides)
  importlib.reload(gpu_preview);session.start('modelPanel4');guides.edit('aruRetopoGenerator1')
  cmds.setAttr('perspShape.orthographic',False);cmds.setAttr('perspShape.focalLength',35.)
  cmds.setAttr('persp.translate',12,8,16,type='double3')
  constraint=cmds.aimConstraint('occlusionCylinder','persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
  cmds.delete(constraint)
  report['near']=gpu_preview._depth_limits('modelPanel4');capture('bounded_near.png')
  cmds.setAttr('persp.translate',96,64,128,type='double3');cmds.setAttr('perspShape.focalLength',280.)
  report['far']=gpu_preview._depth_limits('modelPanel4');capture('bounded_far.png')
  cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',12.)
  report['ortho']=gpu_preview._depth_limits('modelPanel4');capture('bounded_ortho.png')
  cmds.setAttr('persp.translate',12,8,16,type='double3');cmds.setAttr('perspShape.focalLength',35.)
  cmds.setAttr('perspShape.orthographic',False)
  report['status']={n:cmds.getAttr(n+'.status') for n in cmds.ls(type='aruRetopoPlan') or []}
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'bounded_depth.json').write_text(json.dumps(report,indent=2))
