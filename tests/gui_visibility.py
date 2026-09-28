"""ABBA comparison of owned array guide snapshots in the isolated GPU session."""
import os,json,traceback
from pathlib import Path
from maya import cmds
ROOT=Path(__file__).resolve().parents[1]
def run(reverse=False):
    assert os.getpid()==38780
    report={'trials':[]};restore=None
    from Aru_RetopoTool.tests import visibility_candidate,gui_numeric_stroke,gui_point_drag
    from Aru_RetopoTool import viewport_session
    screen=json.loads((ROOT/'tests/gui_certificates_repeated_certificates.json').read_text())['brush_start']
    call_start=visibility_candidate.native_calls
    before=cmds.getAttr('aruRetopoGuideShape1.outNetData')
    try:
        for mode in (('candidate','baseline','baseline','candidate') if reverse else ('baseline','candidate','candidate','baseline')):
            if restore:restore();restore=None
            if mode=='candidate':restore=visibility_candidate.install()
            cmds.refresh(force=True)
            gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen)
            r=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
            assert not r.get('error'),r.get('error')
            assert r['restored'] and r['exact_final_data']
            report['trials'].append({'mode':mode,'numeric':r['modes']['numeric']})
            assert cmds.getAttr('aruRetopoGuideShape1.outNetData')==before
        first=report['trials'][0]['numeric']
        for row in report['trials']:
            assert row['numeric']['guide_hash']==first['guide_hash']
            assert row['numeric']['mesh_hash']==first['mesh_hash']
        report['exact_outputs']=True
        report['native_calls']=visibility_candidate.native_calls-call_start
        assert report['native_calls']>0
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if restore:restore()
        viewport_session.ensure_display();cmds.refresh(force=True)
        (ROOT/'tests'/('gui_visibility_normals_reverse.json' if reverse else 'gui_visibility_normals.json')).write_text(json.dumps(report,indent=2))
