import json,os,traceback,importlib
from pathlib import Path
from maya import cmds

def run():
    assert os.getpid()==48640
    root=Path(__file__).resolve().parents[1];report={'trials':[]};restore=None;original_lib=None
    from Aru_RetopoTool import viewport_session
    from Aru_RetopoTool.tests import gui_numeric_stroke
    from Aru_RetopoTool.editor.curvenet import maya_projector as mp
    from Aru_RetopoTool.editor.curvenet import curve_net_relax
    mp.clear();importlib.reload(mp);importlib.reload(curve_net_relax)
    original_lib=mp.library()
    libraries={'baseline':mp._load_library(root/'bin/2027/aru_retopo_maya_projector_bound.dll'),
               'candidate':mp._load_library(root/'bin/2027/aru_retopo_maya_projector_tangents.dll')}
    try:
        for mode in ('baseline','candidate','candidate','baseline'):
            if restore:restore();restore=None
            mp.clear();mp._LIB=libraries[mode]
            viewport_session.ensure_display();cmds.refresh(force=True)
            gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
            report[mode]=json.loads((root/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
            assert not report[mode].get('error'),report[mode].get('error')
            assert report[mode]['restored']
            assert report[mode]['exact_final_data']
            report['trials'].append({'mode':mode,'median_ms':report[mode]['modes']['numeric']['median_ms'],'library':str(mp.library()._name),'numeric':report[mode]['modes']['numeric']})
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if restore:restore()
        mp.clear();mp._LIB=original_lib
        viewport_session.ensure_display();cmds.refresh(force=True)
        (root/'tests/gui_tangents_integrated.json').write_text(json.dumps(report,indent=2))
