import os,sys,traceback,math,json,time,statistics,copy
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit,maya_projector
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
status=1
try:
    root=Path(__file__).resolve().parent
    scope=dict(relax.__dict__)
    exec((root/'relax_routes_before_arrays.py.txt').read_text(encoding='utf-8'),scope)
    old=scope['_fit_relax_routes']
    exec((root/'relax_routes_array_candidate.py.txt').read_text(encoding='utf-8'),scope)
    candidate=scope['_fit_relax_routes']
    projector_scope=dict(maya_projector.__dict__)
    exec((root/'projector_routes_array_candidate.py.txt').read_text(encoding='utf-8'),projector_scope)
    maya_projector.fit_routes=projector_scope['fit_routes']
    mesh=cmds.polySphere(sx=64,sy=32,ch=False)[0]
    fn,dag=edit._get_mesh_fn(mesh)
    positions=[];splines=[]
    for i in range(400):
        angle=i*.037
        p=[math.cos(angle),.2,math.sin(angle)]
        q=[math.cos(angle+.15),.3,math.sin(angle+.15)]
        base=len(positions)
        positions.extend([p,[(2*a+b)/3 for a,b in zip(p,q)],[(a+2*b)/3 for a,b in zip(p,q)],q])
        splines.append(list(range(base,base+4)))
    data={'positions':positions,'splines':splines}
    times=[[],[]]
    for repeat in range(7):
        results=[]
        for index in (0,1):
            cn=RetopoGuideData.from_dict(copy.deepcopy(data))
            start=time.perf_counter()
            assert (old,candidate)[index](cn,list(range(400)),fn,dag,True)
            times[index].append((time.perf_counter()-start)*1000)
            results.append((cn.positions,cn.surface_binding,cn.manual_handles))
        assert results[0]==results[1]
    for data in ({'positions':[[0,0,0]]*4,'splines':[[0,1,2,3]]},{'positions':[],'splines':[]}):
        cn=RetopoGuideData.from_dict(data)
        assert candidate(cn,list(range(len(cn.splines))),fn,dag,True)
    result=dict(before_ms=statistics.median(times[0][1:]),after_ms=statistics.median(times[1][1:]),exact=True,curves=400)
    (root/('route_array_transfer_'+cmds.about(version=True)+'.json')).write_text(json.dumps(result,indent=2))
    print(result)
    status=0
except BaseException:traceback.print_exc()
finally:
    maya_projector.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
