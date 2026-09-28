"""Load only the adopted function definitions into the disposable GUI instance."""
import ast,os,json,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
    assert os.getpid()==38780
    from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_draw as draw
    for module,name,owner in ((edit,'make_visibility_test',None),(draw,'updateDG','RetopoGuideGeometryOverride')):
        path=Path(module.__file__);tree=ast.parse(path.read_text(encoding='utf-8'))
        body=tree.body if owner is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==owner).body
        node=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name)
        scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),module.__dict__,scope)
        if owner is None:setattr(module,name,scope[name])
        else:
            module._np=np
            setattr(getattr(module,owner),name,scope[name])
    from Aru_RetopoTool.tests import gui_certificates_repeated
    gui_certificates_repeated.run()
    report=json.loads((ROOT/'tests/gui_certificates_repeated_certificates.json').read_text())
    from Aru_RetopoTool.editor.curvenet import maya_visibility
    report['visibility_library']=str(maya_visibility._LIB._name) if maya_visibility._LIB else None
    report['source_methods']=['curve_net_edit.make_visibility_test','curve_net_draw.RetopoGuideGeometryOverride.updateDG']
    (ROOT/'tests/gui_visibility_integrated.json').write_text(json.dumps(report,indent=2))
