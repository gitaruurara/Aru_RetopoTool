import os,sys,json
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import patch_context,brush_context,qt,viewport_session
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as ui
from unittest.mock import patch
assert os.getpid()==51456
report={'modules':[name for name in sys.modules if 'retopo_draw' in name]}
messages=[]
cb=om.MCommandMessage.addCommandOutputCallback(lambda message,kind,*a:messages.append(str(message)))
tool=patch_context._active;tool.timer.stop()
view=ui.M3dView.active3dView();widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
pos=widget.mapToGlobal(qt.QPoint(widget.width()//2,widget.height()//2))
try:
    with patch.object(qt.QCursor,'pos',return_value=pos):
        tool.brush.last=None;tool.brush.update()
        report['display']=str(brush_context.display)[:1600]
        report['camera']=view.getCamera().fullPathName()
        report['overlays']=[(o,cmds.getAttr(o+'.visibility'),cmds.getAttr(o+'.enabled')) for o in cmds.ls(type='aruRetopoOverlay')]
        viewport_session.refresh();viewport_session.ensure_display()
        cmds.refresh(force=True)
        image=om.MImage();view.readColorBuffer(image,True);image.writeToFile(str(Path(__file__).parent/'brush_preview2.png'),'png')
finally:
    om.MMessage.removeCallback(cb)
    report['messages']=messages
    (Path(__file__).parent/'inspect_brush_draw.json').write_text(json.dumps(report,indent=2))
