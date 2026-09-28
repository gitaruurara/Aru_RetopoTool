import os,sys,traceback,json,time,statistics
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_edit as edit
status=1
try:
    root=Path(__file__).resolve().parents[1]
    libs=[mp._load_library(root/'bin'/cmds.about(version=True)/('aru_retopo_maya_projector_'+name+'.dll')) for name in ('v7','normals')]
    rng=np.random.default_rng(7281);queries=rng.normal(size=(4096,3))*1.3
    records=[]
    for kind in ('sphere','cube'):
        mesh=(cmds.polySphere(sx=64,sy=32,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
        for transformed in (False,True):
            if transformed:
                cmds.setAttr(mesh+'.scale',-1.7,.6,1.2,type='double3')
                cmds.setAttr(mesh+'.rotate',17,23,-11,type='double3')
                cmds.setAttr(mesh+'.translate',.2,.1,-.3,type='double3')
            fn,_=edit._get_mesh_fn(mesh)
            results=[];times=[]
            for lib in libs:
                mp.clear();mp._LIB=lib
                outputs=[];timings={}
                for count in (0,1,324,1090,4096):
                    values=queries[:count];durations=[]
                    expected=mp.normals_array(fn,values)
                    for _ in range(15):
                        start=time.perf_counter();actual=mp.normals_array(fn,values);durations.append((time.perf_counter()-start)*1000)
                        np.testing.assert_array_equal(expected,actual)
                    outputs.append(expected);timings[count]=statistics.median(durations)
                    if count:actual[:]=0;np.testing.assert_array_equal(mp.normals_array(fn,values),expected)
                results.append(outputs);times.append(timings)
            for a,b in zip(*results):np.testing.assert_array_equal(a,b)
            try:mp.normals_array(fn,[[float('nan'),0,0]])
            except RuntimeError:pass
            else:raise AssertionError('nonfinite normal query accepted')
            records.append(dict(mesh=kind,transformed=transformed,before=times[0],after=times[1]))
        mp.clear();cmds.delete(mesh)
    (root/'tests'/('native_normals_'+cmds.about(version=True)+'.json')).write_text(json.dumps(dict(exact=True,records=records),indent=2))
    print('PASS native normal exact parity, fallback v7, transforms, ownership, sizes, nonfinite queries')
    for record in records:print(record)
    status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
