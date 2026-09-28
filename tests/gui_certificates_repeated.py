import json,traceback,os
from pathlib import Path
from maya import cmds
import maya.api.OpenMayaUI as ui
ROOT=Path(__file__).resolve().parents[1]
def run(expected_pid=38780,mode='certificates'):
    assert os.getpid()==expected_pid
    report={'pid':os.getpid(),'mode':mode,'trials':[]}
    try:
        from Aru_RetopoTool.tests import gui_numeric_stroke,gui_point_drag
        from Aru_RetopoTool import viewport_session
        viewport_session.start('modelPanel4')
        view=ui.M3dView.active3dView()
        report['viewport']=[view.portWidth(),view.portHeight()]
        report['guide_xray']=cmds.getAttr('aruRetopoGuideShape1.xray')
        report['owners']=[cmds.pluginInfo(p,q=True,path=True) for p in cmds.pluginInfo(q=True,listPlugins=True) or [] if 'aruRetopoMeshBuffer' in (cmds.pluginInfo(p,q=True,dependNode=True) or [])]
        assert len(report['owners'])==1 and report['owners'][0].endswith('aru_retopo_mesh_buffer_'+mode+'.mll'),report['owners']
        from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
        cn,_=relax._world_data('aruRetopoGuideShape1')
        weights=json.loads((ROOT/'tests/relax_benchmark_weights.json').read_text())
        ep=int(max(weights,key=weights.get))
        screen=edit._world_to_screen(cn.positions[ep]);assert screen
        report['anchor_ep']=ep;report['brush_start']=list(screen)
        report['camera']={a:cmds.getAttr('persp.'+a) for a in ('translate','rotate','scale')}
        import hashlib
        report['input_hash']=hashlib.sha256(cmds.getAttr('aruRetopoGuideShape1.outNetData').encode()).hexdigest()
        for i in range(3):
            gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen)
            r=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
            assert not r.get('error'),r.get('error')
            assert r['restored'] and r['exact_final_data']
            report['trials'].append(r)
        viewport_session.ensure_display();cmds.refresh(force=True)
        gui_point_drag.run(numeric=True,brush_start=screen)
        report['point']=json.loads((ROOT/'tests/gui_point_drag.json').read_text())
        assert not report['point'].get('error'),report['point'].get('error')
        assert report['point']['changed'] and report['point']['restored']
    except BaseException:report['error']=traceback.format_exc()
    finally:(ROOT/'tests'/('gui_certificates_repeated_'+mode+'.json')).write_text(json.dumps(report,indent=2))

def prepare(expected_pid=38780,mode='certificates'):
    assert os.getpid()==expected_pid
    from Aru_RetopoTool import viewport_session
    viewport_session.stop()
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-numeric-isolated-20260918.ma',open=True,force=True,prompt=False)
    from PySide6 import QtWidgets
    window=next(w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName()=='MayaWindow')
    window.showNormal();window.resize(2200,1400)
    for control in ('AttributeEditor','ChannelBoxLayerEditor'):
        if cmds.workspaceControl(control,exists=True):cmds.workspaceControl(control,e=True,visible=False)
    cmds.setAttr('aruRetopoGuideShape1.xray',True)
    cmds.setAttr('persp.translate',14.140764334412186,10.605572982588253,14.14076421520291)
    cmds.setAttr('persp.rotate',-27.93835272960237,47.299999999999976,0.)
    cmds.setFocus('modelPanel4')
    cmds.evalDeferred(lambda:fit_view(expected_pid,mode,0),lowestPriority=True)

def fit_view(expected_pid,mode,attempt):
    assert os.getpid()==expected_pid
    from PySide6 import QtWidgets
    window=next(w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName()=='MayaWindow')
    view=ui.M3dView.active3dView();dx=1600-view.portWidth();dy=1000-view.portHeight()
    if dx or dy:
        if attempt>=4:
            (ROOT/'tests'/('gui_certificates_repeated_'+mode+'.json')).write_text(json.dumps({'error':'viewport resize did not converge','viewport':[view.portWidth(),view.portHeight()]}))
            return
        window.resize(window.width()+dx,window.height()+dy)
        cmds.evalDeferred(lambda:fit_view(expected_pid,mode,attempt+1),lowestPriority=True)
    else:run(expected_pid,mode)

def profile():
    assert os.getpid()==38780
    import importlib
    from Aru_RetopoTool.tests import gui_draw_profile
    report=json.loads((ROOT/'tests/gui_certificates_repeated_certificates.json').read_text())
    importlib.reload(gui_draw_profile).run(brush_start=report['brush_start'])
