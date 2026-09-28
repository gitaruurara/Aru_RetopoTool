"""Manual handle parity through real drag/release/reset paths in isolated Maya."""
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from maya import cmds
import maya.api.OpenMaya as om
from unittest.mock import patch
from contextlib import ExitStack
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_context as c,curve_net_edit as e,curve_net_symmetry as sym,brush
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
from Aru_RetopoTool.tests.test_core import network


def close(a,b):assert max(abs(x-y) for x,y in zip(a,b))<1e-6,(a,b)


def run():
    for space in ('world','object'):
      for reverse in (False,True):
        cmds.file(new=True,force=True)
        sym.set_axis('x');sym.set_space(space)
        cmds.optionVar(iv=(brush.SOFT,0));cmds.optionVar(iv=(brush.MERGE,0))
        mesh=cmds.polyPlane(w=20,h=20)[0]
        if space=='object':
            cmds.setAttr(mesh+'.translate',3,1,2,type='double3');cmds.setAttr(mesh+'.rotateY',32)
        matrix=om.MMatrix(cmds.xform(mesh,q=True,ws=True,m=True))
        points,splines=network([(1,0,0),(1,0,3),(-1,0,0),(-1,0,3)],[(0,1),(3,2)])
        points=[list(om.MPoint(*p)*matrix)[:3] for p in points]
        cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
        source=1 if reverse else 0;target=1-source
        h=splines[source][1];mh=splines[target][2]
        assert c._find_mirror_handle(cn,mesh,h)==mh
        guide=guides.create(mesh);acc=e.RetopoGuideAccessor(guide);acc.write(cn)
        cmds.optionVar(sv=('retopoGuideContext_node',guide))
        state=RetopoGuideState();ctx=c.RetopoGuideContext(state)
        state.drag_handle=h;state.drag_handle_anchor=points[h]
        c._state_set(state,'drag_mirror_handle',mh)
        pos=[points[h][0]+.2,points[h][1]+.15,points[h][2]+.1]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else [100,100,0]))
            stack.enter_context(patch.object(c,'_raycast_from_screen',return_value=points[0]))
            stack.enter_context(patch.object(c,'_screen_to_view_plane',return_value=pos))
            ctx._drag_impl()
        edited=acc.read()
        assert {h,mh}<=edited.manual_handles
        close(edited.positions[mh],sym.mirror_point(edited.positions[h],mesh))
        ctx._release_impl();edited=acc.read()
        for a,b in zip(splines[source][1:3],reversed(splines[target][1:3])):
            close(edited.positions[b],sym.mirror_point(edited.positions[a],mesh))
            assert (a in edited.manual_handles)==(b in edited.manual_handles)
        # Both fixed handles must follow endpoint motion by their own EP delta.
        ep=splines[source][0];mep=splines[target][3]
        before=acc.read();old=[list(p) for p in before.positions]
        state.drag_ep=ep;state.drag_mirror_ep=mep;state.drag_side=sym.plane_coord(old[ep],mesh)
        destination=list(om.MPoint(*(1 if source==0 else -1,0,.4))*matrix)[:3] if source==0 else list(om.MPoint(-1,0,3.4)*matrix)[:3]
        with ExitStack() as stack:
            stack.enter_context(patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else [100,100,0]))
            stack.enter_context(patch.object(c,'_raycast_from_screen',return_value=destination))
            stack.enter_context(patch.object(ctx,'_point_preview_for',return_value=None))
            ctx._drag_impl()
        moved=acc.read()
        for endpoint,handle in ((ep,h),(mep,mh)):
            close(moved.positions[handle],[old[handle][k]+moved.positions[endpoint][k]-old[endpoint][k] for k in range(3)])
        original=cmds.getAttr(guide+'.netData')
        assert e.reset_manual_handles(guide,[h])==2
        assert not ({h,mh}&acc.read().manual_handles)
        cmds.undo();assert cmds.getAttr(guide+'.netData')==original
        cmds.redo();assert not ({h,mh}&acc.read().manual_handles)
        print('PASS drag locks, release parity, fixed EP following, mirrored unlock Undo/Redo',space,reverse)
    # A shared seam must match from either overlapping curve, regardless of order.
    sym.set_space('world')
    points,splines=network([(0,0,0),(0,0,3)],[(0,1),(1,0)])
    cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
    for a,b in zip(splines[0][1:3],reversed(splines[1][1:3])):
        assert c._find_mirror_handle(cn,'',a)==b
        assert c._find_mirror_handle(cn,'',b)==a
    print('PASS reciprocal seam handle matching')

if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
    code=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();code=1
    finally:
        cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
