"""GPU batches compared with the unchanged ordinary control drawing branch."""
import ast,inspect,json,time,statistics
from types import SimpleNamespace
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw
from Aru_RetopoTool.editor.curvenet.gpu_guides import draw_controls
from Aru_RetopoTool.tests.dense_performance import fixture
class Recorder:
    def __init__(self,record=True):self.events=[];self.record=record
    def setColor(self,v):self.color=tuple(v)
    def setPointSize(self,v):self.size=v
    def setLineWidth(self,v):self.width=v
    def points(self,values,screen):
        assert not screen
        if self.record:self.events.extend(('point',tuple(p),self.color,self.size) for p in values)
    def lineList(self,values,screen):
        assert not screen
        if self.record:self.events.extend(('line',tuple(p),self.color,self.width) for p in values)
def wrapper(record=True):
    m=draw._WorldForegroundDraw.__new__(draw._WorldForegroundDraw)
    m.manager=Recorder(record);m.np=np;m.pending=[];m.point_pending=[]
    m.outline=True;m.width=1.;m.color=draw.om2.MColor((.2,1.,1.,1.));m.point_size=None
    return m
def reference():
    tree=ast.parse(inspect.getsource(draw))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RetopoGuideGeometryOverride')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='addUIDrawables')
    branch=next(n for n in method.body if isinstance(n,ast.If) and '_WorldForegroundDraw' in ast.unparse(n.test))
    function=ast.parse('def legacy(self,drawManager,st):\n pos=self._positions\n psz=st["point_size"]\n hsz=st["handle_size"]\n').body[0]
    function.body+=branch.orelse
    module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    env=dict(vars(draw));exec(compile(module,'legacy_controls','exec'),env)
    return env['legacy']

def test_render_groups(owner,style):
    from Aru_RetopoTool.editor.curvenet import gpu_guides as gpu
    def reference_groups():
        lines,batches=gpu.cached_controls(owner,style)
        groups=[(gpu.render.MGeometry.kLines,(.55,.55,.55,.7),1.,np.asarray(lines,dtype=np.uint32))]
        by_style={}
        for key,indices in batches:by_style.setdefault(key,[]).extend(indices)
        for (color,size),indices in sorted(by_style.items(),key=lambda pair:pair[0][0]==(0.,1.,0.,1.)):
            groups.append((gpu.render.MGeometry.kPoints,color,size,np.asarray(indices,dtype=np.uint32)))
        return groups
    def check():
        actual=gpu.render_control_groups(owner,style);expected=reference_groups()
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):
            assert a[:3]==b[:3]
            np.testing.assert_array_equal(a[3],b[3])
            assert not a[3].flags.writeable
        return actual
    initial=check()
    saved=owner._positions[0]
    owner._positions[0]=tuple(float(x)+.05 for x in saved)
    assert check() is initial
    owner._positions[0]=saved
    mutations=[lambda:owner._selected_components.symmetric_difference_update({next(iter(owner._ep_set))}),
               lambda:style.update(show_handles=not style['show_handles']),
               lambda:style.update(handle_color=(.8,.2,.4)),
               lambda:style.update(point_size=style['point_size']+1),
               lambda:owner._manual_handles.symmetric_difference_update({next(iter(owner._handle_set))}),
               lambda:setattr(owner,'_splines',list(reversed(owner._splines)))]
    for mutate in mutations:
        previous=check();mutate();assert check() is not previous
    timings=[[],[]]
    for i in range(60):
        for index in (i%2,1-i%2):
            start=time.perf_counter()
            (reference_groups if index==0 else lambda:gpu.render_control_groups(owner,style))()
            timings[index].append((time.perf_counter()-start)*1000)
    print('PASS render index reuse, immutable arrays, selection/style/topology invalidation',
          {'before_ms':statistics.median(timings[0]),'after_ms':statistics.median(timings[1])})

def run():
    legacy=reference();positions,splines=fixture()
    eps={s[i] for s in splines for i in (0,3)};handles={s[i] for s in splines for i in (1,2)}
    owner=SimpleNamespace(_positions=positions,_splines=splines,_ep_set=eps,_handle_set=handles,
        _selected_components=set(),_sel_ep=None,_mirror_ep=None,_ep_types={i:'intersection' for i in eps},_manual_handles=set())
    style=dict(draw._DEFAULT_STYLE)
    for show in (True,False):
        for special in (False,True):
            style['show_handles']=show
            owner._selected_components={next(iter(eps)),next(iter(handles))} if special else set()
            owner._sel_ep=sorted(eps)[1] if special else None
            owner._mirror_ep=sorted(eps)[2] if special else None
            owner._manual_handles={sorted(handles)[1]} if special else set()
            a=wrapper();b=wrapper();legacy(owner,a,style);a.flush();draw_controls(owner,b,style);b.flush()
            assert a.manager.events==b.manager.events,(show,special)
    for delta in (.1,-.2):
        owner._positions=[(x+delta,y,z) for x,y,z in positions]
        style['point_size']+=1.;style['handle_size']+=.5
        style['handle_color']=(.2,.3,.4)
        a=wrapper();b=wrapper();legacy(owner,a,style);a.flush();draw_controls(owner,b,style);b.flush()
        assert a.manager.events==b.manager.events
    owner._positions=positions
    test_render_groups(owner,style)
    style['show_handles']=True;times=[[],[]]
    for i in range(16):
        for k in (i%2,1-i%2):
            manager=wrapper(False);start=time.perf_counter()
            (legacy if k==0 else draw_controls)(owner,manager,style);manager.flush()
            if i>=4:times[k].append((time.perf_counter()-start)*1000)
    result={'guides':len(splines),'legacy_prepare_ms':statistics.median(times[0]),'batch_prepare_ms':statistics.median(times[1])}
    print('PASS GPU control order, colors, sizes, hidden/selected/manual/mirrored controls',result)
    return result
if __name__=='__main__':
    import sys
    report=run()
    if len(sys.argv)>1:
        with open(sys.argv[1],'w') as f:json.dump(report,f,indent=2)
