import os,json,traceback
from pathlib import Path
from Aru_RetopoTool.editor.curvenet import gpu_guides as g
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent
original=g.configure_controls

def configure(owner,items,enabled):
 try:
  original(owner,items,enabled)
  info={'enabled':enabled,'valid':owner._is_valid,'eps':len(owner._ep_set),'handles':len(owner._handle_set),'groups':[]}
  for i in range(len(items)):
   item=items[i]
   if item.name().startswith(g.CONTROL_PREFIX):info['groups'].append({'name':item.name(),'enabled':item.isEnabled(),'primitive':item.primitive(),'parameters':item.getShader().parameterList()})
  (ROOT/'control_runtime.json').write_text(json.dumps(info,indent=2))
 except BaseException:(ROOT/'control_runtime_error.txt').write_text(traceback.format_exc());raise

def run():
 assert os.getpid()==38780
 g.configure_controls=configure;gpu_preview._set_world_guides(True);capture('occlusion_runtime.png')
