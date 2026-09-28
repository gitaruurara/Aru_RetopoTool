import os,sys,traceback,math,json
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit,maya_projector as mp
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests import junction_directions_candidate as candidate
import numpy as np
from unittest.mock import patch
status=1;restore=None
try:
    folder=Path(__file__).resolve().parents[1]/'bin'/cmds.about(version=True)
    mp.clear();mp._LIB=mp._load_library(folder/'aru_retopo_maya_projector_tangents.dll')
    mesh=cmds.polySphere(ch=False)[0];fn,dag=edit._get_mesh_fn(mesh)
    rng=np.random.default_rng(1427);cases=[]
    for threshold in [-.30000000000001,-.3,-.29999999999999]:
        cases.append(([0,0,0],[0,0,1],[[1,0,0],[threshold,math.sqrt(1-threshold*threshold),0]],False))
    cases.extend([([0,0,0],n,[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[1e-10,0,0]],zero) for n in ([0,0,1],[0,0,0],[0,0,1e-14]) for zero in (False,True)])
    for count in range(1,9):
        for repeat in range(20):cases.append((rng.normal(size=3),rng.normal(size=3),rng.normal(size=(count,3)),bool(repeat%2)))
    maximum=0.;checks=0
    for p,n,branches,zero in cases:
        p=np.asarray(p,dtype=float);cn=RetopoGuideData();root=cn.add_cv(p.tolist())
        for index,vector in enumerate(branches):
            v=np.asarray(vector,dtype=float)
            h=cn.add_cv((p if zero else p+v*.3).tolist());j=cn.add_cv((p+v*.7).tolist());end=cn.add_cv((p+v).tolist())
            cn.add_spline(root,h,j,end)
            if index%3==0:cn.manual_handles.add(h)
        for manual in (False,True):
            for amount in (0.,.6,2.):
                outputs=[]
                def capture(cn,touched,directions,mesh_fn):outputs.append((set(touched),{key:value.copy() for key,value in directions.items()}))
                with patch.object(mp,'normals_array',return_value=np.ascontiguousarray([n],dtype=float)),patch.object(relax,'_fit_junction_lengths',side_effect=capture):
                    with patch.object(mp,'junction_directions',return_value=None):
                        relax._smooth_junctions(cn,{root:.7},fn,dag,amount,manual)
                    expected=outputs[-1] if outputs else (set(),{})
                    outputs.clear()
                    relax._smooth_junctions(cn,{root:.7},fn,dag,amount,manual)
                    actual=outputs[-1] if outputs else (set(),{})
                assert expected[0]==actual[0] and expected[1].keys()==actual[1].keys(),('Pairing changed',p,n,branches,amount,manual)
                for key in expected[1]:
                    error=float(np.max(np.abs(expected[1][key]-actual[1][key])));maximum=max(maximum,error)
                    assert error<1e-12,('Direction changed',error)
                checks+=1
    args=[[[0.,0.,0.]],[[0.,0.,1.]],[1.],.6,[0,2],[[1.,0.,0.,.3,0.,0.],[-1.,0.,0.,-.3,0.,0.]]]
    saved=mp.junction_directions(fn,*args);copies=tuple(a.copy() for a in saved)
    mp.junction_directions(fn,*args)
    for a,b in zip(saved,copies):np.testing.assert_array_equal(a,b)
    assert not len(mp.junction_directions(fn,[],[],[],.6,[0],[])[0])
    for bad_offsets in ([0,3],[0,-1],[1,2]):
        bad=list(args);bad[4]=bad_offsets
        try:mp.junction_directions(fn,*bad)
        except RuntimeError:pass
        else:raise AssertionError('Invalid offsets accepted')
    bad=list(args);bad[1]=[]
    try:mp.junction_directions(fn,*bad)
    except ValueError:pass
    else:raise AssertionError('Invalid normal count accepted')
    for value in (float('nan'),1e308):
        bad=list(args);bad[5]=[list(row) for row in args[5]];bad[5][0][0]=value
        try:mp.junction_directions(fn,*bad)
        except RuntimeError:pass
        else:raise AssertionError('Invalid or overflowing vector accepted')
    mp.clear();mp._LIB=mp._load_library(folder/'aru_retopo_maya_projector_bound.dll')
    assert mp.junction_directions(fn,*args) is None
    print('JUNCTION DIRECTIONS CASES PASSED',checks,'maximum_error',maximum)
    (Path(__file__).parent/('junction_directions_cases_'+cmds.about(version=True)+'.json')).write_text(json.dumps(dict(checks=checks,max_error=maximum)))
    status=0
except BaseException:traceback.print_exc()
finally:
    if restore:restore()
    mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
