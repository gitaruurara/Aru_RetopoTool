"""Scoped GUI timings; restores every wrapper after the existing Undo benchmark."""
import json
import statistics
import time
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from Aru_RetopoTool.tests import gui_numeric_stroke
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet import maya_projector
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview


def run(brush_start=(1546,1145)):
    rows = []
    phase = ['ordinary']
    def wrapper(fn, name):
        def measured(*args, **kwargs):
            start = time.perf_counter()
            try: return fn(*args, **kwargs)
            finally: rows.append((phase[0], name, (time.perf_counter()-start)*1000))
        return measured
    original_brush = RelaxPreview.brush
    def numeric_brush(*args, **kwargs):
        phase[0] = 'numeric'
        return original_brush(*args, **kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(RelaxPreview, 'brush', numeric_brush))
        for owner, names in (
            (relax, ('_world_data', 'brush_weights', '_relax_topology', '_smooth_junctions', '_fit_junction_lengths', '_fit_relax_routes')),
            (maya_projector, ('surface_hits', 'fit_routes', 'fit_routes_bound', 'junction_lengths', 'junction_directions', 'points_array')),
            (RelaxPreview, ('_check', 'write')),
        ):
            for name in names:
                stack.enter_context(patch.object(owner, name, wrapper(getattr(owner, name), name)))
        gui_numeric_stroke.run(direct_buffer=True, gpu_controls=True,brush_start=brush_start)
    summary = {}
    for phase_name, name, ms in rows:
        summary.setdefault(phase_name, {}).setdefault(name, []).append(ms)
    result = {mode: {name: {'count':len(values), 'median_ms':statistics.median(values), 'total_ms':sum(values)} for name, values in funcs.items()} for mode, funcs in summary.items()}
    Path(__file__).with_suffix('.json').write_text(json.dumps({'summary':result, 'rows':rows}, indent=2))
