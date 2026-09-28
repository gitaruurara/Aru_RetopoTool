import cProfile,pstats,io,json,os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==44048
 from Aru_RetopoTool.editor.curvenet import curve_net_context as context
 from Aru_RetopoTool.tests import gui_point_drag
 profile=cProfile.Profile();original=context.RetopoGuideContext._release_impl
 def release(self,*args,**kwargs):
  profile.enable()
  try:return original(self,*args,**kwargs)
  finally:profile.disable()
 with patch.object(context.RetopoGuideContext,'_release_impl',release):
  gui_point_drag.run(numeric=True,brush_start=(1546,1145))
 stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(65)
 (ROOT/'tests/gui_release_profile_v7.txt').write_text(stream.getvalue(),encoding='utf-8')
