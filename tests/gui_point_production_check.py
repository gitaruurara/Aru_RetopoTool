import os,json,traceback
from pathlib import Path
import maya.api.OpenMayaRender as r
from Aru_RetopoTool.editor.curvenet import gpu_point_shader as p,gpu_guides as g
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 report={'gpu':g.GPU_CONTROLS,'module':g.__file__}
 try:
  shader=p.shader(r.MRenderer.getShaderManager())
  report['parameters']=shader.parameterList()
  report['pointSize']=str(shader.setParameter('pointSize',[8.,8.]))
  report['graph']=r.MRenderer.getFragmentManager().getFragmentXML('aruRetopoDepthPointShader')
  r.MRenderer.getShaderManager().releaseShader(shader)
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'point_production_check.json').write_text(json.dumps(report,indent=2))
