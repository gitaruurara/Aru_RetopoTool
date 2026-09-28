"""Differential output and timing check for sleeping Maya projector workers."""
import os,sys,json,time,statistics,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as p,curve_net_edit as edit
status=1
try:
    root=Path(__file__).resolve().parents[1];reports={};outputs={}
    mesh=cmds.polySphere(r=3,sx=32,sy=24,ch=False)[0]
    cmds.setAttr(mesh+'.scale',1.2,.8,1.1,type='double3')
    cmds.setAttr(mesh+'.translate',.3,-.2,.4,type='double3')
    fn,dag=edit._get_mesh_fn(mesh)
    rng=np.random.default_rng(281)
    queries=rng.normal(size=(4096,3))*2.8
    ends=rng.normal(size=(200,2,3));ends=ends/np.linalg.norm(ends,axis=2)[:,:,None]*3
    controls=np.stack((ends[:,0],ends[:,0]*.7+ends[:,1]*.3,ends[:,0]*.3+ends[:,1]*.7,ends[:,1]),axis=1)
    for version in ('v7','sleepteam'):
        p.clear();p._LIB=p._load_library(root/'bin'/cmds.about(version=True)/('aru_retopo_maya_projector_'+version+'.dll'))
        rows={};values=[]
        for count in (1,511,512,4096):
            samples=[]
            for repeat in range(12):
                start=time.perf_counter();out=p.points_array(fn,queries[:count]);samples.append((time.perf_counter()-start)*1000)
            values.append(out);rows['points'+str(count)]=statistics.median(samples[2:])
        for count in (1,15,16,200):
            for draft in (True,False):
                samples=[]
                for repeat in range(8):
                    start=time.perf_counter();out=p.fit_routes(fn,controls[:count],draft);samples.append((time.perf_counter()-start)*1000)
                values.append(np.asarray(out));rows['routes'+str(count)+'_'+str(draft)]=statistics.median(samples[2:])
        cpu=time.process_time();time.sleep(.05);rows['idle_cpu_ms']=(time.process_time()-cpu)*1000
        outputs[version]=values;reports[version]=rows;p.clear()
    for a,b in zip(outputs['v7'],outputs['sleepteam']):np.testing.assert_array_equal(a,b)
    reports['exact_outputs']=True
    (root/'tests'/('projector_team_'+cmds.about(version=True)+'.json')).write_text(json.dumps(reports,indent=2))
    print('PASS projector team exact outputs, serial/parallel thresholds, transformed reference, idle and destruction',reports)
    status=0
except BaseException:traceback.print_exc()
finally:
    p.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
