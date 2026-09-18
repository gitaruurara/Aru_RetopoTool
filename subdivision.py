"""Owned native Catmull-Clark topology and CSR coefficient arrays."""
import ctypes as C
from array import array
from .native import library
from .stencil_compiler import view

def plan(count,faces,guides,levels):
    lib=library();I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
    definitions=(
        ('aru_subdivision_plan_create',[C.c_int,I,C.c_int,I,C.c_int,I,C.c_int,C.c_int],C.c_void_p),
        ('aru_subdivision_plan_destroy',[C.c_void_p],None),
        ('aru_subdivision_plan_step',[C.c_void_p,C.c_int],C.c_void_p),
        ('aru_subdivision_plan_size',[C.c_void_p,C.c_int],C.c_int),
        ('aru_subdivision_plan_copy_int',[C.c_void_p,C.c_int,I,C.c_int],C.c_int),
        ('aru_subdivision_plan_copy_double',[C.c_void_p,C.c_int,D,C.c_int],C.c_int),
        ('aru_subdivision_size',[C.c_void_p,C.c_int],C.c_int),
        ('aru_subdivision_copy_int',[C.c_void_p,C.c_int,I,C.c_int],C.c_int),
        ('aru_subdivision_copy_weights',[C.c_void_p,D,C.c_int],C.c_int),
    )
    for name,args,result in definitions:
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    offsets=array('i',[0]);vertices=array('i');edges=array('i',[v for edge in guides for v in edge])
    for face in faces:vertices.extend(face);offsets.append(len(vertices))
    handle=lib.aru_subdivision_plan_create(count,view(offsets),len(faces),view(vertices),len(vertices),view(edges),len(guides),levels)
    if not handle:raise ValueError('Invalid subdivision topology')
    try:
        steps=[]
        for level in range(levels):
            stage=lib.aru_subdivision_plan_step(handle,level);row=[]
            for which in (1,2,8):
                size=lib.aru_subdivision_size(stage,which)
                if size<0:raise RuntimeError('Invalid subdivision stage size')
                values=array('d' if which==8 else 'i',[0])*size
                ok=(lib.aru_subdivision_copy_weights(stage,view(values),size) if which==8 else lib.aru_subdivision_copy_int(stage,which,view(values),size))
                if not ok:raise RuntimeError('Cannot copy subdivision stage')
                row.append(values)
            steps.append(tuple(row))
        buffers=[]
        for which in range(11):
            size=lib.aru_subdivision_plan_size(handle,which)
            if size<0:raise RuntimeError('Invalid subdivision plan size')
            values=array('d' if which>=8 else 'i',[0])*size
            ok=(lib.aru_subdivision_plan_copy_double(handle,which-8,view(values),size) if which>=8 else lib.aru_subdivision_plan_copy_int(handle,which,view(values),size))
            if not ok:raise RuntimeError('Cannot copy subdivision plan')
            buffers.append(values)
        return steps,buffers
    finally:lib.aru_subdivision_plan_destroy(handle)
