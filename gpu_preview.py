"""VP2 retopo passes sharing scene depth with a small display-only bias."""
import sys
from maya import cmds
from . import maya_api as api
import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as render
import maya.api.OpenMayaUI as omui

# Keep the Python instance alive across development reloads: findRenderOverride
# returns a base wrapper, not the original Python subclass with owned operations.
_override=globals().get('_override')
_saved_panels=globals().get('_saved_panels',{})
_registered_name=globals().get('_registered_name')



_reference_nodes=globals().get('_reference_nodes')
_reference_callbacks=globals().get('_reference_callbacks',[])


def _invalidate_references(*args):
    global _reference_nodes
    _reference_nodes=None


def _reference_objects():
    """Cache node discovery, but read connections and meshName every frame."""
    global _reference_nodes
    if not _reference_callbacks:
        try:
            for kind in ('aruRetopoMesh','retopoGuideNode'):
                _reference_callbacks.append(om.MDGMessage.addNodeAddedCallback(_invalidate_references,kind))
                _reference_callbacks.append(om.MDGMessage.addNodeRemovedCallback(_invalidate_references,kind))
        except Exception:
            for callback in _reference_callbacks:om.MMessage.removeCallback(callback)
            _reference_callbacks.clear()
    if _reference_nodes is None or not _reference_callbacks:
        nodes=[]
        for kind in ('aruRetopoMesh','retopoGuideNode'):
            for name in cmds.ls(type=kind) or []:
                selection=om.MSelectionList();selection.add(name)
                nodes.append((kind,om.MObjectHandle(selection.getDependNode(0))))
        _reference_nodes=nodes
    return _reference_nodes


def _reference_meshes():
    references=set()
    for kind,handle in _reference_objects():
        if not handle.isValid() or not handle.isAlive():continue
        fn=om.MFnDependencyNode(handle.object())
        if kind=='retopoGuideNode':
            mesh=fn.findPlug('meshName',False).asString()
            if mesh:references.add(mesh)
        else:
            for source in fn.findPlug('referenceMesh',False).connectedTo(True,False):
                if source.node().hasFn(om.MFn.kDagNode):
                    references.add(om.MFnDagNode(source.node()).fullPathName())
    return references


def _depth_limits(panel):
    """Bound display bias in reference-object units, independently of zoom."""
    camera=cmds.modelPanel(panel,q=True,camera=True)
    selection=om.MSelectionList();selection.add(camera)
    camera_path=selection.getDagPath(0)
    if camera_path.node().hasFn(om.MFn.kTransform):camera_path.extendToShape()
    camera_fn=om.MFnCamera(camera_path)
    view=camera_path.inclusiveMatrixInverse()
    references=_reference_meshes()
    # A screen/zoom-based cap shrinks the bias below polygon chord error at
    # close range. Bound only by the reference geometry in world units.
    fraction=float('inf')
    offset=float('inf')
    found=False
    for mesh in references:
        selection=om.MSelectionList()
        try:selection.add(mesh)
        except RuntimeError:continue
        path=selection.getDagPath(0)
        if path.node().hasFn(om.MFn.kTransform):path.extendToShape()
        if not path.node().hasFn(om.MFn.kMesh):continue
        bounds=om.MFnDagNode(path).boundingBox
        lo,hi=bounds.min,bounds.max;world=path.inclusiveMatrix()
        extents=[(om.MVector(hi.x-lo.x,0,0)*world).length(),
                 (om.MVector(0,hi.y-lo.y,0)*world).length(),
                 (om.MVector(0,0,hi.z-lo.z)*world).length()]
        positive=[extent for extent in extents if extent>0.]
        if not positive:continue
        tolerance=min(positive)*.02
        depths=[-(om.MPoint(x,y,z)*world*view).z
                for x in (lo.x,hi.x) for y in (lo.y,hi.y) for z in (lo.z,hi.z)]
        farthest=max(depths)
        if farthest<=0.:continue
        fraction=min(fraction,tolerance/farthest)
        offset=min(offset,tolerance)
        found=True
    return (fraction,offset) if found else (0.,0.)


class Foreground(render.MSceneRender):
    def __init__(self,name='aruRetopoForeground'):
        super().__init__(name)
        self.objects=om.MSelectionList()
        self.panel=None
        self.depth_fraction=0.
        self.depth_offset=0.
        self._camera=render.MCameraOverride()
    def objectSetOverride(self):return self.objects
    def displayModeOverride(self):return self.kShaded | self.kWireFrame
    def getObjectTypeExclusions(self):return self.kExcludeGrid | self.kExcludeMeshes
    def renderFilterOverride(self):return self.kRenderAllItems
    def postEffectsOverride(self):return self.kPostEffectDisableAll
    def cullingOverride(self):return self.kCullBackFaces
    def cameraOverride(self):
        if not self.panel:return None
        camera=cmds.modelPanel(self.panel,q=True,camera=True)
        selection=om.MSelectionList();selection.add(camera)
        path=selection.getDagPath(0)
        if path.node().hasFn(om.MFn.kTransform):path.extendToShape()
        fn=om.MFnCamera(path)
        override=self._camera
        override.mCameraPath=path
        override.mUseProjectionMatrix=True
        override.mProjectionMatrix=omui.M3dView.getM3dViewFromModelPanel(self.panel).projectionMatrix()
        override.mUseNearClippingPlane=True
        override.mUseFarClippingPlane=True
        # VP2 rebuilds projection Z from these clipping planes even with a
        # projection matrix override. Keep XY and scene geometry untouched.
        multiplier=1.2 if self.name()=="aruRetopoGuides" else 1.
        factor=self.depth_fraction*multiplier
        if fn.isOrtho():
            offset=self.depth_offset*multiplier
            override.mNearClippingPlane=fn.nearClippingPlane+offset
            override.mFarClippingPlane=fn.farClippingPlane+offset
        else:
            override.mNearClippingPlane=fn.nearClippingPlane*(1.+factor)
            override.mFarClippingPlane=fn.farClippingPlane*(1.+factor)
        return override
    def clearOperation(self):
        op=super().clearOperation();op.setMask(0)
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
    def setup(self,destination):
        self.foreground.panel=destination
        self.guides.panel=destination
        fraction,offset=_depth_limits(destination)
        for operation in (self.foreground,self.guides):
            operation.depth_fraction=fraction
            operation.depth_offset=offset
    def cleanup(self):pass


def enable(panel):
    global _override,_registered_name
    if _override is None:
        candidate=Preview()
        render.MRenderer.registerOverride(candidate)
        _override=candidate
        _registered_name=Preview.NAME
    objects=om.MSelectionList()
    for node in cmds.ls(type='aruRetopoMesh') or []:
        if api.foreground_enabled(node):
            for display in api.display_shapes(node): objects.add(display)
    guide_objects=om.MSelectionList()
    for guide in cmds.ls(type='retopoGuideNode') or []:guide_objects.add(guide)
    _override.guides.objects=guide_objects
    for overlay in cmds.ls(type='aruRetopoOverlay') or []:
        objects.add(overlay)
    _override.foreground.objects=objects
    _set_world_guides(True)
    # GPU guide buffers are shared by all panels. Every panel must use the
    # matching foreground pass, including front/side views after a layout switch.
    for destination in cmds.getPanel(type='modelPanel') or [panel]:
        if destination not in _saved_panels:
            _saved_panels[destination]=cmds.modelEditor(destination,q=True,rendererOverrideName=True)
        cmds.modelEditor(destination,e=True,rendererOverrideName=_registered_name)
    cmds.refresh(force=True)


def _set_world_guides(enabled):
    module=sys.modules.get('Aru_RetopoTool.editor.curvenet.curve_net_draw')
    if module is not None:
        module._gpu_world_guides=enabled
        for guide in cmds.ls(type='retopoGuideNode') or []:
            selection=om.MSelectionList();selection.add(guide)
            render.MRenderer.setGeometryDrawDirty(selection.getDependNode(0))


def disable():
    global _override,_registered_name,_reference_nodes
    for callback in _reference_callbacks:om.MMessage.removeCallback(callback)
    _reference_callbacks.clear();_reference_nodes=None
    for panel,previous in list(_saved_panels.items()):
        if cmds.modelPanel(panel,exists=True):cmds.modelEditor(panel,e=True,rendererOverrideName=previous)
    _saved_panels.clear()
    _set_world_guides(False)
    cmds.refresh(force=True)

    # Keep the original Python owner until deregistration succeeds.
    # findRenderOverride returns a base wrapper and cannot replace this owner.
    if _override is not None:
        render.MRenderer.deregisterOverride(_override)
        _override=None
        _registered_name=None
