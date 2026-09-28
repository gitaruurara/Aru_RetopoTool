"""Curve clicks, loop preview/commit, native extrusion overlay and respacing."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from maya import cmds
from unittest.mock import patch
from contextlib import ExitStack
from Aru_RetopoTool import core,density,curve_loop,drag_extrude as d,construction,guides,maya_api as api,patch_context
from Aru_RetopoTool.editor.curvenet import curve_net_context as c,curve_net_edit as e,curve_net_symmetry as sym
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState, _ctx
from Aru_RetopoTool.tests.test_core import network


def fixture():
    cmds.file(new=True,force=True);sym.set_axis('')
    mesh=cmds.polyPlane(w=10,h=10)[0]
    p,s=network([(-2,0,-2),(2,0,-2),(2,0,2),(-2,0,2)],[(0,1),(1,2),(2,3),(3,0)])
    cn=RetopoGuideData.from_dict(dict(positions=p,splines=s))
    guide=guides.create(mesh);e.RetopoGuideAccessor(guide).write(cn)
    output,node=api.create(guide,mesh)
    cmds.optionVar(sv=('retopoGuideContext_node',guide))
    key=core.patch_key(core.regions(p,s,lambda p:(0,1,0))[0])
    patch_context.confirm(node,key)
    return mesh,guide,node,p,s


def run():
    mesh,guide,node,p,s=fixture();state=_ctx;state.sel_ep=None;ctx=c.RetopoGuideContext(state)
    hit=[0,.3,core.bezier(p,s[0],.3)]
    with ExitStack() as stack:
        stack.enter_context(patch.object(cmds,'draggerContext',side_effect=lambda *a,**kw:1 if kw.get('button') else [100,100,0]))
        stack.enter_context(patch.object(cmds,'getModifiers',return_value=0))
        stack.enter_context(patch.object(c,'_raycast_from_screen',side_effect=lambda *a:hit[2]))
        stack.enter_context(patch.object(c,'_find_spline_under_screen',side_effect=lambda *a,**kw:tuple(hit)))
        ctx.press();ctx.release()
        cn=e.RetopoGuideAccessor(guide).read();assert len(cn.splines)==5
        assert state.sel_ep is not None
        hit[:]=[2,.7,core.bezier(p,s[2],.7)]
        ctx.press();ctx.release()
    cn=e.RetopoGuideAccessor(guide).read();assert len(cn.splines)==7
    assert len(patch_context.selected(node))==2,(patch_context.selected(node),e.RetopoGuideAccessor(guide).read().to_dict())
    cmds.undo();assert len(e.RetopoGuideAccessor(guide).read().splines)==5
    cmds.redo();assert len(patch_context.selected(node))==2
    print('PASS real curve clicks insert, connect, split filled patch, Undo/Redo')
    mesh,guide,node,p,s=fixture()
    raw=cmds.getAttr(guide+'.netData');pv=curve_loop.Preview(node)
    with patch.object(d,'mouse',return_value=(100,100)),patch.object(c,'_find_spline_under_screen',return_value=(0,.35,core.bezier(p,s[0],.35))):
        pv.update()
        assert pv.pending and cmds.getAttr(guide+'.netData')==raw
        assert d.overlays(node) and all(construction.preview_lines[path] for path in d.overlays(node))
        pv.commit()
    assert len(patch_context.selected(node))==2
    cmds.undo();assert cmds.getAttr(guide+'.netData')==raw
    cmds.redo();assert len(patch_context.selected(node))==2
    print('PASS loop preview routes to native overlay without writes, commit, Undo/Redo')
    # Self-mirrored boundaries receive matching cuts on both sides of the plane.
    mesh,guide,node,p,s=fixture();sym.set_axis('x');sym.set_space('world')
    cn=e.RetopoGuideAccessor(guide).read();added=curve_loop.build(cn,mesh,0,.3)
    assert len(added)==2
    assert len(core.regions(cn.positions,cn.splines,lambda p:(0,1,0)))==3
    sym.set_axis('')
    print('PASS symmetric loop insertion on a self-mirrored patch')
    # Ctrl on guide curves takes priority; Ctrl on patch interiors still reduces.
    from types import SimpleNamespace
    from Aru_RetopoTool import qt
    hits=[]
    fake=SimpleNamespace(context='test',node=node,brush=None,local=SimpleNamespace(event=lambda ev:hits.append('reduce') or True))
    event=SimpleNamespace(type=lambda:qt.QEvent.MouseButtonPress,button=lambda:qt.Qt.MiddleButton,
                          modifiers=lambda:qt.Qt.ControlModifier)
    preview=SimpleNamespace(pending=True,update=lambda:None,commit=lambda:hits.append('insert'))
    fake.loop_preview=preview
    with patch.object(cmds,'currentCtx',return_value='test'),patch.object(patch_context,'viewport_receiver',return_value=True):
        assert patch_context.PatchTool.eventFilter(fake,None,event)
        assert hits==['insert']
        preview.pending=None;hits.clear()
        assert patch_context.PatchTool.eventFilter(fake,None,event)
        assert hits==['reduce']
    print('PASS Ctrl MMB curve insertion and patch reduction routing')

    from Aru_RetopoTool.tests.drag_extrude import run as extrusion
    cmds.file(new=True,force=True);extrusion()
    p,s=network([(0,0,0),(4,0,0),(4,0,4),(0,0,4)],[(0,1),(1,2),(2,3),(3,0)])
    base=core.Plan(p,s,lambda p:(0,1,0),3)
    requests=[];plan=base
    for count in range(2):
        for seed in density.Topology(plan.faces).owners:
            try:
                request=density.describe(plan,seed)
                candidate=density.apply(base,requests+[request])
                if len(candidate.applied)==len(requests)+1:break
            except ValueError:continue
        else:raise AssertionError('No reduction found')
        requests.append(request);plan=candidate
        coords=next(iter(plan.edit_coordinates().values()))
        for k in (0,1):
            values=sorted({round(p[k],10) for p in coords.values()})
            assert max(abs(values[i]-i/(len(values)-1)) for i in range(len(values)))<1e-8
        pts=plan.evaluate(p,s);offsets,ids,weights=plan.compile_stencil(s)
        for i,point in enumerate(pts):
            computed=[sum(p[ids[j]][k]*weights[j] for j in range(offsets[i],offsets[i+1])) for k in range(3)]
            assert max(abs(a-b) for a,b in zip(point,computed))<1e-8
    print('PASS repeated loop reduction evenly redistributes positions and compiled stencils')
    from Aru_RetopoTool.tests.test_core import polygon
    p,s=polygon(5);base=core.Plan(p,s,lambda p:(0,1,0),3)
    for seed in density.Topology(base.faces).owners:
        try:
            candidate=density.apply(base,[density.describe(base,seed)])
            if candidate.applied:break
        except ValueError:continue
    else:raise AssertionError('No general-patch reduction')
    pts=candidate.evaluate(p,s);offsets,ids,weights=candidate.compile_stencil(s)
    assert candidate._base_samples
    for i,point in enumerate(pts):
        compiled=[sum(p[ids[j]][k]*weights[j] for j in range(offsets[i],offsets[i+1])) for k in range(3)]
        assert max(abs(a-b) for a,b in zip(point,compiled))<1e-8
    print('PASS general patch redistribution and native stencil parity')

    from Aru_RetopoTool.tests import test_core,test_regions,test_local_edits
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_core,test_regions,test_local_edits))
    assert unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()

if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python');status=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();status=1
    finally:
        cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
