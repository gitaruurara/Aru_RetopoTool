"""One owned numeric relax stroke. Caller owns Undo and context lifecycle.

The context owns release/cancel/tool-change/save hooks and the Undo chunk.
"""
from maya import cmds
import maya.api.OpenMaya as om
from . import curve_net_relax as relax
from . import curve_net_edit as edit


class RelaxPreview:
    def __init__(self,node):
        self.node=node
        self.attribute=node+'.editPreviewPositions'
        if not cmds.objExists(self.attribute):
            raise ValueError('Numeric preview requires the current guide plugin')
        if edit.is_pose_driven(node):
            raise ValueError('Cannot preview a pose-driven guide')
        if cmds.getAttr(self.attribute):
            raise ValueError('Another preview is already active')
        self.raw=cmds.getAttr(node+'.netData')
        self.pending=None
        self.affected=set()
        self.closed=False
        self._redraw=True
        self._undo_anchor=False

    def _check(self):
        if self.closed:raise RuntimeError('Relax preview is closed')
        if not cmds.objExists(self.node) or cmds.getAttr(self.node+'.netData')!=self.raw:
            raise RuntimeError('Guide changed outside the relax stroke')

    def world(self):
        self._check()
        # Copy pending topology/bindings once rather than copying base metadata
        # first and immediately replacing it with another full deep copy.
        return relax._world_data(self.node,_source=self.pending)

    def _set_positions(self, values):
        # Preview data is ephemeral. Redo must never resurrect an unowned stroke,
        # including cancellation inside Maya's non-undoable save callback.
        selection=om.MSelectionList();selection.add(self.node)
        dep=om.MFnDependencyNode(selection.getDependNode(0))
        dep.findPlug('editPreviewPositions',False).setMObject(
            om.MFnDoubleArrayData().create(values))

    def write(self,cn):
        self._check()
        if not self._undo_anchor:
            # One empty->empty entry preserves the stroke's Undo boundary.
            cmds.setAttr(self.attribute,[],type='doubleArray')
            self._undo_anchor=True
        self._set_positions([v for p in cn.positions for v in p])
        self.pending=cn
        if self._redraw:edit._dirty_shape_view()

    def _edit_world(self):
        self._check()
        # Only this stroke owns pending. Public world() still returns a copy.
        # Non-identity transforms retain copied snapshots to avoid intermediate
        # world-space mutations when the brush has no affected points.
        return relax._world_data(self.node,_source=self.pending,_reuse_source=True)

    def apply(self,weights,**options):
        try:
            affected=relax.relax(self.node,weights,_world=self._edit_world(),_writer=self.write,**options)
            self.affected.update(affected)
            return affected
        except Exception:
            self.cancel()
            raise

    def brush(self,sx,sy,radius=80.):
        try:
            world=self._edit_world()
            weights=relax.brush_weights(self.node,sx,sy,radius,_world=world)
            affected=relax.relax(self.node,weights,_world=world,_writer=self.write)
            self.affected.update(affected)
            return affected
        except Exception:
            self.cancel()
            raise

    def commit(self,refine=True):
        self._check()
        # Refinement and the final base write are one synchronous operation.
        # Draw only after transient positions are cleared, avoiding stale
        # preview frames and duplicate mesh/GPU work during mouse release.
        self._redraw=False
        try:
            if self.pending is not None:
                if refine and self.affected:
                    self.apply({ep:1. for ep in self.affected},draft=False,smooth=False)
                edit.RetopoGuideAccessor(self.node).write(self.pending,refresh=False)
            self._set_positions([])
            self.pending=None
            self.closed=True
        finally:
            self._redraw=True
        edit._dirty_shape_view()

    def cancel(self):
        if self.closed:return
        if cmds.objExists(self.attribute):
            self._set_positions([])
        self.pending=None
        self.closed=True
        edit._dirty_shape_view()
