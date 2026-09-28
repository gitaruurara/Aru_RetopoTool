"""Measure current defaults in the existing disposable benchmark GUI."""
import importlib,json,traceback,os
from pathlib import Path
from maya import cmds

def run():
    root=Path(__file__).resolve().parents[1];report={'pid':os.getpid()}
    assert os.getpid()==48640, 'Run only in the identified disposable Maya'
    try:
        from Aru_RetopoTool.editor.curvenet import maya_projector,curve_net_relax
        maya_projector.clear();importlib.reload(maya_projector);importlib.reload(curve_net_relax)
        from Aru_RetopoTool import viewport_session
        viewport_session.start('modelPanel4')
        from Aru_RetopoTool.tests import gui_numeric_stroke
        gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
        report['relax']=json.loads((root/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
        assert not report['relax'].get('error'),report['relax'].get('error')
        viewport_session.ensure_display();cmds.refresh(force=True)
        from Aru_RetopoTool.tests import gui_point_drag
        gui_point_drag.run(numeric=True)
        report['point']=json.loads((root/'tests/gui_point_drag.json').read_text())
    except BaseException:report['error']=traceback.format_exc()
    (root/'tests/gui_bound_current.json').write_text(json.dumps(report,indent=2))
    return report
