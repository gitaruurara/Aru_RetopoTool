"""Reuse only identical positions, connectivity, normals and source spline IDs."""
from Aru_RetopoTool import regions_native as regions
from Aru_RetopoTool.tests.test_core import polygon

def run():
    from unittest.mock import patch
    native=regions.library();calls=[]
    class Create:
        def __call__(self,*args):calls.append(1);return native.aru_regions_create(*args)
    class Proxy:
        aru_regions_create=Create()
        def __getattr__(self,name):return getattr(native,name)
    p,s=polygon(5);normal=lambda p:(0.,1.,0.)
    # Initialize the real ctypes signatures before wrapping its constructor.
    regions.regions(p,s,normal)
    regions._REGION_CACHE.clear()
    with patch.object(regions,'library',return_value=Proxy()):
        first=regions.regions(p,s,normal);assert len(calls)==1
        assert regions.regions(p,s,normal)==first and len(calls)==1
        # Returned list mutation cannot corrupt cached loop grouping.
        first[0].clear();assert regions.regions(p,s,normal)[0]
        p[0]=tuple(v+.01 for v in p[0]);regions.regions(p,s,normal);assert len(calls)==2
        regions.regions(p,s,lambda p:(.01,1.,0.));assert len(calls)==3
        shifted=list(reversed(s));regions.regions(p,shifted,normal);assert len(calls)==4
        for offset in range(6):
            moved=[(x+offset*.1,y,z) for x,y,z in p]
            regions.regions(moved,s,normal)
        assert len(regions._REGION_CACHE)==4
        try:regions.regions(p,s,lambda p:(0.,1.))
        except ValueError:pass
        else:raise AssertionError('Cached hit must still validate normals')
    regions._REGION_CACHE.clear()
    print('PASS exact region cache keys, fresh output lists, invalidation and bounded ownership')
