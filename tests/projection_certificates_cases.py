"""Candidate cache versus existing C ABI, across repeated small and large edits."""
import ctypes as C, json, math, os, random, sys, traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
root=Path(__file__).resolve().parents[1]
D=C.POINTER(C.c_double);I=C.POINTER(C.c_int)
def load(name):
    lib=C.CDLL(str(root/'bin'/cmds.about(version=True)/('aru_retopo_mesh_buffer_'+name+'.mll')))
    lib.aru_surface_create.argtypes=[D,C.c_int,I,C.c_int];lib.aru_surface_create.restype=C.c_void_p
    lib.aru_surface_destroy.argtypes=[C.c_void_p]
    lib.aru_relax.argtypes=[C.c_void_p,D,C.c_int,I,I,D,C.c_int,C.c_double,I,C.c_int]
    return lib
candidate_name=os.environ.get('ARU_TEST_CERTIFICATE_CANDIDATE','certificates')
base=load('numeric_t16');candidate=load(candidate_name)
def doubles(values):return (C.c_double*len(values))(*values)
def ints(values):return (C.c_int*len(values))(*values)
status=1;checks=0
try:
    rng=random.Random(92851)
    for case in range(8):
        size=12;vertices=[];tri=[]
        scale=1.e-5 if case==4 else 1.
        shift=1.e6 if case==5 else 0.
        for layer in range(2 if case==2 else 1):
            start=len(vertices)//3
            for y in range(size):
                for x in range(size):
                    z=abs(x-5)*.5 if case==1 else math.sin(x*.3)*math.cos(y*.3)*.2
                    vertices.extend((shift+x*scale,shift+y*scale,shift+(z+layer*.05)*scale))
            for y in range(size-1):
                for x in range(size-1):
                    a=start+y*size+x;b=a+1;c=a+size;d=c+1
                    tri.extend((a,b,d,a,d,c))
        if case==3:tri.extend((0,0,1,0,1,1,2,2,2))
        if case==6:tri.extend(tri[:6])  # exact duplicate triangles / tied winners
        if case==7:tri=[j for i in range(0,len(tri),3) for j in (tri[i],tri[i+2],tri[i+1])]
        v=doubles(vertices);t=ints(tri)
        a=base.aru_surface_create(v,len(v)//3,t,len(t)//3)
        b=candidate.aru_surface_create(v,len(v)//3,t,len(t)//3)
        assert a and b
        try:
            count=512
            positions=[(rng.uniform(0,11),rng.uniform(0,11),rng.uniform(-.1,.3)) for _ in range(count)]
            offsets=ints([i*2 for i in range(count+1)])
            neighbors=ints([j for i in range(count) for j in ((i-1)%count,(i+1)%count)])
            seeds=[-1]*count
            for frame in range(80):
                count=127 if 32<=frame<48 else 512
                offsets=ints([i*2 for i in range(count+1)])
                neighbors=ints([j for i in range(count) for j in ((i-1)%count,(i+1)%count)])
                seeds=(seeds+[-1]*count)[:count]
                if frame%9==0:seeds=[rng.randrange(-3,len(t)//3+3) for _ in range(count)]
                if frame%13==0:positions[frame%count]=(rng.uniform(-1,12),rng.uniform(-1,12),rng.uniform(-2,2))
                motion=.00001 if frame%2 else .03
                positions=[(x+rng.uniform(-motion,motion),y+rng.uniform(-motion,motion),z) for x,y,z in positions]
                raw=[shift+value*scale for p in positions[:count] for value in p]
                weights=doubles([1. if i%11==0 else (.4 if frame%7==0 else 0.) for i in range(count)])
                steps=(frame//16)%5;strength=.35 if frame%8 else .7;guard=int((frame//20)%2)
                outputs=[]
                for lib,surface in ((base,a),(candidate,b)):
                    values=doubles(raw);ids=ints(seeds)
                    assert lib.aru_relax(surface,values,count,offsets,neighbors,weights,steps,strength,ids,guard)==1
                    outputs.append((list(values),list(ids)))
                assert outputs[0]==outputs[1],(case,frame,max(abs(x-y) for x,y in zip(outputs[0][0],outputs[1][0])))
                if frame%10==0:
                    fresh=candidate.aru_surface_create(v,len(v)//3,t,len(t)//3)
                    try:
                        values=doubles(raw);ids=ints(seeds)
                        assert candidate.aru_relax(fresh,values,count,offsets,neighbors,weights,steps,strength,ids,guard)==1
                        assert (list(values),list(ids))==outputs[0],('cold',case,frame)
                    finally:candidate.aru_surface_destroy(fresh)
                seeds=outputs[0][1];checks+=1
        finally:
            base.aru_surface_destroy(a);candidate.aru_surface_destroy(b)
    report={'passed':True,'candidate':candidate_name,'comparisons':checks,'point_counts':[127,512],'maya':cmds.about(version=True),'cold_comparisons':64,'exact_coordinates_and_seeds':True,'cases':['curved grid','fold','disconnected close layers','degenerate triangles','small scale','large translation','duplicate triangles','reversed winding'],'limits':'finite synthetic coordinates; not a complete correctness proof or interactive benchmark'}
    (root/'tests'/('projection_certificates_cases_'+candidate_name+'_'+cmds.about(version=True)+'.json')).write_text(json.dumps(report,indent=2))
    print('CERTIFICATES CASES PASSED',checks);status=0
except BaseException:traceback.print_exc()
finally:
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)

