"""Profile junction fitting without permanently changing any callback."""
import cProfile,pstats,io
from pathlib import Path
from unittest.mock import patch
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.tests import gui_numeric_stroke

def run():
    profiler=cProfile.Profile();original=relax._fit_junction_lengths
    def measured(*args,**kwargs):return profiler.runcall(original,*args,**kwargs)
    try:
        with patch.object(relax,'_fit_junction_lengths',measured):
            gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
    finally:
        stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
        Path(__file__).with_suffix('.txt').write_text(stream.getvalue(),encoding='utf-8')
