"""Inspect real evaluated data for either an editable locator or a baked mesh."""
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api


def mesh_fn(output):
    shapes = cmds.listRelatives(output, shapes=True, fullPath=True) or [output]
    for shape in shapes:
        if cmds.nodeType(shape) == 'mesh':
            return om.MFnMesh(om.MSelectionList().add(shape).getDagPath(0))
        if cmds.attributeQuery('retopoOwner',node=shape,exists=True):
            owners=cmds.listConnections(shape+'.retopoOwner',s=True,d=False,type='aruRetopoMesh') or []
            if owners:
                plug=om.MSelectionList().add(api.output_plug(owners[0])).getPlug(0)
                return om.MFnMesh(plug.asMObject())
    raise AssertionError('No mesh or retopo locator: '+output)


def face_count(output):
    from Aru_RetopoTool import native_backend
    for shape in cmds.listRelatives(output, shapes=True, fullPath=True) or [output]:
        if cmds.attributeQuery('retopoOwner',node=shape,exists=True):
            owner=cmds.listConnections(shape+'.retopoOwner',s=True,d=False,type='aruRetopoMesh')[0]
            native=native_backend.backend(owner)
            data=om.MSelectionList().add(native+'.faceCounts').getPlug(0).asMObject()
            return len(om.MFnIntArrayData(data).array())
    return mesh_fn(output).numPolygons
