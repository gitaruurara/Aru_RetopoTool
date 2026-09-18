"""Owned guide nodes, migration, and the combined curve/patch context."""
import os
import json
from maya import cmds
import maya.api.OpenMaya as om
from . import maya_api as api

TYPE = 'retopoGuideNode'


def load():
    name = 'aru_retopo_guide_plugin'
    if not cmds.pluginInfo(name,q=True,loaded=True):
        cmds.loadPlugin(os.path.join(os.path.dirname(__file__),'editor','curvenet',name+'.py'))


def create(reference):
    load()
    reference = api.shape(reference,'mesh')
    with api.undo_chunk('Aru Retopo: create guides'):
        guide = cmds.createNode(TYPE,name='aruRetopoGuideShape#')
        cmds.setAttr(guide+'.meshName',reference,type='string')
        cmds.setAttr(guide+'.netData',json.dumps({'positions':[],'splines':[]}),type='string')
    return guide


def import_legacy(source, reference=None):
    """Copy evaluated CVs; keep the original object and its rig/history intact."""
    load()
    source = api.shape(source,'curveNetNode')
    selection=om.MSelectionList();selection.add(source)
    matrix=selection.getDagPath(0).inclusiveMatrix()
    data=json.loads(cmds.getAttr(source+'.outNetData'))
    for i,p in enumerate(data['positions']):
        q=om.MPoint(*p)*matrix;data['positions'][i]=[q.x,q.y,q.z]
    with api.undo_chunk('Aru Retopo: import guide copy'):
        target=create(reference or cmds.getAttr(source+'.meshName'))
        cmds.setAttr(target+'.netData',json.dumps(data),type='string')
    return target


def attach(node, guide):
    guide=api.shape(guide,TYPE)
    with api.undo_chunk('Aru Retopo: attach owned guides'):
        cmds.connectAttr(guide+'.outNetData',node+'.guideData',force=True)
        cmds.connectAttr(guide+'.worldMatrix[0]',node+'.guideMatrix',force=True)


def edit(node):
    load()
    guide=(cmds.listConnections(node+'.guideData',s=True,d=False,shapes=True) or [None])[0]
    if not guide or cmds.nodeType(guide)!=TYPE:
        raise ValueError('既存CurveNetを「ガイドをコピーして取り込み」で取り込んでください。')
    from .editor.curvenet import curve_net_menu as menu
    from . import patch_context
    patch_context._preferred_owner = node
    cmds.optionVar(sv=('retopoGuideContext_node',guide))
    cmds.select(guide)
    menu._enter_curvenet_context()


def settings():
    from .editor.curvenet import curve_net_toolsettings
    curve_net_toolsettings.show()
