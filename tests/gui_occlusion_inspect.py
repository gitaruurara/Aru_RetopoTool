import os,json,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import gpu_preview as g,viewport_session as s
from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
ROOT=Path(__file__).resolve().parent

def pre(self,context):
 c=self._camera
 (ROOT/(self.name()+'_current_matrix.json')).write_text(json.dumps({'panel':self.panel,'near':c.mNearClippingPlane,'far':c.mFarClippingPlane,'camera':c.mCameraPath.fullPathName(),'actual':list(context.getMatrix(g.render.MFrameContext.kProjectionMtx))}))

def run():
 assert os.getpid()==38780
 try:
  s.stop();g.Foreground.preSceneRender=pre;s.start('modelPanel4')
  capture('occlusion_inspect.png')
 except BaseException:(ROOT/'occlusion_inspect_error.txt').write_text(traceback.format_exc())
