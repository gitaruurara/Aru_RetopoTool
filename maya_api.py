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
            transform = cmds.createNode('transform', name='aruRetopoMesh#'); created.append(transform)
            output = cmds.createNode('mesh', name=transform+'Shape', parent=transform)
            cmds.setAttr(transform+'.inheritsTransform', False)
            for attr in ('translate', 'rotate', 'scale'):
                for axis in 'XYZ': cmds.setAttr(transform+'.'+attr+axis, lock=True, keyable=False)
            cmds.setAttr(transform+'.inheritsTransform', lock=True)
            cmds.connectAttr(guide+'.outNetData', node+'.guideData')
            cmds.connectAttr(guide+'.worldMatrix[0]', node+'.guideMatrix')
            cmds.connectAttr(reference+'.worldMesh[0]', node+'.referenceMesh')
            cmds.setAttr(node+'.subdivisions', subdivisions)
            cmds.setAttr(node+'.relaxIterations', iterations)
            cmds.setAttr(node+'.guideWeight', guide_weight)
            cmds.connectAttr(node+'.outMesh', output+'.inMesh')
            cmds.sets(output, edit=True, forceElement='initialShadingGroup')
            cmds.setAttr(output+'.displayColors', False)
            # Wire overlay without changing the reference mesh's display state.
            cmds.setAttr(output+'.overrideEnabled', True)
            cmds.setAttr(output+'.overrideShading', False)
            cmds.setAttr(output+'.overrideColor', 17)
            set_foreground(node, True)
            status = cmds.getAttr(node+'.status') or ''
            if status.startswith('ERROR:'): raise ValueError(status[7:])
            cmds.select(transform)
            return transform, node
        except Exception:
            for item in reversed(created):
                if cmds.objExists(item): cmds.delete(item)
            raise


def generator_from_selection():
    for selected in cmds.ls(selection=True, objectsOnly=True, long=True) or []:
        if cmds.nodeType(selected) == 'aruRetopoMesh': return selected
        nodes = [selected] + (cmds.listRelatives(selected, shapes=True, fullPath=True) or [])
        for node in nodes:
            connections = cmds.listConnections(node, source=True, destination=False, type='aruRetopoMesh') or []
            if connections: return connections[0]
    raise ValueError('生成済みのRetopoメッシュを選択してください。')


def rebuild(node):
    with undo_chunk('Aru Retopo: rebuild'):
        cmds.setAttr(node+'.rebuildSerial', cmds.getAttr(node+'.rebuildSerial')+1)
    return cmds.getAttr(node+'.status')


def foreground_enabled(node):
    overlays = cmds.listConnections(node+'.outMesh', s=False, d=True, shapes=True, type='aruRetopoOverlay') or []
    return bool(overlays) and all(cmds.getAttr(s+'.enabled') for s in overlays)


def _preview_surface(node, outputs):
    """An opaque shaded surface masks rear faces; display wires are separate."""
    if not cmds.attributeQuery('previewShadingGroup', node=node, exists=True):
        cmds.addAttr(node, longName='previewShadingGroup', attributeType='message')
    groups = cmds.listConnections(node+'.previewShadingGroup', s=True, d=False) or []
    if groups:
        group = groups[0]
    else:
        material = cmds.shadingNode('lambert', asShader=True, name='aruRetopoPreviewMaterial#')
        cmds.setAttr(material+'.color', .16, .40, .46, type='double3')
        cmds.setAttr(material+'.transparency', 0, 0, 0, type='double3')
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name='aruRetopoPreviewSG#')
        cmds.connectAttr(material+'.outColor', group+'.surfaceShader')
        cmds.connectAttr(group+'.message', node+'.previewShadingGroup')
    for output in outputs:
        current = cmds.listConnections(output, type='shadingEngine') or []
        if not current or all(g in ('initialShadingGroup', group) for g in current):
            cmds.sets(output, edit=True, forceElement=group)


def set_foreground(node, enabled=True):
    """Attach a non-selectable overlay to each output; original mesh stays editable."""
    path = os.path.join(os.path.dirname(__file__), 'aru_retopo_draw_plugin.py')
    if not cmds.pluginInfo('aru_retopo_draw_plugin', q=True, loaded=True): cmds.loadPlugin(path)
    outputs = cmds.listConnections(node+'.outMesh', s=False, d=True, shapes=True, type='mesh') or []
    with undo_chunk('Aru Retopo: foreground display'):
        _preview_surface(node, outputs)
        for output in outputs:
            cmds.setAttr(output+'.overrideShading', True)
            cmds.setAttr(output+'.alwaysDrawOnTop', bool(enabled))
            parent = cmds.listRelatives(output, parent=True, fullPath=True)[0]
            overlays = cmds.listRelatives(parent, shapes=True, fullPath=True, type='aruRetopoOverlay') or []
            if not overlays and enabled:
                overlay = cmds.createNode('aruRetopoOverlay', name='aruRetopoOverlayShape#', parent=parent, skipSelect=True)
                overlays = [overlay]
            for overlay in overlays:
                # Support an already-loaded development schema without unloading
                # the plugin or clearing the artist's undo history.
                if not cmds.attributeQuery('inputMesh', node=overlay, exists=True):
                    cmds.addAttr(overlay, longName='inputMesh', dataType='mesh')
                if not cmds.attributeQuery('enabled', node=overlay, exists=True):
                    cmds.addAttr(overlay, longName='enabled', attributeType='bool', defaultValue=True)
                if not cmds.isConnected(node+'.outMesh', overlay+'.inputMesh'):
                    cmds.connectAttr(node+'.outMesh', overlay+'.inputMesh')
                cmds.setAttr(overlay+'.enabled', bool(enabled))


def bake(node):
    outputs = cmds.listConnections(node+'.outMesh', source=False, destination=True, shapes=True, type='mesh') or []
    if not outputs: raise ValueError('生成メッシュがありません。')
    status = cmds.getAttr(node+'.status') or ''
    if status.startswith('ERROR:'): raise ValueError(status)
    transform = cmds.listRelatives(outputs[0], parent=True, fullPath=True)[0]
    with undo_chunk('Aru Retopo: bake copy'):
        result = cmds.duplicate(transform, name='aruRetopoBaked#', returnRootsOnly=True,
                                inputConnections=False, upstreamNodes=False)[0]
        cmds.delete(result, constructionHistory=True)
        overlays = cmds.listRelatives(result, shapes=True, fullPath=True, type='aruRetopoOverlay') or []
        if overlays: cmds.delete(overlays)
        for attr in ('translate', 'rotate', 'scale'):
            for axis in 'XYZ': cmds.setAttr(result+'.'+attr+axis, lock=False, keyable=True)
        cmds.setAttr(result+'.inheritsTransform', lock=False)
        for sh in cmds.listRelatives(result, shapes=True, fullPath=True) or []:
            cmds.setAttr(sh+'.overrideEnabled', False)
            cmds.setAttr(sh+'.alwaysDrawOnTop', False)
        cmds.select(result)
    return result
