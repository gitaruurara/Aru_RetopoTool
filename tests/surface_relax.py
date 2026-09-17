"""Surface-relax integration checks; run inside a disposable Maya process."""
import json
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet import curve_net_context as context
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.curve_net_edit import RetopoGuideAccessor


def test_topology_cache():
    cn = RetopoGuideData()
    for i in range(8): cn.add_cv((i, 0, 0))
    cn.add_spline(0, 1, 2, 3)
    cn.add_spline(3, 4, 5, 0)
    cn.add_spline(3, 6, 7, 3)  # Preserve self-loop handle semantics.
    cn.standalone_eps.add(6)
    graph = relax._relax_topology(cn)
    assert graph[1][3] == (2, 4, 6)
    assert graph[2][3][-2:] == ((2, 6, 3), (2, 7, 3))
    import copy
    copied = copy.deepcopy(cn)
    assert relax._relax_topology(copied) is graph
    copied.positions[0][0] += 10
    assert copied.positions[0] != cn.positions[0]
    copied.splines.pop()
    assert relax._relax_topology(copied) is not graph
    assert relax._relax_topology(cn) is graph
    cn.positions[0][0] += .25
    cn.manual_handles.add(1)
    assert relax._relax_topology(cn) is graph
    try:
        graph[0][0] = ()
        raise AssertionError('Cached graph must be read-only')
    except TypeError: pass
    # Rewiring, adding/removing splines, standalone EPs and CV count invalidate.
    for change in (
        lambda: cn.splines.__setitem__(0, (0, 1, 2, 6)),
        lambda: cn.splines.append((6, 1, 2, 0)),
        lambda: cn.splines.pop(),
        lambda: cn.standalone_eps.add(7),
        lambda: cn.add_cv((8, 0, 0)),
    ):
        change()
        updated = relax._relax_topology(cn)
        assert updated is not graph
        graph = updated
    print('PASS relax adjacency reuse and topology invalidation')


def test_normals_array():
    import numpy as np
    from Aru_RetopoTool.editor.curvenet import maya_projector as projector, curve_net_edit as edit
    mesh=cmds.polySphere(sx=12,sy=8,ch=False)[0]
    cmds.setAttr(mesh+'.scale',1.2,.8,1.1,type='double3')
    fn,_dag=edit._get_mesh_fn(mesh)
    queries=np.asarray([[.2,1.4,.1],[-.8,.2,.3],[.1,-1.1,.4]])
    try:
        assert projector.normals_array(fn,[]).shape==(0,3)
        expected=np.asarray([hit[1] for hit in projector.surface_hits(fn,queries)])
        actual=projector.normals_array(fn,queries)
        np.testing.assert_array_equal(actual,expected)
        assert actual.flags.c_contiguous and actual.flags.owndata
        actual[0]=0
        np.testing.assert_array_equal(projector.normals_array(fn,queries),expected)
        with patch.object(projector,'get_projector',return_value=None):
            expected=np.asarray([hit[1] for hit in projector.surface_hits(fn,queries)])
            np.testing.assert_array_equal(projector.normals_array(fn,queries),expected)
    finally:cmds.delete(mesh)
    print('PASS normals-only arrays: native/fallback exact normals, transforms, empty and ownership')


def run():
    test_normals_array()
    test_topology_cache()
    reference = cmds.polyPlane(w=20, h=20, sx=10, sy=10)[0]
    guide = cmds.createNode('retopoGuideNode')
    parent = cmds.listRelatives(guide, parent=True)[0]
    for obj in (reference, parent):
        cmds.setAttr(obj+'.translate', 4,2,1, type='double3')
        cmds.setAttr(obj+'.rotate', 17,23,8, type='double3')
        cmds.setAttr(obj+'.scale', 1.3,1,.8, type='double3')
    cn = RetopoGuideData()
    for p in ((-2,0,0),(0,.5,1),(2,0,0)): cn.add_cv(p)
    for a,b in ((0,1),(1,2)):
        h0=cn.add_cv([(2*cn.positions[a][k]+cn.positions[b][k])/3 for k in range(3)])
        h1=cn.add_cv([(cn.positions[a][k]+2*cn.positions[b][k])/3 for k in range(3)])
        cn.add_spline(a,h0,h1,b)
    cn.classify_endpoints()
    acc=RetopoGuideAccessor(guide);acc.write(cn);acc.mesh_name=reference
    cmds.setAttr(guide+'.controlPoints[1].xValue',.1)
    original=cmds.getAttr(guide+'.netData')
    evaluated=json.loads(cmds.getAttr(guide+'.outNetData'))
    with patch.object(relax.edit, '_world_to_screen_many', side_effect=lambda ps:[(100,100) for p in ps]), \
         patch.object(relax.edit, 'make_visibility_test', return_value=lambda p:p[1]>2):
        weights=relax.brush_weights(guide,100,100)
        world,_=relax._world_data(guide)
        assert all(world.positions[v][1]>2 for v in weights)
    # The shared brush snapshot must produce the same complete data as the
    # separate read path, including transformed positions and surface bindings.
    captured=[]
    with patch.object(relax.edit, '_world_to_screen_many', side_effect=lambda ps:[(100,100) for p in ps]), \
         patch.object(relax.edit, 'make_visibility_test', return_value=lambda p:p[1]>2), \
         patch.object(RetopoGuideAccessor, 'write', side_effect=lambda cn:captured.append(cn.to_dict())):
        separate=relax.relax(guide,relax.brush_weights(guide,100,100),draft=False)
        with patch.object(relax,'_world_data',wraps=relax._world_data) as read_world:
            shared=relax.brush_relax(guide,100,100,draft=False)
            assert read_world.call_count==1
        assert separate==shared and captured[0]==captured[1]
        with patch.object(relax,'_world_data',wraps=relax._world_data) as read_world:
            assert relax.brush_relax(guide,1000,1000)==set()
            assert read_world.call_count==1 and len(captured)==2
    assert cmds.getAttr(guide+'.netData')==original
    assert json.loads(cmds.getAttr(guide+'.outNetData'))==evaluated
    print('PASS shared brush snapshot parity, empty brush and scene ownership')
    cmds.undoInfo(openChunk=True,chunkName='surface relax test')
    try:
        affected=relax.relax(guide,{1:1},draft=False)
    finally: cmds.undoInfo(closeChunk=True)
    updated=acc.read()
    assert affected=={1}
    assert updated.splines==cn.splines
    assert len(updated.positions)==len(cn.positions)
    assert abs(updated.positions[1][1])<1e-5
    assert updated.positions[1][2]<evaluated['positions'][1][2]
    for ep in (0,2):
        assert max(abs(a-b) for a,b in zip(updated.positions[ep],evaluated['positions'][ep]))<1e-6
    cmds.undo()
    assert cmds.getAttr(guide+'.netData')==original
    assert abs(cmds.getAttr(guide+'.controlPoints[1].xValue')-.1)<1e-8
    print('PASS relax projection, smoothing, world transforms, stable connectivity, Undo')
    # Verify drag threshold and routing without synthesizing desktop input.
    state=RetopoGuideState(); ctx=context.RetopoGuideContext(state)
    stroke={'node':guide,'snapped':2,'origin':(100,100),'last':(100,100),'moved':False,'affected':set()}
    context._state_set(state,'relax_stroke',stroke)
    with patch.object(relax,'brush_weights',return_value={1:1}), patch.object(relax,'relax',return_value={1}) as run_relax:
        assert ctx._relax_drag(101,101) and not stroke['moved']
        assert not run_relax.called
        assert ctx._relax_drag(110,100) and stroke['moved']
        assert stroke['affected']=={1}
        with patch.object(ctx,'_merge_shift_click') as merge:
            ctx._release_impl()
            assert not merge.called
    context._state_set(state,'relax_stroke',dict(stroke,moved=False))
    with patch.object(ctx,'_merge_shift_click') as merge:
        ctx._release_impl()
        merge.assert_called_once_with(guide,2)
    print('PASS Shift click preserves merge; Shift drag relaxes without merging')
    cmds.delete(parent,reference)
    # A latitude row on a sphere must not become separate great-circle arches.
    import math
    import numpy as np
    sphere = cmds.polySphere(r=5, sx=80, sy=60)[0]
    fn, dag = relax.edit._get_mesh_fn(sphere)
    net = RetopoGuideData()
    for angle in (-.5, 0., .5):
        net.add_cv([4*math.sin(angle), 3., 4*math.cos(angle)])
    for a, b in ((0, 1), (1, 2)):
        h = net.add_cv([(2*net.positions[a][k]+net.positions[b][k])/3 for k in range(3)])
        j = net.add_cv([(net.positions[a][k]+2*net.positions[b][k])/3 for k in range(3)])
        net.add_spline(a,h,j,b)
    net.classify_endpoints()
    for si in range(2): context._fit_spline_handles_to_mesh(net, si, sphere)
    def kink():
        p = np.array(net.positions[1])
        v = np.array(net.positions[net.splines[0][2]])-p
        w = np.array(net.positions[net.splines[1][1]])-p
        return float(np.dot(v,w)/(np.linalg.norm(v)*np.linalg.norm(w)))
    before = kink()
    ep_positions = {ep:list(net.positions[ep]) for ep in net.endpoint_indices()}
    context._smooth_moved_ep_routes(net, {1, None}, sphere)
    assert kink() < -.999999, (before, kink())
    assert all(net.positions[ep] == p for ep, p in ep_positions.items())
    assert before > kink()+.001, (before, kink())
    errors = []
    for sp in net.splines:
        for t in np.linspace(0, 1, 21):
            p = context._bezier_point(*(net.positions[i] for i in sp), float(t))
            projected, _, _ = relax.edit._closest_point_on_mesh(fn, dag, p)
            errors.append(np.linalg.norm(np.array(p)-projected))
    assert max(errors)<.08, max(errors)
    print('PASS sphere junction tangent continuity and surface error', max(errors))
    # MMB release must run the same route smoother after its final geodesic fit.
    guide = cmds.createNode('retopoGuideNode')
    parent = cmds.listRelatives(guide, parent=True)[0]
    acc = RetopoGuideAccessor(guide); acc.write(net); acc.mesh_name = sphere
    previous_node = cmds.optionVar(q='retopoGuideContext_node') if cmds.optionVar(exists='retopoGuideContext_node') else None
    cmds.optionVar(sv=('retopoGuideContext_node', guide))
    state = RetopoGuideState(); ctx = context.RetopoGuideContext(state)
    state.drag_ep = 1
    before_release = cmds.getAttr(guide+'.netData')
    cmds.undoInfo(openChunk=True, chunkName='MMB route fit test')
    try:
        with patch.object(context, '_smooth_moved_ep_routes', wraps=context._smooth_moved_ep_routes) as fit:
            ctx._release_impl()
            assert fit.call_count == 1
    finally: cmds.undoInfo(closeChunk=True)
    net = acc.read()
    assert kink() < -.999999
    assert all(net.positions[ep] == p for ep, p in ep_positions.items())
    cmds.undo()
    assert cmds.getAttr(guide+'.netData') == before_release
    # Artist-authored handles on a segment must not be changed by MMB smoothing.
    manual = net.splines[0][2]
    net.mark_manual_handle(manual)
    saved = {h:list(net.positions[h]) for h in net.splines[0][1:3]}
    context._smooth_moved_ep_routes(net, {1}, sphere)
    assert all(net.positions[h] == p for h,p in saved.items())
    if previous_node is None: cmds.optionVar(remove='retopoGuideContext_node')
    else: cmds.optionVar(sv=('retopoGuideContext_node', previous_node))
    cmds.delete(parent, sphere)
    print('PASS MMB release route fit, fixed EP positions, manual handles, Undo')
