"""Disposable mayapy: native graph, paint, reduction and scene persistence."""
import os,sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides,maya_api as api,core,density,local_fields,native_backend
from Aru_RetopoTool.tests.mesh_assertions import mesh_fn
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    cmds.file(new=True,force=True)
    mesh=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
    p,s=polygon(4)
    # Uneven bowed guides make the influence changes visibly measurable.
    p=list(p);p[4]=tuple(x*1.8 for x in p[4])
    cn=RetopoGuideData.from_dict(dict(positions=p,splines=s))
    guide=guides.create(mesh);edit.RetopoGuideAccessor(guide).write(cn)
    output,node=api.create(guide,mesh,subdivisions=3)
    plan=core.Plan(p,s,lambda p:(0,1,0),3)
    cmds.setAttr(node+'.selectedPatches',json.dumps(plan.region_keys),type='string')
    cmds.setAttr(node+'.relaxIterations',10)
    fn=mesh_fn(output);before=[tuple(p) for p in fn.getPoints()]
    field={plan.region_keys[0]:{str(i):(0.,1.) for i in range(17*17)}}
    raw=json.dumps(field);cmds.setAttr(node+'.influenceField',raw,type='string')
    after=[tuple(p) for p in mesh_fn(output).getPoints()]
    assert max(abs(a-b) for p,q in zip(before,after) for a,b in zip(p,q))>1e-4
    assert len(before)==len(after)
    cmds.undo();assert [tuple(p) for p in mesh_fn(output).getPoints()]==before
    cmds.redo();assert cmds.getAttr(node+'.influenceField')==raw
    uv=next(iter(plan.edit_coordinates().values()));topology=density.Topology(plan.faces)
    seed=next(e for e in topology.owners if all(abs(uv[v][0]-.5)<1e-8 for v in e))
    requests=json.dumps([density.describe(plan,seed)])
    cmds.setAttr(node+'.loopReductions',requests,type='string')
    fn=mesh_fn(output);assert fn.numPolygons==56 and fn.numVertices==72
    assert all(abs(p.y)<1e-6 for p in fn.getPoints())
    # Public generator and required native graph must agree on local edits.
    legacy=om.MFnMesh(om.MSelectionList().add(node+'.outMesh').getPlug(0).asMObject())
    assert legacy.numPolygons==fn.numPolygons and legacy.numVertices==fn.numVertices
    assert max(abs(a-b) for p,q in zip(fn.getPoints(),legacy.getPoints()) for a,b in zip(p,q))<1e-8
    cmds.undo();assert mesh_fn(output).numPolygons==64
    cmds.redo();assert mesh_fn(output).numPolygons==56
    cn.positions[0][0]+=.15;edit.RetopoGuideAccessor(guide).write(cn)
    assert mesh_fn(output).numPolygons==56
    assert cmds.getAttr(node+'.influenceField')==raw and cmds.getAttr(node+'.loopReductions')==requests
    with tempfile.TemporaryDirectory(prefix='retopo_fields_') as folder:
        from Aru_RetopoTool.local_edit_runtime import PreviewValue
        transient=PreviewValue(node,'influenceField');transient.write({})
        path=os.path.join(folder,'local.ma');cmds.file(rename=path);cmds.file(save=True,type='mayaAscii',force=True)
        assert transient.closed and cmds.getAttr(node+'.influenceField')==raw
        cmds.file(new=True,force=True);cmds.file(path,open=True,force=True)
        assert mesh_fn(output).numPolygons==56
        assert cmds.getAttr(node+'.influenceField')==raw and cmds.getAttr(node+'.loopReductions')==requests
    assert not native_backend.status(node).startswith('ERROR:')
    print('PASS native influence changes geometry; loop removal; parity; Undo/Redo; guide movement; save/reopen')
    transfer_checks()

def transfer_checks():
    from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_symmetry as sym
    from Aru_RetopoTool import patch_context
    from Aru_RetopoTool.tests.test_core import network
    cmds.file(new=True,force=True);sym.set_axis('')
    mesh=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
    points,splines=network([(-2,0,-2),(2,0,-2),(2,0,2),(-2,0,2),(4,0,-2),(4,0,2)],[(0,1),(1,2),(2,3),(3,0),(1,4),(4,5),(5,2)])
    guide=guides.create(mesh);acc=edit.RetopoGuideAccessor(guide)
    acc.write(RetopoGuideData.from_dict(dict(positions=points,splines=splines)))
    output,node=api.create(guide,mesh,subdivisions=3)
    plan=core.Plan(points,splines,lambda p:(0,1,0),3)
    key=next(core.patch_key(loop) for loop in plan.region_loops if any(si==3 for side in loop for si,_ in side))
    patch_context.confirm(node,key)
    field={key:{str(i):(.7,1.) for i in range(289)}}
    raw=json.dumps(field);cmds.setAttr(node+'.influenceField',raw,type='string')
    original=cmds.getAttr(guide+'.netData')
    with api.undo_chunk('split painted patch'):
        cn=acc.read();a=context._split_spline_at(cn,0,.5,mesh);b=context._split_spline_at(cn,2,.5,mesh)
        context._add_spline_to_cn(cn,mesh,a,b);edit._commit_net_data(guide,cn)
    selected=patch_context.selected(node);fields=json.loads(cmds.getAttr(node+'.influenceField'))
    assert len(selected)==2 and set(fields)==selected,(selected,fields.keys())
    for field in fields.values():
        value,alpha=local_fields.sample(field,.5,.5)
        assert abs(value-.7)<1e-6 and abs(alpha-1.)<1e-6,(value,alpha)
    cmds.undo();assert cmds.getAttr(guide+'.netData')==original and cmds.getAttr(node+'.influenceField')==raw
    cmds.redo();assert set(json.loads(cmds.getAttr(node+'.influenceField')))==selected
    print('PASS painted patch splits into painted children; unfilled neighbor untouched; atomic Undo/Redo')
    cmds.file(new=True,force=True)
    mesh=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
    points,splines=network([(0,0,-1),(2,0,-1),(2,0,1),(0,0,1)],[(0,1),(1,2),(2,3),(3,0)])
    guide=guides.create(mesh);acc=edit.RetopoGuideAccessor(guide)
    acc.write(RetopoGuideData.from_dict(dict(positions=points,splines=splines)))
    output,node=api.create(guide,mesh,subdivisions=3)
    plan=core.Plan(points,splines,lambda p:(0,1,0),3);key=plan.region_keys[0]
    patch_context.confirm(node,key)
    field={key:{str(i):(.65,1.) for i in range(289)}}
    raw=json.dumps(field);cmds.setAttr(node+'.influenceField',raw,type='string')
    uv=plan.edit_coordinates()[key];topology=density.Topology(plan.faces)
    seed=next(e for e in topology.owners if all(abs(uv[v][0]-.5)<1e-8 for v in e))
    requests=json.dumps([density.describe(plan,seed,key)])
    cmds.setAttr(node+'.loopReductions',requests,type='string')
    original=cmds.getAttr(guide+'.netData')
    edit.mirror_curvenet(guide,axis='x',space='world',direction='positive',mode='add',quiet=True)
    fields=json.loads(cmds.getAttr(node+'.influenceField'))
    assert set(fields)==patch_context.selected(node) and len(fields)==2,fields.keys()
    for field in fields.values():
        value,alpha=local_fields.sample(field,.5,.5)
        assert abs(value-.65)<1e-6 and abs(alpha-1.)<1e-6,(value,alpha)
    assert mesh_fn(output).numPolygons==112,mesh_fn(output).numPolygons
    cmds.undo();assert cmds.getAttr(guide+'.netData')==original
    assert cmds.getAttr(node+'.influenceField')==raw and cmds.getAttr(node+'.loopReductions')==requests
    cmds.redo();assert mesh_fn(output).numPolygons==112
    print('PASS explicit mirror copies paint and reductions with symmetry disabled; atomic Undo/Redo')
    saved_fields=cmds.getAttr(node+'.influenceField');saved_requests=cmds.getAttr(node+'.loopReductions')
    with api.undo_chunk('delete painted source edge'):
        cn=acc.read();cn.splines.pop(0);edit._commit_net_data(guide,cn)
    assert len(patch_context.selected(node))==1
    assert set(json.loads(cmds.getAttr(node+'.influenceField')))==patch_context.selected(node)
    assert mesh_fn(output).numPolygons==56,mesh_fn(output).numPolygons
    cmds.undo()
    assert cmds.getAttr(node+'.influenceField')==saved_fields and cmds.getAttr(node+'.loopReductions')==saved_requests
    assert mesh_fn(output).numPolygons==112
    print('PASS deleted patch drops local edits; surviving renumbered patch retains paint/reduction; Undo')



if __name__=='__main__':
    result=0
    try:run()
    except Exception:
        import traceback;traceback.print_exc();result=1
    finally:cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(result)
