"""Editable lazy metadata matches eager edits without sharing parsed data."""
from unittest.mock import patch
from Aru_RetopoTool.tests.curve_edit_features import fixture
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit

def run():
    _,guide,_,_,_=fixture();accessor=edit.RetopoGuideAccessor(guide)
    lazy=accessor.read();other=accessor.read();raw=accessor.read_raw_json()
    eager=RetopoGuideData.from_json(raw)
    assert lazy._lazy_objects and not eager._lazy_objects
    assert lazy is not other and lazy.positions[0] is not other.positions[0]
    def compare():
        assert lazy.to_dict()==eager.to_dict()
        assert lazy._endpoint_type==eager._endpoint_type
        assert lazy.curves==eager.curves
        assert lazy.ep_indices==eager.ep_indices and lazy.handle_indices==eager.handle_indices
        for cn in (lazy,eager):
            assert {ep.cv_idx for ep in cn.eps}==cn.ep_indices
            for i,sp in enumerate(cn.splines):
                assert cn.handle_at(sp[1],i).position==cn.positions[sp[1]]
    compare()
    with patch.object(lazy,'_rebuild_curves',wraps=lazy._rebuild_curves) as rebuild:
        for _ in range(5):lazy.classify_endpoints()
        assert rebuild.call_count==0
    for cn in (lazy,eager):
        cn.positions[0][0]+=.2;cn.manual_handles.add(cn.splines[0][1]);cn.classify_endpoints()
    compare()
    for cn in (lazy,eager):
        cn.split_spline(0,.4);cn.classify_endpoints()
    compare()
    for cn in (lazy,eager):
        cn.standalone_eps.add(cn.add_cv((4.,0.,4.)));cn.classify_endpoints()
    compare()
    assert other.to_json()==raw
    print('PASS lazy editable classification, independent ownership, wrappers, split and standalone endpoints')
