"""Required native graph wiring. All changes are undoable scene operations."""
import os
from maya import cmds
from . import maya_api as api
BINARY_NAME="aru_retopo_mesh_buffer_certified.mll"

def available():
    return ('aruRetopoMeshBuffer' in cmds.allNodeTypes() or
            os.path.isfile(os.path.join(os.path.dirname(__file__),'bin',
                                        cmds.about(version=True),BINARY_NAME)))


def backend(node):
    if not cmds.attributeQuery('nativeBackend',node=node,exists=True):return None
    nodes=cmds.listConnections(node+'.nativeBackend',source=True,destination=False,type='aruRetopoMeshBuffer') or []
    return nodes[0] if len(nodes)==1 else None

def source(node):
    native = backend(node)
    if not native: raise ValueError('Retopo native backend is missing: '+node)
    return native+'.outMesh'

def status(node):
    native=backend(node)
    if not native:return 'ERROR: Retopo native backend is missing'
    plans=cmds.listConnections(node+'.nativePlan',source=True,destination=False,type='aruRetopoPlan') or []
    message=cmds.getAttr(plans[0]+'.status') if plans else 'ERROR: Missing native topology provider'
    if message.startswith('ERROR:'):return message
    native_status=cmds.getAttr(native+'.status') or ''
    return native_status if native_status.startswith('ERROR:') else message

def enable(node):
    if backend(node):return backend(node)
    guide_source=cmds.connectionInfo(node+'.guideData',sourceFromDestination=True)
    if not guide_source:raise ValueError('Guide is not connected')
    guide=guide_source.rsplit('.',1)[0]
    if not cmds.attributeQuery('outPositions',node=guide,exists=True):raise ValueError('最新版のガイドプラグインでMayaを開き直してください。')
    reference=cmds.connectionInfo(node+'.referenceMesh',sourceFromDestination=True)
    matrix=cmds.connectionInfo(node+'.guideMatrix',sourceFromDestination=True)
    if not reference or not matrix:raise ValueError('Reference/guide matrix is not connected')
    root=os.path.dirname(__file__)
    cmds.loadPlugin(os.path.join(root,'aru_retopo_plan_plugin.py'),quiet=True)
    # An older scene may already own this Maya node type. Never register a
    # second version with the same type id in the running session.
    if 'aruRetopoMeshBuffer' not in cmds.allNodeTypes():
        cmds.loadPlugin(os.path.join(root,'bin',cmds.about(version=True),BINARY_NAME),quiet=True)
    created=[]
    with api.undo_chunk('Aru Retopo: native backend'):
        try:
            plan=cmds.createNode('aruRetopoPlan',name='aruRetopoPlan#');created.append(plan)
            native=cmds.createNode('aruRetopoMeshBuffer',name='aruRetopoNative#');created.append(native)
            for name in ('nativeBackend','nativePlan'):
                if not cmds.attributeQuery(name,node=node,exists=True):cmds.addAttr(node,longName=name,attributeType='message')
            cmds.addAttr(native,longName='retopoOwner',attributeType='message')
            cmds.connectAttr(node+'.message',native+'.retopoOwner')
            cmds.connectAttr(native+'.message',node+'.nativeBackend');cmds.connectAttr(plan+'.message',node+'.nativePlan')
            for src,dst in ((guide+'.netData','guideData'),(guide+'.outPositions','guidePositions'),(reference,'referenceMesh'),(matrix,'guideMatrix')):
                cmds.connectAttr(src,plan+'.'+dst)
            for name in ('selectedPatches','subdivisions','rebuildSerial','guideWeight','influenceField','loopReductions'):cmds.connectAttr(node+'.'+name,plan+'.'+name)
            for name in ('stencilOffsets','stencilIndices','stencilWeights','faceCounts','faceIndices','adjacencyOffsets','adjacencyIndices','guideWeights'):
                cmds.connectAttr(plan+'.'+name,native+'.'+name)
            for src,dst in ((guide+'.outPositions','positions'),(reference,'referenceMesh'),(matrix,'guideMatrix')):cmds.connectAttr(src,native+'.'+dst)
            for name in ('relaxIterations','relaxStrength','projectionGuard'):cmds.connectAttr(node+'.'+name,native+'.'+name)
            cmds.setAttr(native+'.projectToReference',True)
            message=status(node)
            if message.startswith('ERROR:'):raise ValueError(message)
            return native
        except Exception:
            for item in reversed(created):
                if cmds.objExists(item):cmds.delete(item)
            raise
