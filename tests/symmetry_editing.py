"""Center-curve constraints and explicit mirrored patch selection."""
import json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides,maya_api as api,core,patch_context
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_symmetry as sym,symmetry_constraints as constraint
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.test_core import network


def drag_checks():
    from unittest.mock import patch
    from contextlib import ExitStack
    from Aru_RetopoTool.editor.curvenet import curve_net_context as context,brush
    from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
    cmds.file(new=True,force=True);sym.set_axis('x');sym.set_space('world')
    cmds.optionVar(iv=(brush.SOFT,0));cmds.optionVar(iv=(brush.MERGE,0))
    mesh=cmds.polyPlane(w=12,h=12)[0]
    pts,splines=network([(0,0,0),(0,0,2),(2,0,2)],[(0,1),(1,2)])
    guide=guides.create(mesh);edit.RetopoGuideAccessor(guide).write(RetopoGuideData.from_dict(dict(positions=pts,splines=splines)))
    cmds.optionVar(sv=('retopoGuideContext_node',guide))
    state=RetopoGuideState();ctx=context.RetopoGuideContext(state)
    point=[0.,0.,0.]
    original=cmds.getAttr(guide+'.netData')
    with ExitStack() as stack:
        stack.enter_context(patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else [100,100,0]))
        stack.enter_context(patch.object(cmds,'getModifiers',return_value=0))
        stack.enter_context(patch.object(context,'_raycast_from_screen',side_effect=lambda *a:point[:]))
        stack.enter_context(patch.object(context,'_find_spline_under_screen',return_value=None))
        ctx.press();assert state.drag_ep==0 and state.drag_side==0.
        point[:]=[.5,0,.25];ctx._drag_impl();ctx.release()
        result=edit.RetopoGuideAccessor(guide).read()
        assert abs(result.positions[0][0])<1e-8 and result.positions[0][2]>.1
        for h in constraint.seam_handles(result,mesh):assert abs(result.positions[h][0])<1e-8
        cmds.undo();assert cmds.getAttr(guide+'.netData')==original
        def press_handle():
            state.drag_handle=splines[0][1];state.drag_handle_anchor=pts[state.drag_handle]
        stack.enter_context(patch.object(ctx,'_press_impl',side_effect=press_handle))
        stack.enter_context(patch.object(context,'_screen_to_view_plane',return_value=[1,0,1]))
        ctx.press();ctx._drag_impl();ctx.release()
        result=edit.RetopoGuideAccessor(guide).read()
        assert abs(result.positions[splines[0][1]][0])<1e-8
        assert splines[0][1] in result.manual_handles
        cmds.undo();assert cmds.getAttr(guide+'.netData')==original
    print('PASS real center EP/handle drag handlers, plane lock, manual handles and Undo')


def run():
    saved=sym.get_axis(),sym.get_space()
    try:
        for space in ('world','object'):
            for sign in (1,-1):
                cmds.file(new=True,force=True)
                mesh=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
                sym.set_axis('x');sym.set_space(space)
                if space=='object':
                    cmds.setAttr(mesh+'.translate',3,0,2,type='double3');cmds.setAttr(mesh+'.rotateY',32)
                matrix=om.MMatrix(cmds.xform(mesh,q=True,ws=True,m=True)) if space=='object' else om.MMatrix()
                points,splines=network([(sign*x,0,z) for x,z in ((0,0),(1,0),(2,0),(0,1),(1,1),(2,1))],[(0,1),(1,2),(2,5),(5,4),(4,3),(3,0),(1,4)])
                points=[list(om.MPoint(*p)*matrix)[:3] for p in points]
                cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
                guide=guides.create(mesh);edit.RetopoGuideAccessor(guide).write(cn)
                output,node=api.create(guide,mesh)
                fn,_=edit._get_mesh_fn(mesh);normal=lambda p:edit._get_normal_at_point(fn,p)
                loops=core.regions(cn.positions,cn.splines,normal)
                keys=[core.patch_key(loop) for loop in loops]
                cmds.setAttr(node+'.selectedPatches',json.dumps(keys[:1]),type='string')
                raw=cmds.getAttr(guide+'.netData')
                edit.mirror_curvenet(guide,axis='x',space=space,direction='positive' if sign==1 else 'negative',mode='add',quiet=True)
                assert len(patch_context.selected(node))==2,patch_context.selected(node)
                result=edit.RetopoGuideAccessor(guide).read()
                assert len(core.regions(result.positions,result.splines,normal))==4
                seam=constraint.seam_handles(result,mesh)
                assert seam
                for h in seam:
                    p=list(result.positions[h]);p[0]+=.25
                    result.positions[h]=constraint.drag_position(result,h,p,mesh,.01)
                    assert sym.on_symmetry_plane(result.positions[h],mesh,1e-6)
                count=len(result.splines)
                cmds.undo();assert cmds.getAttr(guide+'.netData')==raw
                assert patch_context.selected(node)==set(keys[:1])
                cmds.redo();assert len(patch_context.selected(node))==2
                edit.mirror_curvenet(guide,axis='x',space=space,direction='positive' if sign==1 else 'negative',mode='add',quiet=True)
                assert len(edit.RetopoGuideAccessor(guide).read().splines)==count
                assert len(patch_context.selected(node))==2
                # Replacement removes destination fill choices and rebuilds
                # them exclusively from the source, even after repeated mirrors.
                all_keys={core.patch_key(loop) for loop in core.regions(result.positions,result.splines,normal)}
                source_keys={core.patch_key(loop) for loop in core.regions(result.positions,result.splines,normal)
                    if all(sym.plane_coord(result.positions[result.splines[si][e]],mesh)*sign>=-1e-6 for side in loop for si,_ in side for e in (0,3))}
                before_replace=(all_keys-source_keys)|(patch_context.selected(node)&source_keys)
                assert len(before_replace)==3
                cmds.setAttr(node+'.selectedPatches',json.dumps(sorted(before_replace)),type='string')
                edit.mirror_curvenet(guide,axis='x',space=space,direction='positive' if sign==1 else 'negative',mode='replace',quiet=True)
                assert len(patch_context.selected(node))==2
                cmds.undo();assert patch_context.selected(node)==before_replace
        # A filled patch crossing the plane stays filled after source replacement.
        cmds.file(new=True,force=True)
        sym.set_axis('');sym.set_space('world')
        mesh=cmds.polyPlane(w=12,h=12)[0]
        points,splines=network([(-1,0,0),(2,0,0),(2,0,1),(-1,0,1)],[(0,1),(1,2),(2,3),(3,0)])
        guide=guides.create(mesh)
        edit.RetopoGuideAccessor(guide).write(RetopoGuideData.from_dict(dict(positions=points,splines=splines)))
        output,node=api.create(guide,mesh)
        key=core.patch_key(core.regions(points,splines,lambda p:(0,1,0))[0])
        cmds.setAttr(node+'.selectedPatches',json.dumps([key]),type='string')
        edit.mirror_curvenet(guide,axis='x',space='world',direction='positive',mode='replace',quiet=True)
        assert len(patch_context.selected(node))==1,patch_context.selected(node)
        from Aru_RetopoTool.tests.mesh_assertions import mesh_fn
        fn=mesh_fn(output)
        assert fn.numPolygons>0
        assert all(fn.getPolygonNormal(i).y>0 for i in range(fn.numPolygons))
        drag_checks()
        print('PASS mirrored confirmed/unconfirmed patches, shared seam, object/world, both directions, repeat, Undo/Redo')
    finally:sym.set_axis(saved[0]);sym.set_space(saved[1])


if __name__=='__main__':
    result=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();result=1
    finally:
        cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(result)
