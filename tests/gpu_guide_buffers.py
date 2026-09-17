"""Validate curve buffer topology and shared evaluated guide positions."""
import json
from types import SimpleNamespace
import numpy as np
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw
from Aru_RetopoTool.editor.curvenet import gpu_guides


def run():
    positions,splines=polygon(7)
    owner=SimpleNamespace(_positions=positions,_splines=splines)
    buffer=gpu_guides.positions(owner)
    reference=draw._bezier_strips(positions,splines,raw=True)
    expected=np.stack((reference[:,:-1],reference[:,1:]),axis=2).reshape(-1,3)
    np.testing.assert_allclose(buffer[owner._gpu_curve_indices],expected,atol=1e-7)
    np.testing.assert_allclose(buffer[:len(positions)],positions,atol=1e-7)
    assert owner._gpu_curve_indices.max()<len(buffer)
    assert len(owner._gpu_curve_indices)==len(splines)*draw._BEZIER_N*2
    for delta in (.1,-.2):
        owner._positions=[(x+delta,y,z) for x,y,z in positions]
        current=gpu_guides.positions(owner)
        ref=draw._bezier_strips(owner._positions,splines,raw=True)
        expected=np.stack((ref[:,:-1],ref[:,1:]),axis=2).reshape(-1,3)
        np.testing.assert_allclose(current[owner._gpu_curve_indices],expected,atol=1e-7)
    owner._splines=splines[:-1]
    current=gpu_guides.positions(owner)
    assert len(owner._gpu_curve_indices)==len(owner._splines)*draw._BEZIER_N*2
    # Compare incremental samples bit-for-bit with the original full evaluator.
    owner=SimpleNamespace(_positions=np.asarray(positions,dtype=float),_splines=splines)
    retained=gpu_guides.positions(owner); retained_copy=retained.copy()
    for point,delta in ((0,.012),(0,0.),(3,-.2),(len(positions)-1,.3)):
        owner._positions[point,0]+=delta
        actual=gpu_guides.positions(owner)
        controls=np.asarray(owner._positions,dtype=float)
        curves=owner._gpu_sample_basis @ controls[owner._gpu_sample_controls]
        expected=np.ascontiguousarray(np.concatenate((controls,curves.reshape(-1,3))),dtype=np.float32)
        np.testing.assert_array_equal(actual,expected)
        if delta==0.:assert owner._gpu_resampled_count==0
        else:assert owner._gpu_resampled_count==sum(point in sp for sp in splines)
    np.testing.assert_array_equal(retained,retained_copy)
    # Connectivity changes with the same counts must invalidate all samples.
    owner._splines=list(reversed(splines))
    actual=gpu_guides.positions(owner)
    assert owner._gpu_resampled_count==len(splines)
    expected=owner._gpu_sample_basis @ owner._positions[owner._gpu_sample_controls]
    np.testing.assert_array_equal(actual[len(positions):],expected.reshape(-1,3).astype(np.float32))
    from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
    cn=RetopoGuideData.from_dict({'positions':positions,'splines':splines})
    meta=SimpleNamespace()
    gpu_guides.sync_topology(meta,cn)
    saved=(meta._splines,meta._ep_set,meta._handle_set,meta._ep_types)
    cn.positions[0][0]+=.5
    gpu_guides.sync_topology(meta,cn)
    assert all(a is b for a,b in zip(saved,(meta._splines,meta._ep_set,meta._handle_set,meta._ep_types)))
    cn.splines.pop();cn.classify_endpoints()
    gpu_guides.sync_topology(meta,cn)
    assert meta._splines==tuple(cn.splines) and meta._splines is not saved[0]
    standalone=cn.add_cv((0,0,0));cn.standalone_eps.add(standalone)
    cn.classify_endpoints();gpu_guides.sync_topology(meta,cn)
    assert standalone in meta._ep_set
    meta._ep_types[standalone]='test-only'
    assert cn._endpoint_type[standalone]!='test-only'
    # The identity fast path is restricted to the documented read-only cache.
    frozen=RetopoGuideData.from_json_cached(json.dumps({'positions':positions,'splines':splines}))
    shared=SimpleNamespace()
    gpu_guides.sync_topology(shared,frozen,shared_readonly=True)
    token=shared._draw_topology_key
    gpu_guides.sync_topology(shared,frozen,shared_readonly=True)
    assert shared._draw_topology_key is token
    replacement=RetopoGuideData.from_dict({'positions':positions,'splines':splines[:-1]})
    gpu_guides.sync_topology(shared,replacement,shared_readonly=True)
    assert shared._splines==tuple(splines[:-1])
    # Switching back to mutable data must invalidate the read-only shortcut.
    gpu_guides.sync_topology(shared,replacement)
    replacement.splines.pop();replacement.classify_endpoints()
    gpu_guides.sync_topology(shared,replacement)
    assert shared._splines==tuple(replacement.splines)
    guide=cmds.createNode('retopoGuideNode')
    parent=cmds.listRelatives(guide,parent=True,fullPath=True)[0]
    try:
        cmds.setAttr(guide+'.netData',json.dumps({'positions':positions,'splines':splines}),type='string')
        selection=om.MSelectionList();selection.add(guide)
        override=draw.RetopoGuideGeometryOverride(selection.getDependNode(0))
        snapshots=[]
        for amount in (0.,.1,-.3):
            cmds.setAttr(guide+'.controlPoints[0]',amount,.02,0,type='double3')
            override.updateDG()
            expected=json.loads(cmds.getAttr(guide+'.outNetData'))['positions']
            assert override._is_valid
            assert isinstance(override._positions,np.ndarray)
            assert override._positions.flags.c_contiguous
            for retained,copy in snapshots:np.testing.assert_array_equal(retained,copy)
            snapshots.append((override._positions,override._positions.copy()))
            np.testing.assert_allclose(override._positions,expected,rtol=0,atol=0)
    finally:cmds.delete(parent)
    print('PASS GPU curve samples/indices preserve geometry and guide drawing uses evaluated output')
