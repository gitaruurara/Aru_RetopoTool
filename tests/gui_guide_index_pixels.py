import os,json,traceback,importlib
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as ui

def run():
    assert os.getpid()==48640
    root=Path(__file__).resolve().parents[1];folder=root/'tests/guide_index_pixels';folder.mkdir(exist_ok=True)
    from Aru_RetopoTool.tests import guide_index_candidate
    from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw
    from Aru_RetopoTool import viewport_session
    candidate=importlib.reload(guide_index_candidate)
    node='aruRetopoGuideShape1';report={'cases':[]};restore=None
    original=draw._ctx.sel_ep
    selection=om.MSelectionList();selection.add(node);obj=selection.getDependNode(0)
    def refresh():
        cmds.refresh(force=True)
    def capture(name):
        image=om.MImage();ui.M3dView.active3dView().readColorBuffer(image,True)
        path=folder/(name+'.png');image.writeToFile(str(path),'png');return str(path)
    try:
        viewport_session.ensure_display()
        stats,restore=candidate.install()
        # Both draws are forced through current DG data. Changing selection
        # exercises same-count marker regrouping without touching guide geometry.
        for index,ep in enumerate((None,645,None,646)):
            draw._ctx.sel_ep=ep
            import maya.api.OpenMayaRender as render
            render.MRenderer.setGeometryDrawDirty(obj);refresh();refresh()
            candidate_path=capture(str(index)+'_candidate')
            restore();restore=None
            render.MRenderer.setGeometryDrawDirty(obj);refresh()
            baseline_path=capture(str(index)+'_baseline')
            report['cases'].append({'ep':ep,'candidate':candidate_path,'baseline':baseline_path,'stats':dict(stats)})
            stats,restore=candidate.install()
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if restore:restore()
        draw._ctx.sel_ep=original
        import maya.api.OpenMayaRender as render
        render.MRenderer.setGeometryDrawDirty(obj);refresh()
        (root/'tests/gui_guide_index_pixels.json').write_text(json.dumps(report,indent=2))
