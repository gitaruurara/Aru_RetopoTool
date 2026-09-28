"""Owned native Catmull-Clark topology and CSR coefficient arrays."""
import ctypes as C
from array import array
from Aru_RetopoTool.native import library
from Aru_RetopoTool.stencil_compiler import view

def plan(count,faces,guides,levels):
    lib=library();I=C.POINTER(C.c_int);D=C.POINTER(C.c_double)
    definitions=(
        ('aru_subdivision_plan_create',[C.c_int,I,C.c_int,I,C.c_int,I,C.c_int,C.c_int],C.c_void_p),
        ('aru_subdivision_plan_destroy',[C.c_void_p],None),
        ('aru_subdivision_plan_compile',[C.c_void_p,I,C.c_int,I,C.c_int,I,C.c_int,I,I,C.c_int],C.c_void_p),
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
        steps=Steps(lib,handle,levels)
        buffers=[]
        for which in range(11):
            size=lib.aru_subdivision_plan_size(handle,which)
            if size<0:raise RuntimeError('Invalid subdivision plan size')
            values=array('d' if which>=8 else 'i',[0])*size
            ok=(lib.aru_subdivision_plan_copy_double(handle,which-8,view(values),size) if which>=8 else lib.aru_subdivision_plan_copy_int(handle,which,view(values),size))
            if not ok:raise RuntimeError('Cannot copy subdivision plan')
            buffers.append(values)
        return steps,buffers
    except BaseException:
        lib.aru_subdivision_plan_destroy(handle)
        if 'steps' in locals():steps.handle=None
        raise


class Steps:
    """Own the native topology; materialize diagnostic step arrays only on demand."""
    def __init__(self,lib,handle,levels):
        self.lib,self.handle,self.levels=lib,handle,levels
        self._cache={}
    def close(self):
        if self.handle:self.lib.aru_subdivision_plan_destroy(self.handle);self.handle=None
    def __del__(self):self.close()
    def __len__(self):return self.levels
    def __getitem__(self,level):
        if not self.handle:raise RuntimeError('Subdivision plan closed')
        if level<0:level+=self.levels
        if not 0<=level<self.levels:raise IndexError(level)
        if level not in self._cache:
            stage=self.lib.aru_subdivision_plan_step(self.handle,level);row=[]
            for which in (1,2,8):
                size=self.lib.aru_subdivision_size(stage,which)
                if size<0:raise RuntimeError('Invalid subdivision stage size')
                values=array('d' if which==8 else 'i',[0])*size
                ok=(self.lib.aru_subdivision_copy_weights(stage,view(values),size) if which==8 else self.lib.aru_subdivision_copy_int(stage,which,view(values),size))
                if not ok:raise RuntimeError('Cannot copy subdivision stage')
                row.append(values)
            self._cache[level]=tuple(row)
        return self._cache[level]
    def compile(self,endpoints,splines,sides):
        if not self.handle:raise RuntimeError('Subdivision plan closed')
        if any(len(sp)!=4 for sp in splines):raise ValueError('Spline requires four controls')
        eps=array('i',endpoints);controls=array('i',(v for sp in splines for v in sp))
        offsets=array('i',[0]);sources=array('i');directions=array('i')
        for side in sides:
            for source,direction in side:sources.append(source);directions.append(direction)
            offsets.append(len(sources))
        result=self.lib.aru_subdivision_plan_compile(self.handle,view(eps),len(eps),view(controls),len(splines),
                view(offsets),len(sides),view(sources),view(directions),len(sources))
        if not result:raise ValueError('Cannot compile subdivision plan')
        try:
            size=self.lib.aru_stencil_result_size(result)
            count=self.lib.aru_subdivision_plan_size(self.handle,1)
            offsets=array('i',[0])*count;ids=array('i',[0])*size;weights=array('d',[0])*size
            if not self.lib.aru_stencil_result_copy(result,view(offsets),len(offsets),view(ids),view(weights),size):
                raise RuntimeError('Cannot copy compiled plan')
            return offsets.tolist(),ids.tolist(),weights.tolist()
        finally:self.lib.aru_stencil_result_destroy(result)
