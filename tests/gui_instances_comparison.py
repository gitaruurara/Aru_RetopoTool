import os,json,time,statistics,traceback,importlib.util
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import core
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==42912
 report={}
 try:
  spec=importlib.util.spec_from_file_location('instance_reference',ROOT/'core_instances_reference.py')
  old=importlib.util.module_from_spec(spec);old.__package__='Aru_RetopoTool';spec.loader.exec_module(old)
  selection=om.MSelectionList();selection.add('aruRetopoPlan1')
  node=om.MFnDependencyNode(selection.getDependNode(0)).userNode();plan=node.plan
  cn,_=relax._world_data('aruRetopoGuideShape1')
  report['regions']=plan.region_count;report['vertices']=plan.count
  results={};times={'before':[],'after':[]}
  for i in range(7):
   for name,method in (('before',old.Plan.compile_stencil),('after',core.Plan.compile_stencil)):
    t=time.perf_counter();result=method(plan,cn.splines);elapsed=(time.perf_counter()-t)*1000
    if i:times[name].append(elapsed)
    results[name]=result
  report['identical']=results['before']==results['after'];assert report['identical']
  report['milliseconds']={name:{'median':statistics.median(values),'samples':values} for name,values in times.items()}
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'instances_comparison.json').write_text(json.dumps(report,indent=2))
