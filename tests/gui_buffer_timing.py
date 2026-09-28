"""Separate direct-buffer callbacks from synchronous viewport refresh."""
import ctypes as C,json,time
from pathlib import Path
from unittest.mock import patch
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.tests import gui_buffer_session


def run(plugin='aru_retopo_buffer_preview_timing.mll'):
    root=Path(__file__).resolve().parents[1]
    lib=C.CDLL(str(root/'bin/2027'/plugin))
    lib.aru_buffer_stats.argtypes=[C.POINTER(C.c_double),C.POINTER(C.c_longlong)]
    lib.aru_buffer_stats.restype=None
    ms=(C.c_double*3)();counts=(C.c_longlong*3)()
    selection=om.MSelectionList();selection.add('aruRetopoNative1')
    output=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outPositions',False)
    original=edit._dirty_shape_view;rows=[]
    def measured():
        start=time.perf_counter();output.asMObject();evaluated=time.perf_counter()
        lib.aru_buffer_stats(ms,counts)
        original();finished=time.perf_counter()
        lib.aru_buffer_stats(ms,counts)
        rows.append(dict(evaluate_ms=(evaluated-start)*1000,draw_ms=(finished-evaluated)*1000,buffer_ms=list(ms),buffer_calls=list(counts)))
    with patch.object(edit,'_dirty_shape_view',measured):gui_buffer_session.run()
    Path(__file__).with_suffix('.json').write_text(json.dumps(rows,indent=2))
