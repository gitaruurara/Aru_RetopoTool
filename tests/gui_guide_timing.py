"""Profile guide callbacks during the existing restored brush benchmark."""
import time,json,statistics
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw,gpu_guides
from Aru_RetopoTool.tests import gui_numeric_stroke

def run():
    samples={}
    def measured(fn,key):
        def call(*args,**kwargs):
            start=time.perf_counter()
            try:return fn(*args,**kwargs)
            finally:samples.setdefault(key,[]).append((time.perf_counter()-start)*1000)
        return call
    with ExitStack() as stack:
        cls=draw.RetopoGuideGeometryOverride
        for name in ('updateDG','updateRenderItems','populateGeometry','addUIDrawables'):
            stack.enter_context(patch.object(cls,name,measured(getattr(cls,name),name)))
        for name in ('positions','configure_controls','upload_indices','sync_topology'):
            stack.enter_context(patch.object(gpu_guides,name,measured(getattr(gpu_guides,name),name)))
        gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)
    report={key:dict(count=len(values),total_ms=sum(values),median_ms=statistics.median(values),max_ms=max(values)) for key,values in samples.items()}
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
