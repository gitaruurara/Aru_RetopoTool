import os,json,traceback
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as ui
from Aru_RetopoTool import gpu_preview,viewport_session
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent
calls=0

def camera(self):
 global calls
 calls+=1
 view=ui.M3dView.active3dView()
 base=view.projectionMatrix()
 override=gpu_preview.render.MCameraOverride()
 override.mCameraPath=view.getCamera()
 matrix=om.MMatrix(base)
 for row in range(4):matrix.setElement(row,2,base.getElement(row,2)-.005*base.getElement(row,3))
 override.mProjectionMatrix=matrix
 override.mUseProjectionMatrix=True
 self._test_camera=override
 override.mUseNearClippingPlane=True
 override.mNearClippingPlane=.1005
 override.mProjectionMatrix=matrix
 return override

def clear(self):
 op=gpu_preview.render.MSceneRender.clearOperation(self)
 op.setMask(0)
 return op

def pre(self,context):
 (ROOT/(self.name()+"_projection.json")).write_text(json.dumps({"actual":list(context.getMatrix(gpu_preview.render.MFrameContext.kProjectionMtx)),"requested":list(self._test_camera.mProjectionMatrix)}))

def run():
 assert os.getpid()==38780
 try:
  viewport_session.stop()
  gpu_preview.Foreground.cameraOverride=camera
  gpu_preview.Foreground.preSceneRender=pre
  gpu_preview.Foreground.clearOperation=clear
  viewport_session.start('modelPanel4')
  capture('cylinder_bias_small.png')
  (ROOT/'bias_recreated.json').write_text(json.dumps({'calls':calls}))
 except BaseException:(ROOT/'bias_recreated_error.txt').write_text(traceback.format_exc())
