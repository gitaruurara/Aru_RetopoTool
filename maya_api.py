"""Undoable scene operations. Importing this module does not change the scene."""
import os
from contextlib import contextmanager
from maya import cmds
import maya.api.OpenMaya as om


@contextmanager
def undo_chunk(name):
    cmds.undoInfo(openChunk=True, chunkName=name)
    try: yield
    finally: cmds.undoInfo(closeChunk=True)


def load_plugin():
    from .native import library
    library()
    path = os.path.join(os.path.dirname(__file__), 'aru_retopo_plugin.py')
    if not cmds.pluginInfo('aru_retopo_plugin', q=True, loaded=True): cmds.loadPlugin(path)


def shape(node, kind):
    matches = cmds.ls(node, long=True, objectsOnly=True) or []
    if len(matches) != 1: raise ValueError('オブジェクトを1つ指定してください: '+node)
    node = matches[0]
    candidates = [node] if cmds.nodeType(node) == kind else (cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True, type=kind) or [])
    if len(candidates) != 1: raise ValueError('{} を1つ指定してください: {}'.format(kind, node))
    return candidates[0]


def create(guide, reference, subdivisions=2, iterations=3, guide_weight=1.):
    load_plugin()
    from .guides import TYPE
    guide, reference = shape(guide, TYPE), shape(reference, 'mesh')
    if not 1 <= subdivisions <= 6: raise ValueError('Subdivision must be 1..6')
    if not 0 <= iterations <= 30 or not 0 <= guide_weight <= 1: raise ValueError('Invalid relaxation settings')
    # worldMesh[0]/worldMatrix[0] must refer to the selected non-instanced path.
    for source in (guide, reference):
        selection = om.MSelectionList(); selection.add(source)
        if om.MFnDagNode(selection.getDagPath(0)).isInstanced():
            raise ValueError('インスタンスを複製して通常のオブジェクトにしてから指定してください。')
    created = []
    with undo_chunk('Aru Retopo: create'):
        try:
            node = cmds.createNode('aruRetopoMesh', name='aruRetopoGenerator#'); created.append(node)
            if not cmds.attributeQuery('selectedPatches',node=node,exists=True):
                cmds.addAttr(node,longName='selectedPatches',dataType='string')
            cmds.setAttr(node+'.selectedPatches','[]',type='string')
            transform = cmds.createNode('transform', name='aruRetopoPreview#'); created.append(transform)
            cmds.setAttr(transform+'.inheritsTransform', False)
            for attr in ('translate', 'rotate', 'scale'):
                for axis in 'XYZ': cmds.setAttr(transform+'.'+attr+axis, lock=True, keyable=False)
            cmds.setAttr(transform+'.inheritsTransform', lock=True)
            cmds.connectAttr(guide+'.outNetData', node+'.guideData')
            if cmds.attributeQuery('outPositions', node=guide, exists=True) and cmds.attributeQuery('guidePositions', node=node, exists=True):
                cmds.connectAttr(guide+'.netData', node+'.guideRestData')
                cmds.connectAttr(guide+'.outPositions', node+'.guidePositions')
            cmds.connectAttr(guide+'.worldMatrix[0]', node+'.guideMatrix')
            cmds.connectAttr(reference+'.worldMesh[0]', node+'.referenceMesh')
            cmds.setAttr(node+'.subdivisions', subdivisions)
            cmds.setAttr(node+'.relaxIterations', iterations)
            cmds.setAttr(node+'.guideWeight', guide_weight)
            from . import preview_locator
            preview_locator.ensure(node, parent=transform)
            set_foreground(node, True)
            status = read_status(node)
            if status.startswith('ERROR:'): raise ValueError(status[7:])
            cmds.select(transform)
            return transform, node
        except Exception:
            if created and cmds.objExists(created[0]):
                for attr in ('nativeBackend','nativePlan'):
                    if cmds.attributeQuery(attr,node=created[0],exists=True):
                        created.extend(cmds.listConnections(created[0]+'.'+attr,s=True,d=False) or [])
            for item in reversed(created):
                if cmds.objExists(item): cmds.delete(item)
            raise


def output_plug(node):
    from .native_backend import source
    return source(node)


def read_status(node):
    from .native_backend import status
    return status(node)


def generator_for_guide(guide, reference=None):
    """Resolve an existing owner without creating another output on tool entry."""
    from .guides import TYPE
    guide = shape(guide, TYPE)
    nodes = sorted(set(cmds.listConnections(guide+'.outNetData', s=False, d=True,
                                           type='aruRetopoMesh') or []))
    if reference:
        reference = shape(reference, 'mesh')
        nodes = [node for node in nodes if reference in
                 (cmds.ls(cmds.listConnections(node+'.referenceMesh', s=True, d=False,
                                               shapes=True) or [], long=True) or [])]
    if len(nodes) > 1:
        raise ValueError('このガイドには複数のRetopoメッシュがあります。使用する生成メッシュを「選択から読み込み」で指定してください。')
    return nodes[0] if nodes else None


def generator_from_selection():
    for selected in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
        if cmds.nodeType(selected) == 'aruRetopoMesh': return selected
        nodes = [selected] + (cmds.listRelatives(selected, shapes=True, fullPath=True) or [])
        for node in nodes:
            if cmds.attributeQuery('retopoOwner', node=node, exists=True):
                owners = cmds.listConnections(node+'.retopoOwner', s=True, d=False, type='aruRetopoMesh') or []
                if owners: return owners[0]
            if cmds.nodeType(node) == 'retopoGuideNode':
                owner = generator_for_guide(node)
                if owner: return owner
    raise ValueError('リトポガイドまたは生成ロケーターを選択してください。')


def rebuild(node):
    with undo_chunk('Aru Retopo: rebuild'):
        cmds.setAttr(node+'.rebuildSerial', cmds.getAttr(node+'.rebuildSerial')+1)
    return read_status(node)


def display_shapes(node):
    from . import preview_locator
    locator = preview_locator.shape(node)
    return [locator] if locator else []


def foreground_enabled(node):
    return cmds.getAttr(node+'.displayInFront') if cmds.attributeQuery('displayInFront',node=node,exists=True) else True


def set_foreground(node, enabled=True):
    """Attach hover/gesture overlay; the persistent locator draws faces and edges."""
    path = os.path.join(os.path.dirname(__file__), 'aru_retopo_draw_plugin.py')
    if not cmds.pluginInfo('aru_retopo_draw_plugin', q=True, loaded=True): cmds.loadPlugin(path)
    outputs = display_shapes(node)
    with undo_chunk('Aru Retopo: foreground display'):
        if not cmds.attributeQuery('displayInFront', node=node, exists=True):
            cmds.addAttr(node, longName='displayInFront', attributeType='bool', defaultValue=True)
        cmds.setAttr(node+'.displayInFront', bool(enabled))
        for output in outputs:
            parent = cmds.listRelatives(output, parent=True, fullPath=True)[0]
            overlays = cmds.listRelatives(parent, shapes=True, fullPath=True, type='aruRetopoOverlay') or []
            if not overlays and enabled:
                overlay = cmds.createNode('aruRetopoOverlay', name='aruRetopoOverlayShape#', parent=parent, skipSelect=True)
                overlays = [overlay]
            for overlay in overlays:
                if not cmds.isConnected(output_plug(node), overlay+'.inputMesh'):
                    cmds.connectAttr(output_plug(node), overlay+'.inputMesh')
                cmds.setAttr(overlay+'.enabled', False)


def bake(node):
    """Create the first ordinary mesh from evaluated data, with no live history."""
    status = read_status(node)
    if status.startswith('ERROR:'): raise ValueError(status)
    selection = om.MSelectionList(); selection.add(output_plug(node))
    data = selection.getPlug(0).asMObject()
    if data.isNull(): raise ValueError('生成メッシュがありません。')
    with undo_chunk('Aru Retopo: bake copy'):
        result = cmds.createNode('transform', name='aruRetopoBaked#')
        output = cmds.createNode('mesh', name=result+'Shape', parent=result)
        # Command connections are undoable; disconnect retains an independent value.
        cmds.connectAttr(output_plug(node), output+'.inMesh')
        om.MSelectionList().add(output+'.outMesh').getPlug(0).asMObject()
        cmds.disconnectAttr(output_plug(node), output+'.inMesh')
        cmds.sets(output, edit=True, forceElement='initialShadingGroup')
        cmds.select(result)
    return result
