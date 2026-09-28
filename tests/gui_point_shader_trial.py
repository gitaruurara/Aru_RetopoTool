import os,json,traceback
from pathlib import Path
from Aru_RetopoTool.editor.curvenet import gpu_guides as g
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent
original=g.configure_controls

def configure(owner,items,enabled):
 original(owner,items,enabled)
 manager=g.render.MRenderer.getShaderManager()
 for i in range(len(items)):
  item=items[i]
  if item.name().startswith(g.CONTROL_PREFIX) and item.primitive()==g.render.MGeometry.kPoints:
   old=item.getShader()
   number=int(item.name()[len(g.CONTROL_PREFIX):]);group=g.render_control_groups(owner,owner._style)[number]
   shader=manager.getFragmentShader('aruRetopoFatPointTrial','mayaSolidColorGS',True)
   shader.setParameter('solidColor',group[1]);shader.setParameter('pointSize',[float(group[2]),float(group[2])])
   item.setShader(shader);manager.releaseShader(shader)

def run():
 assert os.getpid()==38780
 try:
  m=g.render.MRenderer.getFragmentManager()
  geom=m.getFragmentXML('mayaPoint2Quad').replace('mayaPoint2Quad','aruRetopoPointQuadTrial').replace(' - dp','')
  graph=m.getFragmentXML('mayaFatPointShader').replace('mayaFatPointShader','aruRetopoFatPointTrial').replace('mayaPoint2Quad','aruRetopoPointQuadTrial')
  if not m.hasFragment('aruRetopoPointQuadTrial'):m.addShadeFragmentFromBuffer(geom.encode(),False)
  if not m.hasFragment('aruRetopoFatPointTrial'):m.addFragmentGraphFromBuffer(graph.encode())
  g.configure_controls=configure;gpu_preview._set_world_guides(True)
  capture('occlusion_point_shader.png')
 except BaseException:(ROOT/'occlusion_point_shader_error.txt').write_text(traceback.format_exc())
