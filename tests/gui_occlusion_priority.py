import os,traceback,json
from pathlib import Path
from maya import cmds
from Aru_RetopoTool.editor.curvenet import gpu_guides as g
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent
original=g.configure_controls

def configure(owner,items,enabled):
 original(owner,items,enabled)
 for i in range(len(items)):
  item=items[i]
  if item.name().startswith(g.CONTROL_PREFIX):item.setDepthPriority(10000)

def run():
 assert os.getpid()==38780
 try:
  g.configure_controls=configure
  gpu_preview._set_world_guides(True)
  capture('occlusion_priority.png')
 except BaseException:(ROOT/'occlusion_priority_error.txt').write_text(traceback.format_exc())
