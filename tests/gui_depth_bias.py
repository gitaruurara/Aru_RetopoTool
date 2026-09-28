import json,traceback
from pathlib import Path
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as ui
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.tests import gui_cylinder_occlusion
ROOT=Path(__file__).resolve().parents[1]
def run():
 try:
  cls=gpu_preview.render.MCameraOverride
  (ROOT/'tests/camera_override_api.json').write_text(json.dumps({'attributes':dir(cls),'doc':cls.__doc__},indent=2))
 except BaseException:(ROOT/'tests/camera_override_error.txt').write_text(traceback.format_exc())

def biased_camera(self):
 return self._test_camera

def apply():
 try:
  view=ui.M3dView.active3dView();base=view.projectionMatrix();camera=view.getCamera()
  for operation,epsilon in ((gpu_preview._override.foreground,.0001),(gpu_preview._override.guides,.00012)):
   override=gpu_preview.render.MCameraOverride();override.mCameraPath=camera
   matrix=om.MMatrix(base)
   for row in range(4):matrix.setElement(row,2,base.getElement(row,2)-epsilon*base.getElement(row,3))
   override.mProjectionMatrix=matrix;override.mUseProjectionMatrix=True
   operation._test_camera=override
  gpu_preview.Foreground.cameraOverride=biased_camera
  gui_cylinder_occlusion.capture('cylinder_depth_bias.png')
 except BaseException:(ROOT/'tests/camera_override_error.txt').write_text(traceback.format_exc())
