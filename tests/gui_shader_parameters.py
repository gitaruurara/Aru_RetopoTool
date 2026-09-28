import json
from pathlib import Path
import maya.api.OpenMayaRender as r
def run():
 manager=r.MRenderer.getShaderManager();out={}
 for name in ('k3dSolidShader','k3dThickLineShader','k3dFatPointShader','k3dDepthShader'):
  shader=manager.getStockShader(getattr(r.MShaderManager,name))
  out[name]=list(shader.parameterList());manager.releaseShader(shader)
 Path(__file__).with_suffix('.json').write_text(json.dumps(out,indent=2))
