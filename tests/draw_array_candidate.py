"""Temporary owned-array draw snapshot; restores the original callback."""
import inspect,textwrap
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw

def install():
    cls=draw.RetopoGuideGeometryOverride;original=cls.updateDG
    source=textwrap.dedent(inspect.getsource(original))
    old='positions=list(zip(values[0::3],values[1::3],values[2::3]))'
    assert old in source
    source=source.replace(old,"positions=__import__('numpy').array(values,dtype='float64').reshape(-1,3)")
    scope={};exec(compile(source,'<owned-draw-snapshot>','exec'),draw.__dict__,scope)
    cls.updateDG=scope['updateDG']
    def restore():cls.updateDG=original
    return restore
