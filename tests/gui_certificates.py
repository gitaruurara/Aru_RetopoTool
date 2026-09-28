"""Disposable GUI benchmark; invoked only by run_gui_isolated_current.bat."""
import os,json,traceback,shutil,sys
from pathlib import Path
from maya import cmds
import maya.api.OpenMayaUI as ui
ROOT=Path('D:/Dropbox/App/DCC/internal/maya/common/scripts/Aru_RetopoTool')
VERSION=os.environ.get('ARU_TEST_BUFFER_VERSION','certificates')
STATUS=ROOT/'tests'/('gui_certificates_'+VERSION+'_status.json')
def status(phase,**kw):
    STATUS.write_text(json.dumps(dict(pid=os.getpid(),phase=phase,**kw),indent=2))
def run():
    status('starting')
    try:
        import aru_mcp_startup
        aru_mcp_startup.start()
        binary='aru_retopo_mesh_buffer_'+VERSION+'.mll'
        for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/2027/'+binary):
            cmds.loadPlugin(str(ROOT/plugin),quiet=True)
        from Aru_RetopoTool import viewport_session,native_backend
        viewport_session.BINARY=binary;native_backend.BINARY_NAME=binary
        cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-numeric-isolated-20260918.ma',open=True,force=True,prompt=False)
        cmds.loadPlugin(str(ROOT/'bin/2027/aru_retopo_buffer_preview_fast.mll'),quiet=True)
        owners=[p for p in cmds.pluginInfo(q=True,listPlugins=True) or [] if 'aruRetopoMeshBuffer' in (cmds.pluginInfo(p,q=True,dependNode=True) or [])]
        assert len(owners)==1,owners
        loaded=cmds.pluginInfo(owners[0],q=True,path=True)
        assert Path(loaded).name==binary,loaded
        panel='modelPanel4'
        cmds.setFocus(panel)
        from Aru_RetopoTool import gpu_preview
        from Aru_RetopoTool.editor.curvenet import gpu_guides
        gpu_guides.GPU_CONTROLS=True
        gpu_preview.enable(panel)
        cmds.refresh(force=True)
        view=ui.M3dView.active3dView()
        status('ready',loaded_plugin=loaded,panel=panel,width=view.portWidth(),height=view.portHeight())
        cmds.evalDeferred(measure,lowestPriority=True)
    except BaseException:status('error',error=traceback.format_exc())
def measure():
    try:
        if os.environ.get('ARU_RETOPO_GUI_DIAGNOSTIC'):
            import importlib
            report=importlib.import_module('Aru_RetopoTool.tests.'+os.environ['ARU_RETOPO_GUI_DIAGNOSTIC']).run()
            status('diagnostic_complete',report=report)
            return
        from Aru_RetopoTool.tests import gui_numeric_stroke,gui_point_drag
        status('measuring')
        gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
        report=json.loads((ROOT/'tests/gui_numeric_stroke_direct_gpu_controls.json').read_text())
        (ROOT/'tests'/('gui_certificates_'+VERSION+'_relax.json')).write_text(json.dumps(report,indent=2))
        if report.get('error'):raise RuntimeError(report['error'])
        status('relax_done',report=report)
        # The brush diagnostic removes its temporary preview on completion.
        from Aru_RetopoTool import viewport_session
        viewport_session.start()
        gui_point_drag.run(numeric=True)
        report=json.loads((ROOT/'tests/gui_point_drag.json').read_text())
        (ROOT/'tests'/('gui_certificates_'+VERSION+'_point.json')).write_text(json.dumps(report,indent=2))
        if report.get('error'):raise RuntimeError(report['error'])
        status('complete',point_median_ms=report['median_ms'])
    except BaseException:status('error',error=traceback.format_exc())
cmds.evalDeferred(run,lowestPriority=True)
