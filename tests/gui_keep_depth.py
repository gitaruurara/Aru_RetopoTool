from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.tests import gui_cylinder_occlusion
def keep_depth(self):
 op=gpu_preview.render.MSceneRender.clearOperation(self)
 op.setMask(0)
 return op
def run():
 gpu_preview.Foreground.clearOperation=keep_depth
 gui_cylinder_occlusion.capture('cylinder_depth_kept.png')
