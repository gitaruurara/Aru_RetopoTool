import json,os,traceback,importlib
from pathlib import Path
from maya import cmds

def run():
    assert os.getpid()==48640
    root=Path(__file__).resolve().parents[1];report={};restore=None
    from Aru_RetopoTool import viewport_session
    from Aru_RetopoTool.tests import gui_numeric_stroke,relax_owned_snapshot_candidate
    candidate=importlib.reload(relax_owned_snapshot_candidate)
    try:
        for mode in ('baseline','candidate'):
            if mode=='candidate':stats,restore=candidate.install()
            viewport_session.ensure_display();cmds.refresh(force=True)
            gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
            report[mode]=json.loads((root/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
            assert not report[mode].get('error'),report[mode].get('error')
            assert report[mode]['restored']
            assert report[mode]['exact_final_data']
        report['snapshot_stats']=dict(stats)
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if restore:restore()
        viewport_session.ensure_display();cmds.refresh(force=True)
        (root/'tests/gui_owned_snapshot.json').write_text(json.dumps(report,indent=2))
