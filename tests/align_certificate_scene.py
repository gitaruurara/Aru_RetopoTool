from pathlib import Path
p=Path('tests/gui_certificates_repeated.py');s=p.read_text()
start=s.index('def prepare(');end=s.index('\ndef profile():',start)
s=s[:start]+'''def prepare(expected_pid=38780,mode='certificates'):
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
''' +s[end:]
p.write_text(s)
