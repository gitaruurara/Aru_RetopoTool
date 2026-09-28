import os,json,math,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def capture(name):
 import maya.api.OpenMaya as om
 import maya.api.OpenMayaUI as ui
 from maya import cmds
 cmds.refresh(force=True);view=ui.M3dView.active3dView();img=om.MImage();view.readColorBuffer(img,True);img.writeToFile(str(ROOT/'tests'/name),'png')
def fixture():
 assert os.getpid()==52504
 from maya import cmds
 from Aru_RetopoTool import viewport_session as session,guides,maya_api as api,native_backend,core
 from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
 from Aru_RetopoTool.editor.curvenet.curve_net_edit import RetopoGuideAccessor
 try:
  session.stop()
  cmds.file(new=True,force=True)
  mesh=cmds.polyCylinder(r=3,h=6,sx=64,sy=1,sz=1,ch=False,name='occlusionCylinder')[0]
  guide=guides.create(mesh);cn=RetopoGuideData();count=8;theta=2*math.pi/count;k=4/3*math.tan(theta/4)*3
  for y in (-2.,0.,2.):
   for i in range(count):cn.add_cv((3*math.cos(i*theta),y,3*math.sin(i*theta)))
  for row in range(3):
   for i in range(count):
    a=row*count+i;b=row*count+(i+1)%count;p=cn.positions[a];q=cn.positions[b]
    h=cn.add_cv((p[0]-k*math.sin(i*theta),p[1],p[2]+k*math.cos(i*theta)))
    j=cn.add_cv((q[0]+k*math.sin((i+1)*theta),q[1],q[2]-k*math.cos((i+1)*theta)))
    cn.add_spline(a,h,j,b)
  for row in range(2):
   for i in range(count):
    a=row*count+i;b=a+count;p=cn.positions[a];q=cn.positions[b]
    h=cn.add_cv(tuple((2*p[k]+q[k])/3 for k in range(3)));j=cn.add_cv(tuple((p[k]+2*q[k])/3 for k in range(3)))
    cn.add_spline(a,h,j,b)
  cn.classify_endpoints();RetopoGuideAccessor(guide).write(cn)
  output,generator=api.create(guide,mesh,subdivisions=2,iterations=2)
  loops=core.regions(cn.positions,cn.splines,lambda p:(p[0],0,p[2]))
  cmds.setAttr(generator+'.selectedPatches',json.dumps([core.patch_key(loop) for loop in loops]),type='string')
  native_backend.enable(generator)
  cmds.setAttr(guide+'.xray',True);cmds.optionVar(sv=('retopoGuideContext_node',guide));cmds.select(guide)
  cmds.setAttr('persp.translate',10,6,12,type='double3');cmds.setAttr('persp.rotate',-21,40,0,type='double3')
  cmds.setFocus('modelPanel4');cmds.modelEditor('modelPanel4',e=True,displayAppearance='smoothShaded',grid=False)
  session.start('modelPanel4')
  capture('cylinder_2024_initial.png')
  (ROOT/'tests/cylinder_fixture_2024.json').write_text(json.dumps({'guide':guide,'mesh':mesh,'generator':generator,'regions':len(loops)}))
 except BaseException:(ROOT/'tests/cylinder_fixture_2024_error.txt').write_text(traceback.format_exc())

import os,importlib,json,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session as session,gpu_preview,guides
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
REPORT_ROOT=Path(__file__).resolve().parent

def bounds():
 assert os.getpid()==52504
 report={}
 try:
  session.stop()
  from Aru_RetopoTool.editor.curvenet import gpu_guides
  importlib.reload(gpu_guides)
  importlib.reload(gpu_preview);session.start('modelPanel4');guides.edit('aruRetopoGenerator1')
  cmds.setAttr('perspShape.orthographic',False);cmds.setAttr('perspShape.focalLength',35.)
  cmds.setAttr('persp.translate',12,8,16,type='double3')
  constraint=cmds.aimConstraint('occlusionCylinder','persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
  cmds.delete(constraint)
  report['near']=gpu_preview._depth_limits('modelPanel4');capture('bounded_2024_near.png')
  cmds.setAttr('persp.translate',96,64,128,type='double3');cmds.setAttr('perspShape.focalLength',280.)
  report['far']=gpu_preview._depth_limits('modelPanel4');capture('bounded_2024_far.png')
  cmds.setAttr('perspShape.orthographic',True);cmds.setAttr('perspShape.orthographicWidth',12.)
  report['ortho']=gpu_preview._depth_limits('modelPanel4');capture('bounded_2024_ortho.png')
  cmds.setAttr('persp.translate',12,8,16,type='double3');cmds.setAttr('perspShape.focalLength',35.)
  cmds.setAttr('perspShape.orthographic',False)
  report['status']={n:cmds.getAttr(n+'.status') for n in cmds.ls(type='aruRetopoPlan') or []}
 except BaseException:report['error']=traceback.format_exc()
 (REPORT_ROOT/'bounded_depth_2024.json').write_text(json.dumps(report,indent=2))

def run():
 fixture()
 bounds()
