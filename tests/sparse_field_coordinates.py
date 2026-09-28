"""Selective paint coordinates preserve shared seams and reduced-plan weights."""
import inspect,random
from Aru_RetopoTool import core,local_fields as fields,density,regions_native
from Aru_RetopoTool.tests.test_core import network,polygon

def run():
    scope=dict(vars(fields))
    exec(inspect.getsource(fields.weights).replace('plan.edit_coordinates(fields)','plan.edit_coordinates()'),scope)
    legacy=scope['weights']
    p,s=network([(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,1),(2,0,0)],
                [(0,1),(1,2),(2,3),(3,0),(2,4),(4,5),(5,3)])
    plan=core.Plan(p,s,lambda p:(0,1,0),3)
    first,last=plan.region_keys
    paint={};fields.paint(paint,.5,.5,.35,.8);fields.paint(paint,1.,.5,.75,1.)
    expected=fields.coordinates(plan)
    subset=plan.edit_coordinates({first})
    assert subset=={first:expected[first]}
    assert set(plan._partial_edit_coordinates)=={first}
    assert not hasattr(plan,'_edit_coordinates')
    assert plan.edit_coordinates({'missing'})=={}
    assert plan.edit_coordinates({last})=={last:expected[last]}
    assert plan.edit_coordinates()==expected
    for payload in ({},{'missing':paint},{first:paint},{last:paint},{first:paint,last:paint}):
        fresh=core.Plan(p,s,lambda p:(0,1,0),3)
        actual=fields.weights(fresh,payload,.7)
        assert actual==legacy(fresh,payload,.7)
    for n in (3,4,5,7):
        for level in (1,2,3):
            pp,ss=polygon(n);item=core.Plan(pp,ss,lambda p:(0,1,0),level)
            assert item.edit_coordinates(set(item.region_keys))==fields.coordinates(item)
    reduced=None
    for seed in density.Topology(plan.faces).owners:
        try:
            candidate=density.apply(plan,[density.describe(plan,seed)])
            if candidate.applied:reduced=candidate;break
        except ValueError:pass
    assert reduced is not None
    for payload in ({first:paint},{first:paint,last:paint},{'missing':paint}):
        assert fields.weights(reduced,payload,.7)==legacy(reduced,payload,.7)
    # Duplicate and reversed boundaries retain the previous alias tolerance.
    old=inspect.getsource(regions_native.spline_aliases)
    old=old.replace('        if candidates:\n            extent', '        if True:\n            extent')
    scope=dict(vars(regions_native));exec(old,scope)
    rng=random.Random(91)
    for _ in range(50):
        points=[tuple(rng.uniform(-1,1) for k in range(3)) for i in range(12)]
        curves=[(0,1,2,3),(3,2,1,0),(0,4,5,3),(6,7,8,9)]
        points[4]=tuple(v+rng.choice((0.,1e-11,1e-6)) for v in points[1]);points[5]=points[2]
        assert regions_native.spline_aliases(points,curves)==scope['spline_aliases'](points,curves)
    print('PASS selective coordinates, shared seam weights, reduced plans, alias tolerance')
