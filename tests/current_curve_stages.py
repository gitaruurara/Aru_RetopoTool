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
 from Aru_RetopoTool import patch_transfer,subdivision,local_fields
 events=[]
 def timed(fn,label):
  def call(*args,**kwargs):
   t=time.perf_counter()
   try:return fn(*args,**kwargs)
   finally:events.append((label,(time.perf_counter()-t)*1000))
  return call
 for name in ('_add_spline_to_cn','_split_splines_at_intersections','_mirror_spline','_commit_net_data'):
  setattr(c,name,timed(getattr(c,name),name))
 for owner,name in [(patch_transfer.SceneTransfer,'__init__'),(patch_transfer.Transfer,'__init__'),(patch_transfer,'prepare_all'),(subdivision,'plan'),(subdivision.Steps,'compile'),(local_fields,'weights')]:
  setattr(owner,name,timed(getattr(owner,name),str(owner)+'.'+name))
 provider=om.MFnDependencyNode(om.MSelectionList().add(cmds.ls(type='aruRetopoPlan')[0]).getDependNode(0)).userNode()
 scope=type(provider).compute.__globals__
 for name in ('Plan','selected_regions'):scope[name]=timed(scope[name],name)
 type(provider).compute=timed(type(provider).compute,'provider.compute')
 def evaluate():
  plug=om.MSelectionList().add(api.output_plug(node)).getPlug(0)
  data=plug.asMObject();return om.MFnMesh(data).numVertices
 evaluate();rows=[]
 for iteration in range(4):
  cn=c.RetopoGuideAccessor(guide).read();sp=cn.splines[-1];a=cn.positions[sp[0]];b=cn.positions[sp[3]]
  _ctx.sel_ep=sp[3];_ctx.preview_end=[b[k]+(b[k]-a[k])*.8 for k in range(3)]
  _ctx.drag_ep=None;_ctx.drag_handle=None;_ctx.ring_cut=None;_ctx.ring_preview=None
  c._state_set(_ctx,'press_screen',(0,0));c._state_set(_ctx,'drag_screen',(100,0))
  c._resolve_drop_target=lambda *args:(None,None,None)
  events.clear();profile=cProfile.Profile()
  if iteration==3:profile.enable()
  try:
   with api.undo_chunk('latency benchmark'):
    t=time.perf_counter();ctx._release_impl();release=(time.perf_counter()-t)*1000
   t=time.perf_counter();vertices=evaluate();evaluation=(time.perf_counter()-t)*1000
  finally:
   if iteration==3:profile.disable()
  changed=cmds.getAttr(guide+'.netData')!=original
  assert changed,'Benchmark did not create curve'
  rows.append(dict(release_ms=release,evaluation_ms=evaluation,vertices=vertices,profiled=iteration==3,native_stages=cmds.getAttr(cmds.ls(type='aruRetopoMeshBuffer')[0]+'.computeMilliseconds'),stages=list(events)))
  cmds.undo();assert cmds.getAttr(guide+'.netData')==original
  evaluate()
  if iteration==3:
   stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(55)
   (ROOT/'tests/current_curve_stages_profile.txt').write_text(stream.getvalue(),encoding='utf-8')
 report['rows']=rows
except BaseException:
 report['error']=traceback.format_exc();status=1
finally:
 (ROOT/'tests/current_curve_stages.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2));sys.stdout.flush();sys.stderr.flush()
 os._exit(status)
