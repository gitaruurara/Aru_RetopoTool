"""Numerical equivalence and topology-cache invalidation regressions (mayapy)."""
import os,sys,math,json,random,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from Aru_RetopoTool.tests.curve_edit_features import fixture

def run():
    from Aru_RetopoTool.tests.region_input_cache import run as region_input_cache
    region_input_cache()
    from Aru_RetopoTool.tests.sparse_field_coordinates import run as sparse_coordinates
    sparse_coordinates()
    from Aru_RetopoTool.tests.patch_key_cache import run as patch_key_cache
    patch_key_cache()
    from Aru_RetopoTool.tests.ordinary_guide_draw import run as ordinary_draw
    ordinary_draw()
    from Aru_RetopoTool.tests.refresh_reentry import run as refresh_test
    refresh_test()
    from Aru_RetopoTool.tests.control_point_snapshot import run as snapshot_test
    snapshot_test()
    from maya import cmds
    import maya.api.OpenMaya as om
    from Aru_RetopoTool import core,local_fields,patch_transfer,maya_api as api
    from Aru_RetopoTool.editor.curvenet import curve_net_context as c,curve_net_edit as e,symmetry_constraints as sc,curve_net_symmetry as sym
    from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
    from Aru_RetopoTool.tests.test_core import polygon
    from collections import defaultdict
    from Aru_RetopoTool import curve_loop
    import numpy as np
    old=dict(c.__dict__)
    exec((ROOT/'tests/curve_crossings_before_latency.py.txt').read_text(encoding='utf-8'),old)
    rng=random.Random(751)
    cn=RetopoGuideData()
    for i in range(20):
        controls=[cn.add_cv((rng.uniform(-3,3),0.,rng.uniform(-3,3))) for _ in range(4)]
        cn.splines.append(tuple(controls))
    for a in range(20):
        for b in range(a):
            expected=old['_find_curve_crossings'](cn,a,b,.02)
            actual=c._find_curve_crossings(cn,a,b,.02)
            assert len(expected)==len(actual),(a,b,expected,actual)
            for x,y in zip(expected,actual):assert np.allclose([x[0],x[1],*x[2]],[y[0],y[1],*y[2]],atol=1e-10,rtol=1e-10)
    exec((ROOT/'tests/nearest_curve_before_latency.py.txt').read_text(encoding='utf-8'),old)
    for _ in range(50):
        point=[rng.uniform(-3,3),0.,rng.uniform(-3,3)]
        expected=old['_nearest_spline_t_excluding'](cn,point,.2)
        actual=c._nearest_spline_t_excluding(cn,point,.2)
        assert expected==actual,(expected,actual)
    reference=types.ModuleType('Aru_RetopoTool.latency_reference')
    reference.__package__='Aru_RetopoTool'
    exec((ROOT/'tests/patch_transfer_before_latency.py.txt').read_text(encoding='utf-8'),reference.__dict__)
    p,s=polygon(4);before=RetopoGuideData.from_dict(dict(positions=p,splines=s))
    keys={core.patch_key(loop) for loop in core.regions(p,s,lambda p:(0,1,0))}
    after=RetopoGuideData.from_dict(before.to_dict())
    a,_,_=after.split_spline(0,.3);b,_,_=after.split_spline(2,.7)
    after.add_spline_two_endpoints(a,b)
    assert reference.transfer(before,after,keys,lambda p:(0,1,0))==patch_transfer.transfer(before,after,keys,lambda p:(0,1,0))
    old_uv=dict(math=math,defaultdict=defaultdict)
    exec((ROOT/'tests/local_coordinates_before_latency.py.txt').read_text(encoding='utf-8'),old_uv)
    for n in (3,4,5,7):
        p,s=polygon(n)
        for level in (1,2,3,4):
            plan=core.Plan(p,s,lambda p:(0,1,0),level)
            assert old_uv['coordinates'](plan)==local_fields.coordinates(plan)
    from Aru_RetopoTool.local_edit_transfer import Atlas
    class IdentitySurface:
        def project(self,points,guard=False):return points,None,None
    for n in (3,4,5):
        p,s=polygon(n); net=RetopoGuideData.from_dict(dict(positions=p,splines=s))
        loop=core.regions(p,s,lambda p:(0,1,0))[0]; key=core.patch_key(loop)
        reference_atlas=Atlas(net,key,lambda p:(0,1,0),IdentitySurface())
        atlas=Atlas(net,key,lambda p:(0,1,0),IdentitySurface(),loop)
        assert atlas.plan.faces==reference_atlas.plan.faces
        assert np.allclose(atlas.points,reference_atlas.points,atol=1e-12,rtol=1e-12)
        points=[(rng.uniform(-2,2),rng.uniform(-.5,.5),rng.uniform(-2,2)) for _ in range(120)]
        points.extend(tuple(p) for p in atlas.points)
        expected=[atlas.closest(p) for p in points]
        uv,distances=atlas.closest_many(points)
        assert np.allclose(uv,[r[0] for r in expected],atol=1e-10,rtol=1e-10),n
        assert np.allclose(distances,[r[1] for r in expected],atol=1e-12,rtol=1e-12),n
        assert atlas.closest_many([])==([],[])
    print('PASS reused region atlases and batched UV projection on triangles, quads and pentagons')
    from Aru_RetopoTool import transfer_native
    from types import SimpleNamespace
    old_net=SimpleNamespace(positions=[list(p) for p in cn.positions],splines=list(cn.splines))
    new_net=SimpleNamespace(positions=[list(p) for p in cn.positions],splines=list(cn.splines))
    new_net.splines.extend(tuple(reversed(sp)) for sp in cn.splines)
    for index in range(0,len(new_net.positions),7):new_net.positions[index][0]+=.49e-6
    assert transfer_native.matches(old_net,new_net)==patch_transfer._python_endpoint_matches(old_net,new_net)
    invalid=SimpleNamespace(positions=[[0.,0.]],splines=[(0,0,0,0)])
    try:transfer_native.matches(invalid,invalid)
    except ValueError:pass
    else:raise AssertionError('Invalid dimensions accepted')
    print('PASS native correspondence, reversed duplicates, tolerance, invalid dimensions')
    print('PASS crossing and parameter-coordinate equivalence')
    from Aru_RetopoTool.tests.curve_edit_features import fixture
    mesh,guide,node,_,_=fixture()
    def evaluated():
        obj=om.MSelectionList().add(api.output_plug(node)).getPlug(0).asMObject()
        return om.MFnMesh(obj).numVertices
    evaluated()
    plan_node=cmds.ls(type='aruRetopoPlan')[0]
    provider=om.MFnDependencyNode(om.MSelectionList().add(plan_node).getDependNode(0)).userNode()
    before=provider.plan;acc=e.RetopoGuideAccessor(guide)
    with api.undo_chunk('unselected branch'):
        cn=acc.read();ep=cn.add_cv((-3,0,-3));c._add_spline_to_cn(cn,mesh,0,ep);e._commit_net_data(guide,cn)
    evaluated();assert provider.plan is before,'Unchanged filled region rebuilt'
    cmds.undo();evaluated();assert provider.plan is before
    with api.undo_chunk('selected split'):
        cn=acc.read();a=c._split_spline_at(cn,0,.5,mesh);b=c._split_spline_at(cn,2,.5,mesh);c._add_spline_to_cn(cn,mesh,a,b);e._commit_net_data(guide,cn)
    evaluated();assert provider.plan is not before and provider.plan.region_count==2
    cmds.undo();evaluated();assert provider.plan.region_count==1
    surface=provider._surface
    cmds.move(0,.15,0,mesh+'.vtx[0]',relative=True)
    evaluated();assert provider._surface is not surface,'Reference accelerator not invalidated'
    for space in ('object','world'):
        for axis in ('x','y','z',''):
            cn=acc.read()
            expected=set()
            if axis:
                for a,h,j,b in cn.splines:
                    if all(sym.on_symmetry_plane(cn.positions[v],mesh,1e-6,axis,space) for v in (a,b)):expected.update((h,j))
            values={v:sym.project_to_plane(cn.positions[v],mesh,axis,space) for v in expected}
            assert sc.constrain(cn,mesh,axis=axis,space=space)==expected
            for v,p in values.items():assert cn.positions[v]==p
    from Aru_RetopoTool import gpu_preview,guides
    initial=gpu_preview._reference_meshes()
    mesh2=cmds.polyPlane()[0];guide2=guides.create(mesh2)
    assert gpu_preview._reference_nodes is None
    assert cmds.getAttr(guide2+'.meshName') in gpu_preview._reference_meshes()
    cmds.setAttr(guide2+'.meshName',cmds.getAttr(guide+'.meshName'),type='string')
    assert gpu_preview._reference_meshes()==initial
    cmds.delete(cmds.listRelatives(guide2,parent=True)[0],mesh2)
    assert gpu_preview._reference_nodes is None
    assert gpu_preview._reference_meshes()==initial
    for callback in gpu_preview._reference_callbacks:om.MMessage.removeCallback(callback)
    gpu_preview._reference_callbacks.clear()
    print('PASS retained plan, split/Undo invalidation, reference edits, symmetry constraints')
    from Aru_RetopoTool.tests import patch_transfer as transfer_test
    cmds.file(new=True,force=True);transfer_test.run()
    from Aru_RetopoTool.tests.final_position_snapshot import run as final_position_snapshot
    final_position_snapshot()
    from Aru_RetopoTool.tests.hidden_net_data import run as hidden_net_data
    hidden_net_data()
    from Aru_RetopoTool.tests.edit_lazy_classification import run as edit_lazy_classification
    edit_lazy_classification()
    from Aru_RetopoTool.tests.reference_mesh_snapshot import run as reference_snapshot
    reference_snapshot()
    from Aru_RetopoTool.tests.patch_preview_latency import run as preview_test
    preview_test()
    from Aru_RetopoTool.tests.renumber_local_edits import run as renumber_test
    renumber_test()
    mesh,guide,node,_,_=fixture();acc=e.RetopoGuideAccessor(guide);cn=acc.read()
    cn.positions.insert(0,[0.,0.,0.]);cn.splines=[tuple(v+1 for v in sp) for sp in cn.splines]
    acc.write(cn)
    offsets={2:(.1,.2,.3),6:(-.2,.15,-.1)}
    for i,value in offsets.items():cmds.setAttr(guide+'.controlPoints[%d]'%i,*value,type='double3')
    old_count=len(cn.positions)
    with api.undo_chunk('compact offsets'):
        removed,remap=e.prune_orphan_cvs_and_write(guide,acc.read())
    assert removed==1 and remap[2]==1 and remap[6]==5
    for i,value in offsets.items():assert np.allclose(cmds.getAttr(guide+'.controlPoints[%d]'%remap[i])[0],value)
    cmds.undo();assert len(acc.read().positions)==old_count
    for i,value in offsets.items():assert np.allclose(cmds.getAttr(guide+'.controlPoints[%d]'%i)[0],value)
    cmds.redo();assert len(acc.read().positions)==old_count-1
    for i,value in offsets.items():assert np.allclose(cmds.getAttr(guide+'.controlPoints[%d]'%remap[i])[0],value)
    print('PASS batched control-point capture, compacted indices and offsets through Undo/Redo')


if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python');status=0
    try:run()
    except BaseException:
        import traceback
        traceback.print_exc();status=1
    from maya import cmds
    cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
