"""Avoid recursive hover rendering without delaying explicit click evaluation."""
from types import SimpleNamespace
from unittest.mock import patch
from Aru_RetopoTool import patch_context as pc
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit

def run():
    probe=SimpleNamespace(context='test',node='test',_extrude_press=True)
    assert not edit.view_refresh_active()
    with patch.object(edit.cmds,'optionVar',return_value=False),patch.object(edit.cmds,'about',return_value=False),patch.object(pc.cmds,'currentCtx',return_value='test') as current,patch.object(pc.cmds,'objExists',return_value=True):
        def refresh(**kwargs):
            assert edit.view_refresh_active()
            pc.PatchTool.tick(probe);assert current.call_count==0
            pc.PatchTool.tick(probe,force=True);assert current.call_count==1
            def failed(**kwargs):
                assert edit._VIEW_REFRESH_DEPTH==2
                raise RuntimeError('render failed')
            with patch.object(edit.cmds,'refresh',side_effect=failed):
                try:edit._dirty_shape_view()
                except RuntimeError:pass
                else:raise AssertionError('Expected render error')
            assert edit._VIEW_REFRESH_DEPTH==1
        with patch.object(edit.cmds,'refresh',side_effect=refresh):edit._dirty_shape_view()
        assert not edit.view_refresh_active()
        pc.PatchTool.tick(probe);assert current.call_count==2
        with patch.object(edit.cmds,'refresh',side_effect=RuntimeError('outer failure')):
            try:edit._dirty_shape_view()
            except RuntimeError:pass
        assert not edit.view_refresh_active()
    print('PASS nested redraw suppression, forced click evaluation and exception recovery')
