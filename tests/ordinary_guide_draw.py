"""World-space fallback preserves geometry, marker order and cache invalidation."""
from types import SimpleNamespace
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw, gpu_guides as gpu
from Aru_RetopoTool.tests.gpu_control_batches import reference, wrapper, Recorder

def run():
    owner=SimpleNamespace(_positions=[[i*.2, i%3, 0.] for i in range(8)],
        _splines=[(0,1,2,3),(3,4,5,6)],_ep_set={0,3,6,7},
        _handle_set={1,2,4,5},_selected_components={1,3},
        _sel_ep=0,_mirror_ep=6,_ep_types={7:'intersection'},_manual_handles={2})
    def check():
        actual=draw._cached_bezier_strips(owner)
        expected=draw._bezier_strips(owner._positions,owner._splines)
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):np.testing.assert_array_equal(np.asarray(a),np.asarray(b))
        return list(actual)
    first=check();second=check()
    assert all(a is b for a,b in zip(first,second))
    owner._positions[1][0]+=.25
    third=check();assert third[0] is not second[0] and third[1] is second[1]
    owner._splines[1]=(6,5,4,3);check()
    owner._splines.append((3,4,5,90));check()
    owner._splines.pop()
    # Existing render items must switch cleanly between foreground, ordinary
    # and disabled modes. Ordinary controls retain ordered UI marker batches.
    from unittest.mock import patch
    class Item:
        def getShader(self):return None
        def setDepthPriority(self,value):pass
        def enable(self,value):self.enabled=value
    class Items(list):
        def indexOf(self,name):return gpu.NAMES.index(name)
    items=Items([Item(),Item()]);owner._style=dict(draw._DEFAULT_STYLE)
    owner._is_valid=True
    with patch.object(gpu,'configure_controls') as controls, patch.object(gpu,'GPU_CONTROLS',True):
        for enabled,foreground in ((True,True),(True,False),(False,False),(False,True),(True,True)):
            gpu.configure(owner,items,enabled,foreground=foreground)
            assert [i.enabled for i in items]==[enabled and foreground,enabled]
            assert owner._gpu_curve_active==enabled
            assert controls.call_args.args[2]==(enabled and foreground)
        owner._is_valid=False;gpu.configure(owner,items,True,foreground=False)
        assert not any(i.enabled for i in items)
    legacy=reference()
    for show in (True,False):
        style=dict(draw._DEFAULT_STYLE,show_handles=show)
        expected=wrapper();legacy(owner,expected,style);expected.flush()
        actual=Recorder();gpu.draw_controls(owner,actual,style,wrapped=False)
        assert actual.events==expected.manager.events
    owner._positions=[];owner._splines=[];assert check()==[]
    print('PASS ordinary strips, selective invalidation, topology, marker order/colors/sizes')
