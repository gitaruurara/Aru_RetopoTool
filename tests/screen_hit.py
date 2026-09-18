"""Scalar/batched screen hit parity, including missing projections and ties."""
import random
from unittest.mock import patch
from types import SimpleNamespace
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit,maya_screen


def run():
    with patch.object(maya_screen.C,'PyDLL',side_effect=OSError('missing test DLL')):
        try:maya_screen.load_library('missing.dll')
        except RuntimeError as exc:assert 'could not be loaded' in str(exc)
        else:raise AssertionError('Missing screen DLL accepted')
    with patch.object(maya_screen.C,'PyDLL',return_value=SimpleNamespace(aru_maya_screen_points=SimpleNamespace())):
        try:maya_screen.load_library('old.dll')
        except RuntimeError as exc:assert 'aru_maya_screen_segments' in str(exc)
        else:raise AssertionError('Old screen DLL accepted')
    lib=maya_screen.load_library(maya_screen.Path(maya_screen.__file__).resolve().parents[2]/'bin'/maya_screen.cmds.about(version=True)/maya_screen.BINARY_NAME)
    assert len(lib.aru_maya_screen_segments.argtypes)==10
    print('PASS required screen DLL exports and one-time signatures')
    rng=random.Random(3842)
    points=[[rng.uniform(-2,2) for _ in range(3)] for _ in range(48)]
    splines=[tuple(range(i,i+4)) for i in range(0,48,4)]
    splines += [splines[0],(0,0,0,0),(0,1,2,100)]
    cn=SimpleNamespace(positions=points,splines=splines)
    def project(p):
        if p[2]<-.75:return None
        return (int(100+45*p[0]/(1+.2*p[2])),int(100+45*p[1]/(1+.2*p[2])))
    with patch.object(maya_screen,'project',return_value=None), \
         patch.object(context,'_world_to_screen',side_effect=project), \
         patch.object(edit,'_world_to_screen_many',side_effect=lambda ps:[project(p) for p in ps]), \
         patch.object(context,'make_visibility_test',return_value=lambda p:p[0]>-.3):
        for index in range(100):
            x,y=rng.randrange(30,170),rng.randrange(30,170)
            options=dict(tol_px=(0,6,20)[index%3],exclude_eps={0} if index%2 else set(),mesh_name='test')
            a=context._find_spline_under_screen_scalar(cn,x,y,**options)
            b=context._find_spline_under_screen(cn,x,y,**options)
            assert a==b,(index,a,b)
    import math
    import numpy as np
    pixels=np.asarray([(0,0),(3,4),(80,0),(-80,0),(32767,-32768)]+[(rng.randrange(-32768,32768),rng.randrange(-32768,32768)) for _ in range(1500)],dtype=np.int16)
    valid=np.asarray([index%13!=7 for index in range(len(pixels))])
    with patch.object(maya_screen,'project',return_value=(pixels,valid)):
        for sx,sy in ((0,0),(.25,-.125),(32767,-32768),(-70000,80000)):
            for radius in (-1.,0.,5.,80.,80.00000000001,100000.):
                expected=[]
                for index,(pixel,ok) in enumerate(zip(pixels,valid)):
                    distance=math.hypot(int(pixel[0])-sx,int(pixel[1])-sy)
                    if ok and distance<radius:expected.append((index,distance))
                assert maya_screen.radius_candidates([],sx,sy,radius)==expected
    with patch.object(maya_screen,'project',return_value=None):
        assert maya_screen.radius_candidates([],0,0,80) is None
    print('PASS brush candidate distances/order, strict radius boundaries and signed pixel limits')
    print('PASS batched curve picking: 100 exact scalar matches, invalid projections, exclusions, visibility and ties')
