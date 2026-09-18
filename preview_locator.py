"""One persistent GPU locator per editable retopo output; no temporary DAG copies."""
from pathlib import Path
from maya import cmds
from . import native_backend

TYPE = 'aruRetopoBufferPreview'
BINARY = 'aru_retopo_buffer_preview_fast.mll'


def shape(node):
    if not cmds.attributeQuery('previewLocator', node=node, exists=True): return None
    shapes = cmds.listConnections(node+'.previewLocator', s=True, d=False, shapes=True, type=TYPE) or []
    return shapes[0] if shapes else None


def ensure(node, parent=None):
    existing = shape(node)
    if existing: return existing
    if TYPE not in cmds.allNodeTypes():
        cmds.loadPlugin(str(Path(__file__).parent/'bin'/cmds.about(version=True)/BINARY), quiet=True)
    from . import maya_api as api
    with api.undo_chunk('Aru Retopo: persistent preview'):
        native = native_backend.enable(node)
        if parent is None: raise ValueError('A preview parent is required')
        preview = cmds.createNode(TYPE, name='aruRetopoPreviewShape#', parent=parent, skipSelect=True)
        cmds.addAttr(preview, longName='retopoOwner', attributeType='message')
        cmds.connectAttr(node+'.message', preview+'.retopoOwner')
        if not cmds.attributeQuery('previewLocator', node=node, exists=True):
            cmds.addAttr(node, longName='previewLocator', attributeType='message')
        cmds.connectAttr(preview+'.message', node+'.previewLocator')
        for source, destination in (('outPositions','positions'), ('faceCounts','faceCounts'), ('faceIndices','faceIndices')):
            cmds.connectAttr(native+'.'+source, preview+'.'+destination)
        return preview
