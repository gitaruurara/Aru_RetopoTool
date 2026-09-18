import os,sys,json,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.maya_projector import endpoint_hits
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
 root=Path(__file__).resolve().parents[1];mp._LIB=mp._load_library(root/'bin'/cmds.about(version=True)/mp.BINARY_NAME)
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
 # Owned results, current reference geometry, absent accelerator and old DLL.
 from unittest.mock import patch
 mesh=cmds.polySphere(sx=24,sy=16,ch=False)[0]
 fn,_=edit._get_mesh_fn(mesh)
 old=[[.1,.9,.2],[.3,.8,.1],[.4,.7,.2]];weights={0:.5};neighbors={0:[1,2]}
 retained=endpoint_hits(fn,old,weights,neighbors,.35,True);snapshot=json.dumps(retained)
 for change in ('transform','deform'):
  if change=='transform':cmds.move(.15,.1,0,mesh,relative=True)
  else:cmds.move(.1,.2,.05,mesh+'.vtx[0:8]',relative=True)
  fn,_=edit._get_mesh_fn(mesh)
  actual=endpoint_hits(fn,old,weights,neighbors,.35,True)
  mp.clear();edit._invalidate_mesh_accel();fn,_=edit._get_mesh_fn(mesh)
  assert actual==reference(fn,old,weights,neighbors,.35,True),change
 assert json.dumps(retained)==snapshot
 for bad in (float('nan'),float('inf')):
  try:endpoint_hits(fn,old,{0:bad},neighbors,.35,True)
  except RuntimeError:pass
  else:raise AssertionError('Nonfinite weight accepted')
  damaged=[list(p) for p in old];damaged[1][0]=bad
  try:endpoint_hits(fn,damaged,weights,neighbors,.35,True)
  except RuntimeError:pass
  else:raise AssertionError('Nonfinite point accepted')
 for bad in (-1,len(old)):
  try:endpoint_hits(fn,old,weights,{0:[bad,2]},.35,True)
  except ValueError:pass
  else:raise AssertionError('Invalid neighbor accepted')
 with patch.object(edit,'_accel_for',return_value=None):
  try:endpoint_hits(fn,old,weights,neighbors,.35,True)
  except RuntimeError as exc:assert 'reference mesh' in str(exc)
  else:raise AssertionError('Missing reference accepted')
 from types import SimpleNamespace
 with patch.object(mp.C,'CDLL',return_value=SimpleNamespace()):
  try:mp._load_library('incompatible.dll')
  except RuntimeError as exc:assert 'ABI mismatch' in str(exc)
  else:raise AssertionError('Incompatible DLL accepted')
 with patch.object(mp.C,'CDLL',side_effect=OSError('missing')):
  try:mp._load_library('missing.dll')
  except RuntimeError as exc:assert 'could not be loaded' in str(exc)
  else:raise AssertionError('Missing DLL accepted')
 assert endpoint_hits(fn,old,{},neighbors,.35,True)=={}
 cmds.loadPlugin(str(root/'editor/curvenet/aru_retopo_guide_plugin.py'),quiet=True)
 cmds.undoInfo(state=True)
 from Aru_RetopoTool.tests import surface_relax
 with patch.object(mp,'endpoint_hits',wraps=mp.endpoint_hits) as observed:
  surface_relax.run()
  assert observed.call_count>0
 print('PASS actual relax with required native DLL, projection, topology, Undo and Shift handling',flush=True)
 print('PASS retained arrays, reference transforms/deformation, invalid values, missing projector, explicit DLL failures',flush=True)
 (root/'tests'/('endpoint_release_cases_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
 print('ENDPOINT CASES EXACT',len(records),flush=True);status=0
except BaseException:traceback.print_exc()
finally:
 mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
