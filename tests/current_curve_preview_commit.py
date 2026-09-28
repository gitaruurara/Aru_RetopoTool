import sys,os,time,json,cProfile,pstats,io,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides,maya_api as api
from Aru_RetopoTool.editor.curvenet import curve_net_context as c,curve_net_symmetry as sym
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx
report={};status=0
try:
 guides.load();api.load_plugin()
 cmds.file(str(ROOT/'tests/current_curve_latency_scene.mb'),open=True,force=True)
 guide=cmds.ls(type='retopoGuideNode')[0];node=cmds.ls(type='aruRetopoMesh')[0]
 cmds.optionVar(sv=('retopoGuideContext_node',guide));sym.set_axis('x');sym.set_space('object')
 ctx=c.RetopoGuideContext(_ctx)
 original=cmds.getAttr(guide+'.netData')
 def evaluate():
  plug=om.MSelectionList().add(api.output_plug(node)).getPlug(0)
  data=plug.asMObject();return om.MFnMesh(data).numVertices
 import types
 from Aru_RetopoTool import patch_context as pc
 overlay=types.SimpleNamespace(node=node,cache=None,surface=None,candidates=[])
 pc.PatchTool.rebuild(overlay)
 evaluate();rows=[]
 for iteration in range(4):
  # Model a fresh edit, not repeated Undo/replay hits from an identical network.
  from Aru_RetopoTool import regions_native
  regions_native._REGION_CACHE.clear()
  cn=c.RetopoGuideAccessor(guide).read();sp=cn.splines[-1];a=cn.positions[sp[0]];b=cn.positions[sp[3]]
  _ctx.sel_ep=sp[3];_ctx.preview_end=[b[k]+(b[k]-a[k])*.8 for k in range(3)]
  _ctx.drag_ep=None;_ctx.drag_handle=None;_ctx.ring_cut=None;_ctx.ring_preview=None
  c._state_set(_ctx,'press_screen',(0,0));c._state_set(_ctx,'drag_screen',(100,0))
  c._resolve_drop_target=lambda *args:(None,None,None)
  profile=cProfile.Profile()
  if iteration==3:profile.enable()
  try:
   with api.undo_chunk('latency benchmark'):
    t=time.perf_counter();ctx._release_impl();release=(time.perf_counter()-t)*1000
   t=time.perf_counter();vertices=evaluate();evaluation=(time.perf_counter()-t)*1000
   previous={id(row[2]) for row in overlay.candidates}
   t=time.perf_counter();pc.PatchTool.rebuild(overlay);preview_ms=(time.perf_counter()-t)*1000
   rebuilt=sum(id(row[2]) not in previous for row in overlay.candidates)
  finally:
   if iteration==3:profile.disable()
  changed=cmds.getAttr(guide+'.netData')!=original
  assert changed,'Benchmark did not create curve'
  rows.append(dict(preview_ms=preview_ms,rebuilt=rebuilt,total_patches=len(overlay.candidates),release_ms=release,evaluation_ms=evaluation,vertices=vertices,profiled=iteration==3,native_stages=cmds.getAttr(cmds.ls(type='aruRetopoMeshBuffer')[0]+'.computeMilliseconds')))
  cmds.undo();assert cmds.getAttr(guide+'.netData')==original
  evaluate();pc.PatchTool.rebuild(overlay)
  if iteration==3:
   stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(55)
   (ROOT/'tests/current_curve_preview_commit_profile.txt').write_text(stream.getvalue(),encoding='utf-8')
 report['rows']=rows
except BaseException:
 report['error']=traceback.format_exc();status=1
finally:
 (ROOT/'tests/current_curve_preview_commit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2));sys.stdout.flush();sys.stderr.flush()
 os._exit(status)
