"""Bounded standalone leak reproduction and balanced handle stress test."""
import os,sys,json,gc,ctypes,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.maya_data import plug_handle
class Memory(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
def private_bytes():
    info=Memory();info.cb=ctypes.sizeof(info)
    process=ctypes.windll.kernel32.GetCurrentProcess;process.restype=ctypes.c_void_p
    fn=ctypes.windll.psapi.GetProcessMemoryInfo;fn.argtypes=[ctypes.c_void_p,ctypes.POINTER(Memory),ctypes.c_ulong]
    assert fn(process(),ctypes.byref(info),ctypes.sizeof(info))
    return info.PrivateUsage
report={};status=0
try:
    mesh=cmds.polyPlane(sx=100,sy=100,w=10,h=10)[0]
    shape=cmds.listRelatives(mesh,shapes=True)[0]
    plug=om.MFnDependencyNode(om.MSelectionList().add(shape).getDependNode(0)).findPlug('worldMesh',False).elementByLogicalIndex(0)
    if '--scene' in sys.argv:
        from Aru_RetopoTool import guides,maya_api as api
        guides.load();api.load_plugin()
        cmds.file(str(ROOT/'tests/current_curve_latency_scene.mb'),open=True,force=True)
        node=cmds.ls(type='aruRetopoMesh')[0]
        plug=om.MFnDependencyNode(om.MSelectionList().add(node).getDependNode(0)).findPlug('referenceMesh',False)
    def balanced():
        with plug_handle(plug) as handle:
            fn=om.MFnMesh(handle.asMeshTransformed())
            return fn.numVertices,tuple(fn.getPoints()[0])
    expected=balanced()
    for _ in range(10):assert balanced()==expected
    gc.collect();start=private_bytes();t=time.perf_counter()
    for i in range(500):
        assert balanced()==expected
        if i%20==0:assert private_bytes()-start<256*1024**2,'Balanced handle memory runaway'
    gc.collect();report['balanced_500_bytes']=private_bytes()-start;report['balanced_500_ms']=(time.perf_counter()-t)*1000
    start=private_bytes()
    for i in range(16):
        handle=plug.asMDataHandle();fn=om.MFnMesh(handle.asMeshTransformed());assert fn.numVertices==expected[0]
        del fn,handle
        if private_bytes()-start>256*1024**2:break
    gc.collect();report['unbalanced_count']=i+1;report['unbalanced_bytes']=private_bytes()-start
    class Probe:
        def __init__(self):self.closed=0
        def asMDataHandle(self):return self
        def destructHandle(self,handle):assert handle is self;self.closed+=1
    probe=Probe()
    try:
        with plug_handle(probe):raise ValueError('expected')
    except ValueError:pass
    assert probe.closed==1
    assert report['balanced_500_bytes']<32*1024**2,report
    print('PASS balanced Maya handle lifetime, geometry and exception cleanup')
except BaseException:
    report['error']=traceback.format_exc();status=1
finally:
    (ROOT/('tests/data_handle_memory_scene.json' if '--scene' in sys.argv else 'tests/data_handle_memory.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));sys.stdout.flush();sys.stderr.flush();os._exit(status)
