import os,json,traceback,statistics,importlib,importlib.util,gc,time
from pathlib import Path
from unittest.mock import patch
from maya import cmds
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==44048
 report={'before':[],'after':[]}
 try:
  from Aru_RetopoTool import patch_transfer
  from Aru_RetopoTool.tests import gui_point_drag
  spec=importlib.util.spec_from_file_location('transfer_before_lazy',ROOT/'patch_transfer_before_lazy.py')
  old=importlib.util.module_from_spec(spec);old.__package__='Aru_RetopoTool';spec.loader.exec_module(old)
  importlib.reload(patch_transfer);new=patch_transfer.prepare
  for i in range(4):
   for name,fn in (('before',old.prepare),('after',new)):
    events=[];started={}
    def event(phase,info):
     generation=info['generation']
     if phase=='start':started[generation]=time.perf_counter()
     elif generation in started:events.append({'generation':generation,'ms':(time.perf_counter()-started.pop(generation))*1000,'collected':info['collected']})
    gc.callbacks.append(event)
    try:
     with patch.object(patch_transfer,'prepare',fn):gui_point_drag.run(numeric=True,brush_start=(1546,1145))
    finally:gc.callbacks.remove(event)
    result=json.loads((ROOT/'gui_point_drag.json').read_text());result['gc']=events
    assert not result.get('error') and result['restored'] and result['buffers'],result
    assert all('ERROR' not in s for s in result['plan_status'].values())
    report[name].append(result)
    (ROOT/'release_lazy_transfer.json').write_text(json.dumps(report,indent=2))
  for a,b in zip(report['before'],report['after']):assert a['buffers']==b['buffers']
  report['median_ms']={name:statistics.median(r['release_ms'] for r in report[name][1:]) for name in ('before','after')}
  report['identical_output']=True
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'release_lazy_transfer.json').write_text(json.dumps(report,indent=2))
