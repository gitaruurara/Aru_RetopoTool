import ast,os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from maya import cmds
 from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_relax as relax
 mp.clear()
 for module,name in ((mp,'_load_library'),(mp,'junction_compact'),(relax,'_fit_junction_lengths')):
  path=Path(module.__file__);tree=ast.parse(path.read_text(encoding='utf-8'))
  node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
  scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),module.__dict__,scope);setattr(module,name,scope[name])
 mp._LIB=mp._load_library(ROOT/'bin'/cmds.about(version=True)/'aru_retopo_maya_projector_compact.dll')
 from Aru_RetopoTool.tests import gui_certificates_repeated
 gui_certificates_repeated.run()
 r=json.loads((ROOT/'tests/gui_certificates_repeated_certificates.json').read_text())
 r['projector_library']=str(mp._LIB._name)
 (ROOT/'tests/gui_compact_integrated.json').write_text(json.dumps(r,indent=2))
