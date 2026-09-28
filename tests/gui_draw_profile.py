"""Profile only synchronous viewport refresh, with scoped callback restoration."""
import cProfile, pstats, io
from pathlib import Path
from unittest.mock import patch
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.tests import gui_numeric_stroke

def run(brush_start=(1546,1145)):
    profile = cProfile.Profile()
    original = edit._dirty_shape_view
    def measured():
        return profile.runcall(original)
    try:
        with patch.object(edit, '_dirty_shape_view', measured):
            gui_numeric_stroke.run(direct_buffer=True, gpu_controls=True,brush_start=brush_start)
    finally:
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(65)
        Path(__file__).with_suffix('.txt').write_text(stream.getvalue(), encoding='utf-8')
