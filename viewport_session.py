"""Default interactive viewport session; no global Maya preferences are changed."""
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from . import gpu_preview,native_backend,maya_api as api
from .editor.curvenet import gpu_guides,maya_screen,maya_projector

_active=False
_callbacks=[]
_saved=None
_pending=False
_generation=0
_panel=None
BINARY='aru_retopo_mesh_buffer_certified.mll'

def active():return _active

def _schedule(*unused):
    global _pending
    if not _active or _pending:return
    _pending=True
    token=_generation
    def resume():
        if _active and token==_generation:
            try:ensure_display()
            except Exception as exc:cmds.warning('Aru Retopo 高速表示の再開に失敗: '+str(exc))
    cmds.evalDeferred(resume)

def ensure_display():
    global _pending
    if not _active or not _pending:return
    _pending=False
    override=gpu_preview._override
    if override is None:return
    session=gpu_preview._buffer_session
    if session is not None:session.close()
    # Rebuild object handles after Undo/Redo; do not insert commands into Undo.
    objects=om.MSelectionList()
    for generator in cmds.ls(type='aruRetopoMesh') or []:
        for mesh in cmds.listConnections(api.output_plug(generator),s=False,d=True,type='mesh') or []:
            objects.add(mesh)
    for overlay in cmds.ls(type='aruRetopoOverlay') or []:
        selection=om.MSelectionList();selection.add(overlay)
        attribute=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('enabled',False)
        gpu_preview._saved_attributes.setdefault(overlay+'.enabled',attribute.asBool())
        attribute.setBool(False)
    override.foreground.objects=objects
    guides=om.MSelectionList()
    for guide in cmds.ls(type='retopoGuideNode') or []:guides.add(guide)
    override.guides.objects=guides
    from .gpu_buffer_preview import BufferPreview
    gpu_preview._buffer_session=BufferPreview(override.foreground)
    gpu_preview._set_world_guides(True)

def start(panel=None):
    global _active,_saved,_panel,_generation
    root=Path(__file__).parent;folder=root/'bin'/cmds.about(version=True)
    if panel is None:
        focused=cmds.getPanel(withFocus=True)
        panels=cmds.getPanel(type='modelPanel') or []
        visible=cmds.getPanel(visiblePanels=True) or []
        panel=focused if focused in panels else next((p for p in panels if p in visible),None)
    if not panel or not cmds.modelPanel(panel,exists=True):raise RuntimeError('使用するビューポートを開いてください。')
    for path in (folder/BINARY,folder/maya_projector.BINARY_NAME,folder/'aru_retopo_maya_screen_segments.dll',folder/'aru_retopo_buffer_preview_fast.mll'):
        if not path.is_file():raise RuntimeError('描画用ファイルがありません: '+str(path))
    for plugin in cmds.pluginInfo(q=True,listPlugins=True) or []:
        types=cmds.pluginInfo(plugin,q=True,dependNode=True) or []
        if 'aruRetopoMeshBuffer' in types and Path(cmds.pluginInfo(plugin,q=True,path=True)).name!=BINARY:
            raise RuntimeError('別バージョンの更新プラグインが使用中です。シーンを保存し、新しいMayaで先に Aru_RetopoTool.show() を実行してください。')
    maya_projector.library()  # Validate the native ABI before changing the scene.
    if _active:stop()
    previous=(native_backend.BINARY_NAME,gpu_guides.GPU_CONTROLS,maya_screen._LIB)
    try:
        if 'aruRetopoMeshBuffer' not in cmds.allNodeTypes():cmds.loadPlugin(str(folder/BINARY),quiet=True)
        native_backend.BINARY_NAME=BINARY
        maya_screen._LIB=maya_screen.load_library(folder/'aru_retopo_maya_screen_segments.dll')
        for node in cmds.ls(type='aruRetopoMesh') or []:native_backend.enable(node)
        gpu_guides.GPU_CONTROLS=True
        gpu_preview.enable(panel,direct_buffer=True)
        _saved=previous;_panel=panel;_active=True;_generation+=1
        for event in ('Undo','Redo'):_callbacks.append(om.MEventMessage.addEventCallback(event,_schedule))
        _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterSave,_schedule))
        for event in (om.MSceneMessage.kBeforeOpen,om.MSceneMessage.kBeforeNew):
            _callbacks.append(om.MSceneMessage.addCallback(event,lambda *unused:stop()))
    except Exception:
        if _active:stop()
        else:
            gpu_preview.disable()
            native_backend.BINARY_NAME,gpu_guides.GPU_CONTROLS,maya_screen._LIB=previous
        raise
    return '差分更新とGPU表示を有効にしました。'

def refresh():
    if _active:_schedule()

def stop():
    global _active,_saved,_pending,_generation,_panel
    if not _active:return
    _active=False;_pending=False;_generation+=1
    for callback in _callbacks:om.MMessage.removeCallback(callback)
    _callbacks.clear()
    try:gpu_preview.disable()
    finally:
        if _saved is not None:
            native_backend.BINARY_NAME,gpu_guides.GPU_CONTROLS,maya_screen._LIB=_saved
        _saved=None;_panel=None
