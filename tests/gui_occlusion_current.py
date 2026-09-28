import os,importlib,traceback,json
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import gpu_preview,viewport_session,guides
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 try:
  viewport_session.stop();importlib.reload(gpu_preview)
  viewport_session.start('modelPanel4')
  guides.edit('aruRetopoGenerator1')
  capture('occlusion_current_front.png')
  cmds.setAttr('persp.translate',-10,6,-12,type='double3')
  cmds.setAttr('persp.rotate',-21,220,0,type='double3')
  capture('occlusion_current_back.png')
  cmds.setAttr('perspShape.orthographic',True)
  cmds.setAttr('perspShape.orthographicWidth',12)
  capture('occlusion_current_ortho.png')
  cmds.setAttr('perspShape.orthographic',False)
  cmds.setAttr('persp.translate',10,6,12,type='double3')
  cmds.setAttr('persp.rotate',-21,40,0,type='double3')
  capture('occlusion_current_restored.png')
  (ROOT/'occlusion_current.json').write_text(json.dumps({'context':cmds.currentCtx(),'scene':cmds.file(q=True,sn=True),'completed':True}))
 except BaseException:(ROOT/'occlusion_current_error.txt').write_text(traceback.format_exc())
