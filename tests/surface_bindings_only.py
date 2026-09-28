import os,sys,json,time,statistics,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from unittest.mock import patch
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_edit as edit
from Aru_RetopoTool.tests import surface_bindings_candidate as candidate
status=1
try:
    rng=np.random.default_rng(218);queries=rng.normal(size=(4096,3));records=[]
    for kind in ('sphere','cube'):
        mesh=(cmds.polySphere(sx=32,sy=24,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
        cmds.setAttr(mesh+'.scale',-1.3,.8,1.7,type='double3');cmds.setAttr(mesh+'.rotate',12,33,-7,type='double3')
        fn,_=edit._get_mesh_fn(mesh)
        for count in (0,1,644,4096):
            values=queries[:count];expected=[(face,bary) for _q,_n,face,bary in mp.surface_hits(fn,values)]
            result=candidate.surface_bindings(fn,values);assert result==expected
            timings={}
            for name,call in [('old',lambda:[(f,b) for _q,_n,f,b in mp.surface_hits(fn,values)]),('bindings',lambda:candidate.surface_bindings(fn,values))]:
                times=[]
                for _ in range(12):
                    start=time.perf_counter();call();times.append((time.perf_counter()-start)*1000)
                timings[name]=statistics.median(times[2:])
            records.append(dict(mesh=kind,count=count,timings=timings))
        with patch.object(mp,'get_projector',return_value=None), patch.object(candidate,'get_projector',return_value=None):
            expected=[(f,b) for _q,_n,f,b in mp.surface_hits(fn,queries[:16])]
            assert candidate.surface_bindings(fn,queries[:16])==expected
        result[0][1].clear();assert candidate.surface_bindings(fn,queries)==[(f,b) for _q,_n,f,b in mp.surface_hits(fn,queries)]
        mp.clear();cmds.delete(mesh)
    (Path(__file__).parent/('surface_bindings_only_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
    print('PASS exact bindings, transformed sphere/cube, fallback, empty, ownership',records);status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
