import os,sys,json,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_edit as edit
from Aru_RetopoTool.tests.endpoint_candidate import endpoint_hits
status=1;records=[]
def reference(fn,old,weights,neighbors,strength,smooth):
 hits=dict(zip(weights,mp.surface_hits(fn,[old[ep] for ep in weights])))
 moving=[ep for ep in weights if smooth and len(neighbors[ep])>=2]
 normals=dict(zip(moving,mp.normals_array(fn,[hits[ep][0] for ep in moving]).tolist()))
 targets=[]
 for ep in moving:
  p=old[ep];projected=hits[ep][0];adjacent=neighbors[ep];n=normals[ep]
  center=[sum(old[v][k] for v in adjacent)/len(adjacent) for k in range(3)]
  delta=[center[k]-p[k] for k in range(3)]
  normal_length=sum(x*x for x in n)
  dn=sum(delta[k]*n[k] for k in range(3))/max(normal_length,1e-12)
  targets.append([projected[k]+strength*weights[ep]*(delta[k]-dn*n[k]) for k in range(3)])
 hits.update(zip(moving,mp.surface_hits(fn,targets)))
 return hits
try:
 root=Path(__file__).resolve().parents[1];mp._LIB=mp._load_library(root/'bin'/cmds.about(version=True)/'aru_retopo_maya_endpoint_candidate.dll')
 rng=np.random.default_rng(137)
 for kind in ('sphere','cube'):
  mesh=(cmds.polySphere(sx=32,sy=16,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
  for transformed in (False,True):
   if transformed:
    cmds.setAttr(mesh+'.translate',1.2,-.4,.8);cmds.setAttr(mesh+'.scale',-1.3,.7,1.8);cmds.setAttr(mesh+'.rotate',17,-23,8)
   edit._invalidate_mesh_accel();mp.clear();fn,_=edit._get_mesh_fn(mesh)
   old=rng.normal(size=(600,3)).tolist()
   for count in (0,1,63,64,500):
    weights={ep:float(rng.uniform(.01,1)) for ep in range(count)}
    neighbors={ep:[(ep+j+1)%600 for j in range(ep%6)] for ep in range(count)}
    for smooth in (False,True):
     expected=reference(fn,old,weights,neighbors,.35,smooth)
     actual=endpoint_hits(fn,old,weights,neighbors,.35,smooth)
     assert actual==expected,(kind,transformed,count,smooth)
     records.append(dict(kind=kind,transformed=transformed,count=count,smooth=smooth,exact=True))
  mp.clear();cmds.delete(mesh)
 (root/'tests'/('endpoint_cases_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
 print('ENDPOINT CASES EXACT',len(records),flush=True);status=0
except BaseException:traceback.print_exc()
finally:
 mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
