import ast,importlib,json,os,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 assert os.getpid()==38780
 from Aru_RetopoTool import viewport_session
 from Aru_RetopoTool.editor.curvenet import maya_visibility as mp,curve_net_edit as relax
 from Aru_RetopoTool.tests import gui_numeric_stroke
 report={};captures=[]
 try:
  viewport_session.start('modelPanel4')
  for updated in (False,True):
   if updated:
    importlib.reload(mp)
    tree=ast.parse(Path(relax.__file__).read_text(encoding='utf-8'))
    names={'make_visibility_test'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),relax.__file__,'exec'),relax.__dict__)
   capture={}
   gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=(841,688),capture=capture)
   result=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
   assert not result.get('error'),result
   assert result['restored'] and result['exact_final_data']
   captures.append(capture['numeric'])
  report={'mesh_exact':captures[0]['mesh']==captures[1]['mesh'],'guide_exact':captures[0]['guide']==captures[1]['guide'],'undo_restored':True}
  assert report['mesh_exact'] and report['guide_exact'],report
 except BaseException:report['error']=traceback.format_exc()
 (ROOT/'tests/gui_visibility_refactor_parity.json').write_text(json.dumps(report,indent=2))
