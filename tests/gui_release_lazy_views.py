import os,json,traceback,statistics,importlib,importlib.util,ast,gc,time
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==44048
 report={'before':[],'after':[]}
 try:
  from Aru_RetopoTool import core,patch_transfer
  from Aru_RetopoTool.tests import gui_point_drag
  importlib.reload(patch_transfer);importlib.reload(core)
  spec=importlib.util.spec_from_file_location('core_before_views',ROOT/'core_before_lazy_views.py')
  old=importlib.util.module_from_spec(spec);old.__package__='Aru_RetopoTool';spec.loader.exec_module(old)
  selection=om.MSelectionList();selection.add('aruRetopoPlan1')
  node=om.MFnDependencyNode(selection.getDependNode(0)).userNode();cls=type(node)
  original=cls.compute;original.__globals__['Plan']=old.Plan
  tree=ast.parse((ROOT.parent/'aru_retopo_plan_plugin.py').read_text(encoding='utf-8'))
  definition=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RetopoPlan')
  method=next(n for n in definition.body if isinstance(n,ast.FunctionDef) and n.name=='compute')
  namespace=dict(original.__globals__);namespace['Plan']=core.Plan;namespace['RetopoPlan']=cls
  exec(compile(ast.Module(body=[method],type_ignores=[]),'retopo_lazy_compute','exec'),namespace)
  candidate=namespace['compute']
  for i in range(5):
   for name,fn in (('before',original),('after',candidate)):
    events=[];started={}
    def event(phase,info):
     generation=info['generation']
     if phase=='start':started[generation]=time.perf_counter()
     elif generation in started:events.append({'generation':generation,'ms':(time.perf_counter()-started.pop(generation))*1000,'collected':info['collected']})
    gc.callbacks.append(event)
    try:
     with patch.object(cls,'compute',fn):gui_point_drag.run(numeric=True,brush_start=(1546,1145))
    finally:gc.callbacks.remove(event)
    result=json.loads((ROOT/'gui_point_drag.json').read_text());result['gc']=events
    assert not result.get('error') and result['restored'] and result['buffers'],result
    assert all('ERROR' not in s for s in result['plan_status'].values())
    if name=='after':
     assert isinstance(node.plan,core.Plan)
     assert 'faces' not in node.plan.__dict__ and 'patches' not in node.plan.__dict__
    report[name].append(result)
    (ROOT/'release_lazy_views.json').write_text(json.dumps(report,indent=2))
  for a,b in zip(report['before'],report['after']):assert a['buffers']==b['buffers']
  report['median_ms']={name:statistics.median(r['release_ms'] for r in report[name][1:]) for name in ('before','after')}
  report['identical_output']=True
  cls.compute=candidate
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'release_lazy_views.json').write_text(json.dumps(report,indent=2))
