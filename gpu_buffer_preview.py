"""Owned, non-persistent direct GPU display session for the native backend.

Explicit opt-in only. Maya meshes remain the authoritative editable/exportable
outputs; temporary sibling shapes bypass their VP2 mesh conversion while active.
"""
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om


class BufferPreview:
    def __init__(self, foreground):
        self.foreground = foreground
        self.original = foreground.objects
        self.shapes = []
        self.visibility = []
        self.callbacks = []
        self.closed = False
        self._start()

    def _start(self):
        try:
            if 'aruRetopoBufferPreview' not in cmds.allNodeTypes():
                plugin = Path(__file__).parent / 'bin' / cmds.about(version=True) / 'aru_retopo_buffer_preview_fast.mll'
                cmds.loadPlugin(str(plugin), quiet=True)
            objects = om.MSelectionList()
            expanded = om.MSelectionList()
            for index in range(self.original.length()):
                path = self.original.getDagPath(index)
                if path.node().hasFn(om.MFn.kTransform):
                    children = cmds.ls(path.fullPathName(), dag=True, shapes=True, long=True) or []
                    if children:
                        for child in children: expanded.add(child)
                        continue
                expanded.add(path)
            for index in range(expanded.length()):
                path = expanded.getDagPath(index)
                mesh = path.node()
                fn = om.MFnDependencyNode(mesh)
                if not mesh.hasFn(om.MFn.kMesh) or path.isInstanced():
                    objects.add(path)
                    continue
                inputs = fn.findPlug('inMesh', False).connectedTo(True, False)
                visibility = fn.findPlug('visibility', False)
                if (len(inputs) != 1 or
                    om.MFnDependencyNode(inputs[0].node()).typeName != 'aruRetopoMeshBuffer' or
                    visibility.isLocked or visibility.isConnected or not visibility.asBool()):
                    objects.add(path)
                    continue
                native = om.MFnDependencyNode(inputs[0].node())
                parent = om.MFnDagNode(mesh).parent(0)
                modifier = om.MDagModifier()
                shape = modifier.createNode('aruRetopoBufferPreview', parent)
                modifier.doIt()
                self.shapes.append(om.MObjectHandle(shape))
                preview = om.MFnDependencyNode(shape)
                preview.setDoNotWrite(True)
                wires = om.MDGModifier()
                for source, destination in (('outPositions', 'positions'), ('faceCounts', 'faceCounts'), ('faceIndices', 'faceIndices')):
                    wires.connect(native.findPlug(source, False), preview.findPlug(destination, False))
                wires.doIt()
                self.visibility.append((om.MObjectHandle(mesh), visibility.asBool()))
                visibility.setBool(False)
                objects.add(om.MDagPath.getAPathTo(shape))
            self.foreground.objects = objects
            for event in (om.MSceneMessage.kBeforeSave, om.MSceneMessage.kBeforeNew, om.MSceneMessage.kBeforeOpen):
                self.callbacks.append(om.MSceneMessage.addCallback(event, self._stop))
            for event in ('Undo', 'Redo'):
                self.callbacks.append(om.MEventMessage.addEventCallback(event, self._stop))
        except Exception:
            self.close()
            raise

    def _stop(self, *unused):
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for callback in self.callbacks:
            om.MMessage.removeCallback(callback)
        self.callbacks.clear()
        self.foreground.objects = self.original
        failures = []
        for handle, visible in self.visibility:
            if handle.isValid() and handle.isAlive():
                try:
                    om.MFnDependencyNode(handle.object()).findPlug('visibility', False).setBool(visible)
                except RuntimeError as exc:
                    failures.append(str(exc))
        self.visibility.clear()
        for handle in reversed(self.shapes):
            if handle.isValid() and handle.isAlive():
                try:
                    modifier = om.MDagModifier()
                    modifier.deleteNode(handle.object())
                    modifier.doIt()
                except RuntimeError as exc:
                    failures.append(str(exc))
        self.shapes.clear()
        if failures:
            cmds.warning('Aru Retopo GPU preview cleanup: ' + '; '.join(failures))
