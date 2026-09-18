"""Disposable GUI fixture: foreground passes follow every model panel."""
import os,json,traceback,importlib,math
from pathlib import Path
from maya import cmds,mel
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
ROOT=Path(__file__).parent

def capture(name):
    cmds.refresh(force=True)
    view=omui.M3dView.active3dView();image=om.MImage();view.readColorBuffer(image,True)
    image.writeToFile(str(ROOT/name),'png')


def fixture(expected_pid):
 assert os.getpid()==expected_pid
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
  capture('cylinder_v8_2027_initial.png')
  (ROOT/'cylinder_fixture_v8_2027.json').write_text(json.dumps({'guide':guide,'mesh':mesh,'generator':generator,'regions':len(loops)}))
 except BaseException:(ROOT/'cylinder_fixture_v8_2027_error.txt').write_text(traceback.format_exc())


def run(expected_pid):
    assert os.getpid()==expected_pid
    report={}
    try:
        from Aru_RetopoTool import viewport_session,gpu_preview,patch_context
        cmds.setToolTo('selectSuperContext')
        if patch_context._active:patch_context._active.stop()
        viewport_session.stop();importlib.reload(gpu_preview)
        fixture(expected_pid)
        panels=cmds.getPanel(type='modelPanel')
        report['overrides']={p:cmds.modelEditor(p,q=True,rendererOverrideName=True) for p in panels}
        assert all(v==gpu_preview.Preview.NAME for v in report['overrides'].values())
        cmds.refresh(force=True)
        for panel in panels:
            if panel not in cmds.getPanel(visiblePanels=True):continue
            view=omui.M3dView.getM3dViewFromModelPanel(panel)
            image=om.MImage();view.readColorBuffer(image,True)
            image.writeToFile(str(ROOT/('foreground_'+panel+'.png')),'png')
        saved=dict(gpu_preview._saved_panels)
        viewport_session.stop()
        assert all(cmds.modelEditor(p,q=True,rendererOverrideName=True)==v for p,v in saved.items())
        viewport_session.start('modelPanel4')
        report['restore_previous']=True;report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    (ROOT/'foreground_panels_report.json').write_text(json.dumps(report,indent=2))
