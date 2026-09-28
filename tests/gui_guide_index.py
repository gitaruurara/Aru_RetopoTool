import json,os,traceback
from pathlib import Path
from maya import cmds

def run():
    assert os.getpid()==48640
    root=Path(__file__).resolve().parents[1];report={};restore=None
    from Aru_RetopoTool import viewport_session
    from Aru_RetopoTool.tests import gui_point_drag,guide_index_candidate
    try:
        for mode in ('baseline','candidate'):
            if mode=='candidate':stats,restore=guide_index_candidate.install()
            viewport_session.ensure_display();cmds.refresh(force=True)
            gui_point_drag.run(numeric=True)
            report[mode]=json.loads((root/'tests/gui_point_drag.json').read_text())
            assert not report[mode].get('error'),report[mode].get('error')
            assert report[mode]['restored']
        report['index_stats']=dict(stats)
        assert report['baseline']['final_hash']==report['candidate']['final_hash']
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if restore:restore()
        viewport_session.ensure_display();cmds.refresh(force=True)
        (root/'tests/gui_guide_index.json').write_text(json.dumps(report,indent=2))
