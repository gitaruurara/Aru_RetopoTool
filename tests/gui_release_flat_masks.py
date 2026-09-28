import os,json,traceback,statistics,importlib,ast,gc,time,ctypes
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==44048
 report={'before':[],'after':[]}
 try:
  from Aru_RetopoTool import core,native,patch_transfer
  from Aru_RetopoTool.tests import gui_point_drag
  from Aru_RetopoTool.editor.curvenet import curve_net_context as context
  importlib.reload(core);importlib.reload(patch_transfer)
  original_lib=native.library();candidate_lib=ctypes.CDLL(str(ROOT.parent/'bin/flat_masks_candidate/aru_retopo_core_v7.dll'))
  native._lib=None
  with patch.object(native.C,'CDLL',return_value=candidate_lib):native.library()
  selection=om.MSelectionList();selection.add('aruRetopoPlan1');node=om.MFnDependencyNode(selection.getDependNode(0)).userNode();cls=type(node)
  tree=ast.parse((ROOT.parent/'aru_retopo_plan_plugin.py').read_text(encoding='utf-8'))
  definition=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RetopoPlan')
  method=next(n for n in definition.body if isinstance(n,ast.FunctionDef) and n.name=='compute')
  namespace=dict(cls.compute.__globals__);namespace['Plan']=core.Plan;namespace['RetopoPlan']=cls
  exec(compile(ast.Module(body=[method],type_ignores=[]),'retopo_current_compute','exec'),namespace);cls.compute=namespace['compute']
  original_release=context.RetopoGuideContext._release_impl
  for i in range(6):
   for name,lib in (('before',original_lib),('after',candidate_lib)):
    native._lib=lib;events=[];started={};active=[False]
    def release(self,*args,**kwargs):
     active[0]=True
     try:return original_release(self,*args,**kwargs)
     finally:active[0]=False
    def event(phase,info):
     if not active[0]:return
     generation=info['generation']
     if phase=='start':started[generation]=time.perf_counter()
     elif generation in started:events.append({'generation':generation,'ms':(time.perf_counter()-started.pop(generation))*1000})
    gc.callbacks.append(event)
    try:
     with patch.object(context.RetopoGuideContext,'_release_impl',release):gui_point_drag.run(numeric=True,brush_start=(1546,1145))
    finally:gc.callbacks.remove(event)
    result=json.loads((ROOT/'gui_point_drag.json').read_text());result['release_gc']=events
    assert not result.get('error') and result['restored'] and result['buffers'],result
    assert all('ERROR' not in s for s in result['plan_status'].values())
    report[name].append(result)
    (ROOT/'release_flat_masks.json').write_text(json.dumps(report,indent=2))
  for a,b in zip(report['before'],report['after']):assert a['buffers']==b['buffers']
  report['median_ms']={name:statistics.median(r['release_ms'] for r in report[name][1:]) for name in ('before','after')}
  report['median_without_gc_ms']={name:statistics.median(r['release_ms']-sum(g['ms'] for g in r['release_gc']) for r in report[name][1:]) for name in ('before','after')}
  report['identical_output']=True
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'release_flat_masks.json').write_text(json.dumps(report,indent=2))
