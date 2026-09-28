import os,sys,json,time,statistics,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_edit as edit
from Aru_RetopoTool.tests.routes_bound_candidate import fit_bound
import numpy as np
status=1
try:
    rng=np.random.default_rng(3184);records=[]
    folder=Path(__file__).resolve().parents[1]/'bin'/cmds.about(version=True)
    old=mp._load_library(folder/'aru_retopo_maya_projector_compact.dll')
    new=mp._load_library(folder/'aru_retopo_maya_projector_basis.dll')
    for kind,count,transformed in [('sphere',0,False),('sphere',1,False),('sphere',15,False),('sphere',16,False),('sphere',500,False),('sphere',500,True),('cube',500,True)]:
        mesh=(cmds.polySphere(sx=64,sy=32,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
        if transformed:
            cmds.setAttr(mesh+'.scale',-1.3,.8,1.7,type='double3');cmds.setAttr(mesh+'.rotate',13,23,-7,type='double3')
        fn,_=edit._get_mesh_fn(mesh)
        a=rng.normal(size=(count,3));a/=np.maximum(np.linalg.norm(a,axis=1)[:,None],1e-12)
        b=a+rng.normal(size=(count,3))*.15;b/=np.maximum(np.linalg.norm(b,axis=1)[:,None],1e-12)
        controls=np.stack((a,a+(b-a)/3,b-(b-a)/3,b),axis=1)
        for draft in (True,False):
            results=[];times={}
            for mode,lib in [('separate',old),('bound',new)]:
                mp.clear();mp._LIB=lib;durations=[]
                for repeat in range(6):
                    start=time.perf_counter()
                    result=fit_bound(fn,controls,draft)
                    durations.append((time.perf_counter()-start)*1000)
                results.append(result);times[mode]=statistics.median(durations[1:])
            assert results[0]==results[1],(kind,count,transformed,draft)
            records.append(dict(mesh=kind,count=count,transformed=transformed,draft=draft,times=times,exact=True))
        if count==1:
            mp.clear();mp._LIB=new
            saved=fit_bound(fn,controls)
            expected=json.dumps(saved)
            fit_bound(fn,controls+.001)
            assert json.dumps(saved)==expected,'Returned result was aliased'
            bad=controls.copy();bad[0,0,0]=float('nan')
            try:fit_bound(fn,bad)
            except RuntimeError:pass
            else:raise AssertionError('Nonfinite input accepted')
            degenerate=controls.copy();degenerate[:,3]=degenerate[:,0]
            actual=fit_bound(fn,degenerate)
            fitted=mp.fit_routes(fn,degenerate)
            expected_bindings=[(face,bary) for pos,normal,face,bary in mp.surface_hits(fn,[p for pair in fitted for p in pair])]
            assert actual==(fitted,expected_bindings)
        # Refactoring shared surface-hit code must also preserve all old fields.
        mp.clear();mp._LIB=old;old_hits=mp.surface_hits(fn,a.tolist())
        mp.clear();mp._LIB=new;assert mp.surface_hits(fn,a.tolist())==old_hits
        mp.clear();cmds.delete(mesh)
    (Path(__file__).parent/('basis_cases_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
    print(json.dumps(records));status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
