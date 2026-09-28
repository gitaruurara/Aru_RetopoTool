"""Disposable benchmark of owned preview snapshots; no global activation."""
import weakref
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import relax_preview as preview
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit


def install():
    cls=preview.RelaxPreview
    original_set=cls._set_positions;original_world=cls._edit_world
    original_commit=cls.commit;original_cancel=cls.cancel
    stats={'reused':0,'fallback':0,'invalidations':0}
    callbacks=set()
    def remove(self):
        callback=getattr(self,'_owned_preview_callback',None)
        if callback is not None:
            om.MMessage.removeCallback(callback);callbacks.discard(callback)
            self._owned_preview_callback=None
        self._owned_preview_valid=False
    def set_positions(self, values):
        if getattr(self,'_owned_preview_callback',None) is None and values:
            selection=om.MSelectionList();selection.add(self.node)
            owner=weakref.ref(self)
            def changed(message,plug,other,*unused):
                mutation=(om.MNodeMessage.kAttributeSet|om.MNodeMessage.kConnectionMade|om.MNodeMessage.kConnectionBroken)
                if not message & mutation:return
                if plug.partialName(useLongNames=True)!='editPreviewPositions':return
                stroke=owner()
                if stroke is not None and not getattr(stroke,'_publishing_preview',False):
                    stroke._owned_preview_valid=False
                    stats['invalidations']+=1
            callback=om.MNodeMessage.addAttributeChangedCallback(selection.getDependNode(0),changed)
            self._owned_preview_callback=callback;callbacks.add(callback)
        self._owned_preview_valid=False
        self._publishing_preview=True
        try:original_set(self,values)
        finally:self._publishing_preview=False
        self._owned_preview_valid=bool(values)
    def world(self):
        self._check()
        if (self.pending is not None and getattr(self,'_owned_preview_valid',False)
                and not edit.is_pose_driven(self.node)):
            selection=om.MSelectionList();selection.add(self.node)
            dag=selection.getDagPath(0);matrix=dag.inclusiveMatrix()
            plug=om.MFnDependencyNode(dag.node()).findPlug('editPreviewPositions',False)
            if matrix==om.MMatrix() and not plug.isDestination:
                stats['reused']+=1
                return self.pending,matrix
        stats['fallback']+=1
        return original_world(self)
    def commit(self,*args,**kwargs):
        try:return original_commit(self,*args,**kwargs)
        finally:remove(self)
    def cancel(self,*args,**kwargs):
        try:return original_cancel(self,*args,**kwargs)
        finally:remove(self)
    cls._set_positions=set_positions;cls._edit_world=world
    cls.commit=commit;cls.cancel=cancel
    def restore():
        for callback in list(callbacks):om.MMessage.removeCallback(callback)
        callbacks.clear()
        cls._set_positions=original_set;cls._edit_world=original_world
        cls.commit=original_commit;cls.cancel=original_cancel
    return stats,restore
