"""Validate actual uploaded VP2 index buffers across topology edits."""
import ctypes as C,json
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import gpu_preview


def run():
    root=Path(__file__).resolve().parents[1]
    lib=C.CDLL(str(root/'bin/2027/aru_retopo_buffer_preview_topology.mll'))
    lib.aru_buffer_items.argtypes=[C.POINTER(C.c_longlong)];lib.aru_buffer_items.restype=None
    values=(C.c_longlong*6)();rows=[]
    shape=cmds.createNode('aruRetopoBufferPreview')
    parent=cmds.listRelatives(shape,parent=True,fullPath=True)[0]
    original=gpu_preview._override.foreground.objects
    objects=om.MSelectionList();objects.add(shape);gpu_preview._override.foreground.objects=objects
    vertices=[(-1.,0.,-1.),(1.,0.,-1.),(1.,0.,1.),(-1.,0.,1.)]
    def hash_indices(indices):
        h=1469598103934665603
        for value in indices:h=((h^value)*1099511628211)&((1<<64)-1)
        return C.c_longlong(h).value
    def check(label,counts,indices,valid=True):
        cmds.setAttr(shape+'.positions',[v for p in vertices for v in p],type='doubleArray')
        cmds.setAttr(shape+'.faceCounts',counts,type='Int32Array')
        cmds.setAttr(shape+'.faceIndices',indices,type='Int32Array')
        cmds.refresh(force=True);lib.aru_buffer_items(values)
        enabled=bool(valid and counts)
        assert list(values)[2:4]==[int(enabled)]*2,(label,list(values))
        if enabled:
            storage=om.MFnMeshData().create();fn=om.MFnMesh();fn.create(om.MPointArray(vertices),counts,indices,parent=storage)
            triangles=list(fn.getTriangles()[1]);edges=set();offset=0
            for count in counts:
                for j in range(count):edges.add(tuple(sorted((indices[offset+j],indices[offset+(j+1)%count]))))
                offset+=count
            edges=[v for edge in sorted(edges) for v in edge]
            assert list(values)[:2]==[len(triangles),len(edges)],(label,list(values))
            assert list(values)[4:]==[hash_indices(triangles),hash_indices(edges)],(label,list(values))
        rows.append(dict(case=label,actual=list(values)))
    try:
        check('quad',[4],[0,1,2,3])
        check('two_triangles',[3,3],[0,1,2,0,2,3])
        check('same_count_rewire',[3,3],[0,1,3,1,2,3])
        check('empty',[],[])
        check('restored_quad',[4],[0,1,2,3])
        check('invalid_index',[4],[0,1,2,9],False)
        check('recover',[4],[0,1,2,3])
        vertices[0]=(-1.1,0.,-1.)
        check('position_only',[4],[0,1,2,3])
        Path(__file__).with_suffix('.json').write_text(json.dumps(rows,indent=2))
    finally:
        gpu_preview._override.foreground.objects=original
        if cmds.objExists(parent):cmds.delete(parent)
        cmds.refresh(force=True)
