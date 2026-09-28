"""Temporary GUI patch; install only in a disposable Maya benchmark."""
import inspect
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw


def index_key(owner, names):
    from Aru_RetopoTool.editor.curvenet.curve_net_draw import _BEZIER_N
    groups=getattr(owner,'_gpu_control_indices',())
    return (len(owner._positions),getattr(owner,'_draw_topology_key',None),
        _BEZIER_N,getattr(owner,'_gpu_curve_active',False),
        tuple((item_names,indices.tobytes()) for item_names,indices in groups),
        tuple(owner._active_indices),names,owner._is_valid)


def install():
    cls=draw.RetopoGuideGeometryOverride
    old_items=cls.updateRenderItems;old_populate=cls.populateGeometry
    inherited=getattr(cls,'isIndexingDirty',None)
    stats={'queries':0,'reused':0,'uploads':0,'failed':0}
    def update_items(self,path,items):
        before=tuple(items[i].name() for i in range(len(items)))
        old_items(self,path,items)
        after=tuple(items[i].name() for i in range(len(items)))
        from Aru_RetopoTool.editor.curvenet.curve_net_draw import _BEZIER_N
        groups=getattr(self,'_gpu_control_indices',())
        # Own immutable byte snapshots: same-sized selection/topology edits
        # and reused NumPy allocations must invalidate the index buffers.
        self._candidate_index_key=index_key(self,after)
        self._candidate_index_dirty=(before!=after or self._candidate_index_key!=getattr(self,'_candidate_uploaded_key',None))
    def indexing(self,item):
        stats['queries']+=1
        dirty=getattr(self,'_candidate_index_dirty',True)
        if not dirty:stats['reused']+=1
        return dirty
    source=inspect.getsource(old_populate)
    import textwrap
    source=textwrap.dedent(source)
    source=source.replace('addr = vb.acquire(nPos, True)',
        "addr = vb.acquire(nPos, True)\n            if not addr:raise RuntimeError('Cannot allocate guide vertices')")
    source=source.replace('if gpu_curves:upload_indices(self,renderItems,geo)',
        "if gpu_curves and getattr(self,'_candidate_index_dirty',True):upload_indices(self,renderItems,geo)")
    source=source.replace('n_active = len(active)',
        "if not getattr(self,'_candidate_index_dirty',True):return\n    stats['uploads']+=1\n    n_active = len(active)")
    source=source.replace('if n_active == 0:\n        return',
        'if n_active == 0:\n        self._candidate_uploaded_key=self._candidate_index_key\n        return')
    source=source.replace('ib.commit(addr)\n            rItem.associateWithIndexBuffer(ib)',
        "ib.commit(addr)\n            else:\n                stats['failed']+=1\n                raise RuntimeError('Cannot allocate selection indices')\n            rItem.associateWithIndexBuffer(ib)\n            self._candidate_uploaded_key=self._candidate_index_key")
    scope=dict(draw.__dict__,stats=stats);exec(source,scope)
    cls.updateRenderItems=update_items;cls.isIndexingDirty=indexing;cls.populateGeometry=scope['populateGeometry']
    def restore():
        cls.updateRenderItems=old_items;cls.populateGeometry=old_populate
        if inherited is None:delattr(cls,'isIndexingDirty')
        else:cls.isIndexingDirty=inherited
    return stats,restore
