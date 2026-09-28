import ast,json,os,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from Aru_RetopoTool import core,native
 for module,path,classname,name in ((native,Path(native.__file__),None,'library'),(core,Path(core.__file__),'Plan','compile_stencil')):
  tree=ast.parse(path.read_text(encoding='utf-8'));body=tree.body
  if classname:body=next(n for n in body if isinstance(n,ast.ClassDef) and n.name==classname).body
  node=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name)
  scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),module.__dict__,scope)
  setattr(getattr(module,classname) if classname else module,name,scope[name])
 native._lib=None
 assert native.library().aru_retopo_version()==5
 from Aru_RetopoTool.tests import gui_refactor_session
 gui_refactor_session.run()
 result=json.loads((ROOT/'tests/gui_refactor_session.json').read_text());result['core_library']=native.library()._name
 (ROOT/'tests/gui_native_state_integrated.json').write_text(json.dumps(result,indent=2))
