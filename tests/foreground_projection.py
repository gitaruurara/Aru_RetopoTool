"""Preserve foreground projection and clipping when bypassing Maya point copies."""
import numpy as np
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet.curve_net_draw import _ForegroundDraw, _bezier_strips


def run():
    class Manager:
        def __init__(self): self.lines=[]
        def setColor(self, value): pass
        def setLineWidth(self, value): pass
        def lineList(self, points, draw2d):
            assert draw2d
            self.lines.append([(p.x,p.y,p.z) for p in points])
    class Path:
        def inclusiveMatrix(self): return om.MMatrix()
    class Frame:
        def __init__(self, matrix): self.matrix=matrix
        def getMatrix(self, kind): return self.matrix
        def getViewportDimensions(self): return (13,17,1600,900)
    rng=np.random.default_rng(917)
    points=rng.uniform(-2,2,(20,3)).tolist()
    splines=[(i,i+1,i+2,i+3) for i in range(0,16,4)]
    raw=_bezier_strips(points,splines,raw=True)
    legacy=_bezier_strips(points,splines)
    matrices=[om.MMatrix(),om.MMatrix((1,0,0,0,0,1,0,0,0,0,1,.25,0,0,0,1))]
    for matrix in matrices:
        manager=Manager();draw=_ForegroundDraw(manager,Path(),Frame(matrix))
        for strip in raw: draw.lineStrip(strip,False)
        draw.flush()
        reference=[]
        for strip in legacy:
            for a,b in zip(strip,list(strip)[1:]):
                qa=a*matrix;qb=b*matrix
                if any(q.w<=1e-10 or q.z < -q.w for q in (qa,qb)): continue
                reference.extend([(13+(q.x/q.w+1)*800,17+(q.y/q.w+1)*450,0) for q in (qa,qb)])
        assert len(manager.lines)==2
        np.testing.assert_allclose(manager.lines[0],reference,rtol=0,atol=1e-9)
        np.testing.assert_allclose(manager.lines[1],reference,rtol=0,atol=1e-9)
    print('PASS batched foreground matches scalar projection, clipping, outline and all curve samples')
