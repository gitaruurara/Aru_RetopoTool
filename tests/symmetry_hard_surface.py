"""Regression coverage for paired construction and exact cube features."""
import math
from maya import cmds
from Aru_RetopoTool.tests.mesh_assertions import face_count
from Aru_RetopoTool import construction as c,core,guides,maya_api as api,patch_context,hard_surface as hard
from Aru_RetopoTool.editor.curvenet import curve_net_context as ctx,curve_net_edit as edit,curve_net_symmetry as sym
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    axis,space=sym.get_axis(),sym.get_space();old_hard=bool(hard.enabled())
    try:
        sym.set_axis('x');sym.set_space('world')
        plane=cmds.polyPlane(w=20,h=20,sx=10,sy=10)[0]
        cn=RetopoGuideData()
        for p in [(1,0,0),(2,0,0),(3,0,0)]:cn.add_cv(p)
        for a,b in [(0,1),(1,2)]:ctx._add_spline_to_cn(cn,plane,a,b)
        cn.classify_endpoints()
        edges=c.boundary_edges(cn,{0},set(),lambda p:(0,1,0))
        keys=c.extrude(cn,plane,edges,[0,0,1])
        assert len(keys)==4 and len(cn.endpoint_indices())==12
        for i in cn.endpoint_indices():assert sym.find_mirror_ep(cn,plane,i,1e-5) is not None
        guide=guides.create(plane);edit.RetopoGuideAccessor(guide).write(cn)
        output,node=api.create(guide,plane)
        patch_context.confirm(node,next(iter(keys)))
        assert len(patch_context.selected(node))==2
        patch_context.confirm(node,next(iter(keys)),True)
        assert not patch_context.selected(node)
        cmds.undo();assert len(patch_context.selected(node))==2
        from Aru_RetopoTool.symmetry_ops import delete_targets
        targets,_=delete_targets(guide,{0});assert len(targets)==2
        _,targets=delete_targets(guide,splines={0});assert len(targets)==2
        print('PASS symmetric extrusion, paired patch fill/remove and Undo')
        cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],plane)
        # Bridge a pair of open borders on one side; create the paired band.
        plane=cmds.polyPlane(w=20,h=20,sx=10,sy=10)[0]
        net=RetopoGuideData()
        for p in [(1,0,0),(2,0,0),(1,0,1),(2,0,1)]:net.add_cv(p)
        ctx._add_spline_to_cn(net,plane,0,1);ctx._add_spline_to_cn(net,plane,2,3)
        keys=c.bridge(net,plane,[(0,1,0)],[(2,3,1)])
        assert len(keys)==2
        # A center-plane EP and its reflected copy must be the same index.
        from Aru_RetopoTool.symmetry_ops import mirrored_splines
        net=RetopoGuideData();net.add_cv([0,0,0]);net.add_cv([1,0,0]);ctx._add_spline_to_cn(net,plane,0,1)
        mirrored_splines(net,plane,{0},True)
        assert len(net.endpoint_indices())==3
        # Reflection uses the transformed reference's local symmetry plane.
        cmds.move(4,2,-3,plane);cmds.rotate(0,35,20,plane)
        sym.set_space('object')
        from Aru_RetopoTool.hard_surface import mesh_fn
        transform=mesh_fn(plane).dagPath().inclusiveMatrix()
        import maya.api.OpenMaya as om
        net=RetopoGuideData()
        for p in [(1,0,0),(2,0,0)]:
            q=om.MPoint(*p)*transform;net.add_cv([q.x,q.y,q.z])
        ctx._add_spline_to_cn(net,plane,0,1);mirrored_splines(net,plane,{0},True)
        assert len(net.endpoint_indices())==4
        for i in net.endpoint_indices():assert sym.find_mirror_ep(net,plane,i,1e-5) is not None
        cmds.delete(plane)
        sym.set_space('world');sym.set_axis('x')
        sphere=cmds.polySphere(r=3,sx=32,sy=24)[0]
        f,dag=edit._get_mesh_fn(sphere)
        points=ctx._compute_ring_by_plane(f,dag,[1,0,0],[1,0,0],8)
        net=RetopoGuideData();ctx._create_ring_curve(net,sphere,points)
        assert len(net.endpoint_indices())==16
        for i in net.endpoint_indices():assert sym.find_mirror_ep(net,sphere,i,1e-5) is not None
        points=ctx._compute_ring_by_plane(f,dag,[0,0,0],[0,1,0],7,phase=13)
        net=RetopoGuideData();ctx._create_ring_curve(net,sphere,points)
        assert len(net.endpoint_indices())==len(points)
        for i in net.endpoint_indices():assert sym.find_mirror_ep(net,sphere,i,1e-5) is not None
        cmds.delete(sphere)
        print('PASS mirrored bridge, seam deduplication, object-space reflection and paired rings')
        sym.set_axis('');cmds.optionVar(iv=(hard.OPTION,1))
        cube=cmds.polyCube(w=4,h=4,d=4)[0]
        guide=guides.create(cube);output,node=api.create(guide,cube)
        assert hard.create_guides(node)==12
        assert hard.create_guides(node)==0
        cn=edit.RetopoGuideAccessor(guide).read()
        assert len(cn.endpoint_indices())==8
        fn=hard.mesh_fn(cube)
        import maya.api.OpenMaya as om
        for sp in cn.splines:
            for t in (.1,.3,.5,.7,.9):
                p=core.bezier(cn.positions,sp,t);q,_=fn.getClosestPoint(om.MPoint(*p),om.MSpace.kWorld)
                assert math.dist(p,tuple(q)[:3])<1e-6
        from Aru_RetopoTool.editor.curvenet.curve_net_relax import relax
        before=[list(cn.positions[i]) for i in cn.endpoint_indices()]
        with api.undo_chunk('cube relax'):relax(guide,{i:1 for i in cn.endpoint_indices()},strength=.5)
        cn=edit.RetopoGuideAccessor(guide).read()
        assert before==[list(cn.positions[i]) for i in cn.endpoint_indices()]
        f,dag=edit._get_mesh_fn(cube)
        ring=ctx._compute_ring_by_plane(f,dag,[0,0,0],[0,1,0],5,phase=13)
        assert all(any(math.dist(p,q)<1e-6 for q in ring) for p in [(-2,0,-2),(-2,0,2),(2,0,-2),(2,0,2)])
        assert face_count(output)==0
        print('PASS cube 12 straight features, deduplication, pinned relax corners, ring corners, explicit faces')
        cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],cube)
    finally:
        sym.set_axis(axis);sym.set_space(space);cmds.optionVar(iv=(hard.OPTION,int(old_hard)))
