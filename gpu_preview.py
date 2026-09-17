"""Experimental VP2 foreground pass, opt-in until interaction parity is verified.

The second scene pass clears depth only. Maya's own shaded/wire rendering then
occludes rear edges using GPU depth, independent of the reference surface.
"""
import sys
from maya import cmds
from . import maya_api as api
import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as render

# Keep the Python instance alive across development reloads: findRenderOverride
# returns a base wrapper, not the original Python subclass with owned operations.
_override=globals().get('_override')
_saved_panels=globals().get('_saved_panels',{})
_saved_attributes=globals().get('_saved_attributes',{})
_registered_name=globals().get('_registered_name')
_buffer_session=globals().get('_buffer_session')


class Foreground(render.MSceneRender):
    def __init__(self,name='aruRetopoForeground'):
        super().__init__(name)
        self.objects=om.MSelectionList()
    def objectSetOverride(self):return self.objects
    def displayModeOverride(self):return self.kShaded | self.kWireFrame
    def getObjectTypeExclusions(self):return self.kExcludeGrid
    def postEffectsOverride(self):return self.kPostEffectDisableAll
    def cullingOverride(self):return self.kCullBackFaces
    def clearOperation(self):
        op=super().clearOperation();op.setMask(render.MClearOperation.kClearDepth)
        return op


class Preview(render.MRenderOverride):
    NAME='aruRetopoGPUPreview'
    def __init__(self):
        super().__init__(self.NAME)
        self.foreground=Foreground()
        self.guides=Foreground('aruRetopoGuides')
        self.operations=[render.MSceneRender('aruRetopoBase'),self.foreground,self.guides,
                         render.MHUDRender(),render.MPresentTarget('aruRetopoPresent')]
        self.operations[0].clearOperation().setOverridesColors(False)
        self.index=0
    def uiName(self):return 'Aru Retopo GPU Preview (experimental)'
    def supportedDrawAPIs(self):return render.MRenderer.kAllDevices
    def startOperationIterator(self):self.index=0;return True
    def renderOperation(self):return self.operations[self.index]
    def nextRenderOperation(self):self.index+=1;return self.index<len(self.operations)
    def setup(self,destination):pass
    def cleanup(self):pass


def enable(panel,direct_buffer=False):
    global _override,_registered_name,_buffer_session
    if _buffer_session is not None:
        _buffer_session.close();_buffer_session=None
    if _override is None:
        candidate=Preview()
        render.MRenderer.registerOverride(candidate)
        _override=candidate
        _registered_name=Preview.NAME
    if panel not in _saved_panels:
        _saved_panels[panel]=cmds.modelEditor(panel,q=True,rendererOverrideName=True)
    objects=om.MSelectionList()
    meshes=[]
    for node in cmds.ls(type='aruRetopoMesh') or []:
        meshes.extend(cmds.listConnections(api.output_plug(node),source=False,destination=True,type='mesh') or [])
    for mesh in set(meshes):
        objects.add(mesh)
        attr=mesh+'.alwaysDrawOnTop'
        if attr not in _saved_attributes:_saved_attributes[attr]=cmds.getAttr(attr)
        cmds.setAttr(attr,False)
        for name,value in (('backfaceCulling',3),('overrideRGBColors',True)):
            attr=mesh+'.'+name
            if attr not in _saved_attributes:_saved_attributes[attr]=cmds.getAttr(attr)
            cmds.setAttr(attr,value)
        attr=mesh+'.overrideColorRGB'
        if attr not in _saved_attributes:_saved_attributes[attr]=cmds.getAttr(attr)[0]
        cmds.setAttr(attr,.025,.075,.10,type='double3')
    guide_objects=om.MSelectionList()
    for guide in cmds.ls(type='retopoGuideNode') or []:guide_objects.add(guide)
    _override.guides.objects=guide_objects
    for overlay in cmds.ls(type='aruRetopoOverlay') or []:
        objects.add(overlay)
        attr=overlay+'.enabled'
        if attr not in _saved_attributes:_saved_attributes[attr]=cmds.getAttr(attr)
        cmds.setAttr(attr,False)
    _override.foreground.objects=objects
    if direct_buffer:
        from .gpu_buffer_preview import BufferPreview
        _buffer_session=BufferPreview(_override.foreground)
    _set_world_guides(True)
    cmds.modelEditor(panel,e=True,rendererOverrideName=_registered_name)
    cmds.refresh(force=True)


def _set_world_guides(enabled):
    module=sys.modules.get('Aru_RetopoTool.editor.curvenet.curve_net_draw')
    if module is not None:
        module._gpu_world_guides=enabled
        for guide in cmds.ls(type='retopoGuideNode') or []:
            selection=om.MSelectionList();selection.add(guide)
            render.MRenderer.setGeometryDrawDirty(selection.getDependNode(0))


def disable():
    global _override,_registered_name,_buffer_session
    if _buffer_session is not None:
        _buffer_session.close();_buffer_session=None
    for panel,previous in list(_saved_panels.items()):
        if cmds.modelPanel(panel,exists=True):cmds.modelEditor(panel,e=True,rendererOverrideName=previous)
    _saved_panels.clear()
    for attr,value in list(_saved_attributes.items()):
        if cmds.objExists(attr):
            if isinstance(value,tuple):cmds.setAttr(attr,*value,type='double3')
            else:cmds.setAttr(attr,value)
    _saved_attributes.clear()
    _set_world_guides(False)
    cmds.refresh(force=True)

    # Keep the original Python owner until deregistration succeeds.
    # findRenderOverride returns a base wrapper and cannot replace this owner.
    if _override is not None:
        render.MRenderer.deregisterOverride(_override)
        _override=None
        _registered_name=None
