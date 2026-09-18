"""Run in a disposable mayapy process, never in an artist's open scene."""
import json
import os
import sys
import tempfile
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool.tests.mesh_assertions import face_count
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.tests.test_core import polygon


def vertices(node):
    from Aru_RetopoTool.tests.mesh_assertions import mesh_fn
    fn=mesh_fn(node)
    return [(p.x,p.y,p.z) for p in fn.getPoints()]



def run():
    cmds.file(new=True, force=True)
    if 'Aru_RetopoTool' in (cmds.moduleInfo(listModules=True) or []):
        cmds.loadPlugin('aru_retopo_plugin.py')
        print('PASS module discovers saved-scene plugin by filename')
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    cmds.loadPlugin(os.path.join(root, 'Aru_RetopoTool/editor/curvenet/aru_retopo_guide_plugin.py'))
    guide = cmds.createNode('retopoGuideNode', name='retopoTestGuideShape')
    positions, splines = polygon(5, height=1)
    raw = json.dumps({'positions': positions, 'splines': splines})
    cmds.setAttr(guide+'.netData', raw, type='string')
    mesh = cmds.polyPlane(w=10, h=10, sx=20, sy=20, name='retopoTestReference')[0]
    output, node = api.create(guide, mesh, subdivisions=3)
    from Aru_RetopoTool import preview_locator
    locator = preview_locator.shape(node)
    assert locator
    cmds.undo()
    assert not cmds.objExists(output) and not cmds.objExists(node)
    cmds.redo()
    assert preview_locator.shape(node) == locator
    print('PASS locator creation is one undoable operation')
    assert not cmds.listRelatives(output, shapes=True, type='mesh')
    assert len(cmds.listRelatives(output, shapes=True, type='aruRetopoBufferPreview') or []) == 1
    assert api.generator_for_guide(guide, mesh) == node
    cmds.select(guide)
    assert api.generator_from_selection() == node
    cmds.select(output)
    assert api.generator_from_selection() == node
    print('PASS existing generator resolution from guide and output')
    assert face_count(output) == 0
    from Aru_RetopoTool.core import regions, patch_key
    from Aru_RetopoTool.patch_context import confirm
    key = patch_key(regions(positions,splines,lambda p:(0,1,0))[0])
    confirm(node,key)
    assert face_count(output) == 80, cmds.getAttr(node+'.status')
    confirm(node,key,remove=True)
    assert face_count(output)==0
    cmds.undo()
    assert face_count(output)==80
    print('PASS explicit patch fill/remove, empty by default, Undo')
    from Aru_RetopoTool import patch_context
    from types import SimpleNamespace
    from unittest.mock import patch
    qt = patch_context.qt
    event = SimpleNamespace(type=lambda:qt.QEvent.MouseButtonPress,
                            button=lambda:qt.Qt.MiddleButton,
                            modifiers=lambda:qt.Qt.ShiftModifier)
    tool = SimpleNamespace(node=node,key=key,tick=lambda **kwargs:None)
    with patch.object(cmds,'currentCtx',return_value=patch_context.NAME),patch.object(patch_context,'viewport_receiver',return_value=True):
        assert patch_context.PatchTool.eventFilter(tool,None,event)
    assert face_count(output)==0
    cmds.undo()
    assert face_count(output)==80
    print('PASS middle mouse event dispatch and Shift removal')
    tool.context='retopoGuideDraggerCtx1'
    tool.near_control_point=lambda:True
    with patch.object(cmds,'currentCtx',return_value=tool.context),patch.object(patch_context,'viewport_receiver',return_value=True):
        assert not patch_context.PatchTool.eventFilter(tool,None,event)
    print('PASS combined context gives control-point dragging priority')
    assert max(abs(p[1]) for p in vertices(output)) < 1e-6
    print('PASS pentagon -> 80 quads; floating guides projected to reference')
    initial = vertices(output)
    assert api.foreground_enabled(node)
    api.set_foreground(node, False)
    assert not api.foreground_enabled(node)
    assert vertices(output) == initial
    api.set_foreground(node, True)
    assert api.foreground_enabled(node)
    print('PASS overlay toggles without changing geometry')
    cmds.setAttr(guide+'.controlPoints[0].xValue', .35)
    changed = vertices(output)
    assert max(abs(a[0]-b[0]) for a,b in zip(initial,changed)) > .05
    assert len(changed) == len(initial)
    print('PASS guide controlPoints drive stable output topology')
    cmds.move(0,2,0,mesh, relative=True)
    assert max(abs(p[1]-2) for p in vertices(output)) < 1e-6
    cmds.move(3,0,0,cmds.listRelatives(guide,parent=True)[0], relative=True)
    assert max(p[0] for p in vertices(output)) > 3.5
    print('PASS reference and guide transforms evaluated in world space')
    with api.undo_chunk('test settings'):
        cmds.setAttr(node+'.subdivisions', 2)
    assert face_count(output) == 20
    cmds.undo()
    assert face_count(output) == 80
    print('PASS undo subdivision settings')
    locator_uuid=cmds.ls(locator,uuid=True)[0]
    baked = api.bake(node)
    baked_points = vertices(baked)
    assert not cmds.listRelatives(baked, shapes=True, type='aruRetopoOverlay')
    assert not cmds.listConnections(api.shape(baked,'mesh')+'.inMesh',source=True,destination=False)
    cmds.move(0,1,0,mesh,relative=True)
    assert vertices(baked) == baked_points
    assert max(abs(p[1]-3) for p in vertices(output)) < 1e-6
    assert cmds.ls(locator,uuid=True)[0] == locator_uuid
    assert not cmds.listRelatives(output, shapes=True, type='mesh')
    print('PASS bake independent copy, original locator still live')
    assert not any(k.startswith('Aru_CurveNetRig') for k in sys.modules)
    import Aru_Menu
    _, _, report = Aru_Menu.validate()
    assert any('カーブガイド・リトポロジー' in name for name in report['accepted'])
    print('PASS menu entry accepted')
    temp_dir = tempfile.mkdtemp(prefix='aru_retopo_smoke_')
    scene = os.path.join(temp_dir,'retopo.ma')
    cmds.file(rename=scene); cmds.file(save=True,type='mayaAscii')
    with open(scene, encoding='utf-8', errors='replace') as stream:
        print('SCENE_PLUGIN_REQUIREMENTS', [line.strip() for line in stream if line.startswith('requires ')])
    cmds.file(new=True,force=True); cmds.file(scene,open=True,force=True)
    assert face_count(output) == 80
    assert cmds.ls(locator,uuid=True)[0] == locator_uuid
    assert preview_locator.shape(node) == locator
    assert not cmds.listRelatives(output, shapes=True, type='mesh')
    cmds.move(0,1,0,mesh,relative=True)
    assert max(abs(p[1]-4) for p in vertices(output)) < 1e-6
    print('PASS save/reopen retains live DG connections')
    duplicate = cmds.instance(mesh)[0]
    try:
        api.create(guide, mesh)
        raise AssertionError('Instanced reference must be rejected')
    except ValueError as error:
        assert 'インスタンス' in str(error)
    cmds.delete(duplicate)
    print('PASS instanced input rejected without partial output')
    print('STATUS', cmds.getAttr(node+'.status'))
    from Aru_RetopoTool.tests.surface_relax import run as test_relax
    test_relax()
    from Aru_RetopoTool.tests.viewport_preflight import run as test_viewport_preflight
    test_viewport_preflight()
    from Aru_RetopoTool.tests.screen_hit import run as test_screen_hit
    test_screen_hit()
    from Aru_RetopoTool.tests.commit_redraw import run as test_commit_redraw
    test_commit_redraw()
    from Aru_RetopoTool.tests.relax_preview import run as test_relax_preview
    test_relax_preview()
    from Aru_RetopoTool.tests.point_preview import run as test_point_preview
    test_point_preview()
    from Aru_RetopoTool.tests.construction import run as test_construction
    test_construction()
    from Aru_RetopoTool.tests.drag_extrude import run as test_drag
    test_drag()
    from Aru_RetopoTool.tests.bridge import run as test_bridge
    test_bridge()
    from Aru_RetopoTool.tests.symmetry_hard_surface import run as test_symmetry_hard
    test_symmetry_hard()
    from Aru_RetopoTool.tests.patch_transfer import run as test_transfer
    test_transfer()
    from Aru_RetopoTool.tests.display import run as test_display
    test_display()
    from Aru_RetopoTool.tests.foreground_projection import run as test_foreground
    test_foreground()
    from Aru_RetopoTool.tests.gpu_guide_buffers import run as test_gpu_guides
    test_gpu_guides()
    from Aru_RetopoTool.tests.typed_positions import run as test_typed_positions
    test_typed_positions()
    from Aru_RetopoTool.tests.reference_dirty import run as test_reference_dirty
    test_reference_dirty()
    from Aru_RetopoTool.tests.gpu_control_batches import run as test_gpu_controls
    test_gpu_controls()
    from Aru_RetopoTool import guides
    empty_guide=guides.create(mesh)
    empty_output,empty_node=api.create(empty_guide,mesh)
    assert not (cmds.getAttr(empty_node+'.status') or '').startswith('ERROR:')
    assert face_count(empty_output)==0
    print('PASS empty owned guides; no legacy Python imports required')
    # Both node types/contexts can coexist; importing copies evaluated geometry.
    cmds.loadPlugin(os.path.join(root,'Aru_CurveNetRig/curvenet/curve_net_plugin.py'))
    legacy=cmds.createNode('curveNetNode')
    cmds.setAttr(legacy+'.netData',raw,type='string')
    cmds.setAttr(legacy+'.meshName',mesh,type='string')
    parent=cmds.listRelatives(legacy,parent=True)[0]
    cmds.setAttr(parent+'.translateX',3.)
    original=cmds.getAttr(legacy+'.outNetData')
    copied=guides.import_legacy(legacy,mesh)
    copy_data=json.loads(cmds.getAttr(copied+'.outNetData'))
    assert abs(copy_data['positions'][0][0]-json.loads(original)['positions'][0][0]-3)<1e-6
    assert cmds.getAttr(legacy+'.outNetData')==original
    assert cmds.nodeType(copied)=='retopoGuideNode'
    print('PASS legacy coexistence, independent import, world transforms, source preserved')
    print('ALL MAYA SMOKE TESTS PASSED', cmds.about(version=True))


if __name__ == '__main__':
    result = 0
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        result = 1
    finally:
        cmds.file(new=True, force=True)
        if cmds.pluginInfo('aru_retopo_draw_plugin',q=True,loaded=True):
            cmds.unloadPlugin('aru_retopo_draw_plugin')
        cmds.unloadPlugin('aru_retopo_plugin', force=True)
        cmds.unloadPlugin('aru_retopo_guide_plugin', force=True)
        maya.standalone.uninitialize()
    sys.stdout.flush(); sys.stderr.flush()
    # Existing CurveNet VP2 callback destruction can crash Python 3.13 shutdown.
    os._exit(result)
