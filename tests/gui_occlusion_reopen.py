import os,traceback,importlib
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session
from Aru_RetopoTool.editor.curvenet import gpu_guides
from Aru_RetopoTool.tests import gui_occlusion_current
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 try:
  viewport_session.stop()
  cmds.file(rename=str(ROOT/'occlusion_cylinder_test.ma'));cmds.file(save=True,type='mayaAscii')
  cmds.file(new=True,force=True)
  importlib.reload(gpu_guides)
  cmds.file(str(ROOT/'occlusion_cylinder_test.ma'),open=True,force=True)
  gui_occlusion_current.run()
 except BaseException:(ROOT/'occlusion_reopen_error.txt').write_text(traceback.format_exc())
