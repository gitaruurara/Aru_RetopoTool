"""Candidate owned C++ halfedge walks with the existing Python return shape."""
import ctypes as C
from array import array
from Aru_RetopoTool.native import library
from Aru_RetopoTool.stencil_compiler import view

def regions(positions,splines,normal_at):
    for sp in splines:
        if len(sp)!=4 or any(v<0 or v>=len(positions) for v in sp):raise ValueError('Invalid spline CV indices')
        if sp[0]==sp[3]:raise ValueError('Self-loop spline: insert at least three distinct corners')
    if any(len(p)!=3 for p in positions):raise ValueError('Position requires three coordinates')
    lib=library();I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
    for name,args,result in (
        ('aru_regions_create',[D,C.c_int,I,C.c_int,D],C.c_void_p),
        ('aru_regions_destroy',[C.c_void_p],None),
        ('aru_regions_size',[C.c_void_p,C.c_int],C.c_int),
        ('aru_regions_copy',[C.c_void_p,C.c_int,I,C.c_int],C.c_int)):
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    points=array('d',(v for p in positions for v in p));controls=array('i',(v for sp in splines for v in sp))
    normals=array('d',[0])*(len(positions)*3)
    for ep in dict.fromkeys(ep for sp in splines for ep in (sp[0],sp[3])):
        normal=array('d',normal_at(positions[ep]))
        if len(normal)!=3:raise ValueError('Normal requires three coordinates')
        normals[ep*3:ep*3+3]=normal
    handle=lib.aru_regions_create(view(points),len(positions),view(controls),len(splines),view(normals))
    if not handle:raise ValueError('Invalid curve network geometry')
    try:
        buffers=[]
        for which in range(3):
            size=lib.aru_regions_size(handle,which)
            if size<0:raise RuntimeError('Invalid region buffer')
            values=array('i',[0])*size
            if not lib.aru_regions_copy(handle,which,view(values),size):raise RuntimeError('Cannot copy regions')
            buffers.append(values)
        loops,sides,halfedges=buffers
        if len(loops)==1:raise ValueError('閉じた領域がありません。交点を接続し、3辺以上で領域を囲んでください。')
        return [[tuple((halfedges[k]//2,-1 if halfedges[k]%2 else 1) for k in range(sides[j],sides[j+1]))
                 for j in range(loops[i],loops[i+1])] for i in range(len(loops)-1)]
    finally:lib.aru_regions_destroy(handle)
