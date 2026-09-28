import ast,json,os,traceback,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from Aru_RetopoTool import core
 from Aru_RetopoTool.tests import gui_point_drag
 report={'trials':[]};original=core.Plan.compile_stencil
 def method(path):
  tree=ast.parse(path.read_text(encoding='utf-8'));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Plan');node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='compile_stencil')
  scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),core.__dict__,scope);return scope['compile_stencil']
 baseline=method(ROOT/'core.py');candidate=method(ROOT/'tests/core_compose_candidate.py.txt');captured=[]
 try:
  for mode in ('old',):
   fn=baseline if mode=='old' else candidate
   def capture(self,splines):
    captured[:]=[(self,splines)];return fn(self,splines)
   core.Plan.compile_stencil=capture
   gui_point_drag.run(numeric=True,brush_start=(841,688))
   r=json.loads((ROOT/'tests/gui_point_drag.json').read_text());assert not r.get('error'),r
   assert r['restored'] and r['changed'];report['trials'].append({'mode':mode,'release_ms':r['release_ms'],'hash':r['final_hash'],'topology':r['topology_counts']})
  assert len({r['hash'] for r in report['trials']})==1
  assert captured
  report['coefficients_exact']=baseline(*captured[0])==candidate(*captured[0]);assert report['coefficients_exact']
  import cProfile,pstats,io
  profile=cProfile.Profile();profile.runcall(candidate,*captured[0])
  stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(25)
  (ROOT/'tests/native_compose_profile.txt').write_text(stream.getvalue(),encoding='utf-8')
 except BaseException:report['error']=traceback.format_exc()
 finally:core.Plan.compile_stencil=original
 (ROOT/'tests/gui_native_compose_profile.json').write_text(json.dumps(report,indent=2))
