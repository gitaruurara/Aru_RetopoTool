"""Warm projection cache must match a fresh surface, including seed output."""
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.core import Plan, unit
from Aru_RetopoTool.native import Surface, stencil


def run(points, triangles):
    p,s=fixture(4,4);plan=Plan(p,s,unit,3)
    warm=Surface(points,triangles);seeds=None
    try:
        for i in range(12):
            moved=list(p);v=p[0];moved[0]=(v[0]+(i//2)*.001,v[1],v[2])
            generated=plan.evaluate(moved,s,stencil)
            options=dict(iterations=3 if i<6 else 5,strength=.35 if i<8 else .6,
                         guide_weight=1. if i<10 else .5,seeds=seeds,guard=i!=11)
            cold=Surface(points,triangles)
            try: expected,expected_seeds=cold.relax(generated,plan,**options)
            finally:cold.close()
            previous=list(seeds) if seeds is not None else None
            actual,seeds=warm.relax(generated,plan,native_seeds=True,**options)
            if previous is not None:assert list(options['seeds'])==previous
            assert max(abs(a-b) for p,q in zip(actual,expected) for a,b in zip(p,q))<1e-12
            assert list(seeds)==expected_seeds
    finally:warm.close()
    print('PASS cached projection equals cold projection with deformation and option changes')
