"""Fixed soft-selection weights, projected positions and stable topology."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax,curve_net_symmetry as sym,brush
from Aru_RetopoTool.editor.curvenet.soft_move import SoftMove
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.test_core import network


def run():
    axis,space=sym.get_axis(),sym.get_space()
    try:
        sym.set_axis('');sym.set_space('world')
        mesh=cmds.polyPlane(w=20,h=20,sx=10,sy=10)[0]
        points,splines=network([(-2,0,0),(0,0,0),(2,0,0)],[(0,1),(1,2)])
        cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
        guide=guides.create(mesh);edit.RetopoGuideAccessor(guide).write(cn)
        with patch.object(relax,'brush_weights',return_value={0:.25,1:1.}):move=SoftMove(guide,1,(100,100))
        a=move.move((0,0,1));b=move.move((0,0,1))
        assert a.positions==b.positions
        for v,z in ((0,.25),(1,1.),(2,0.)):
            assert abs(a.positions[v][2]-z)<1e-6,(v,a.positions[v])
            assert abs(a.positions[v][1])<1e-6
        assert a.splines==cn.splines and len(a.positions)==len(cn.positions)
        c=move.move((0,0,.5))
        assert abs(c.positions[0][2]-.125)<1e-6
        # A new radius never changes weights mid-stroke.
        with patch.object(brush,'radius',return_value=999):assert move.move((0,0,1)).positions==a.positions
        sym.set_axis('x')
        with patch.object(relax,'brush_weights',return_value={2:1.,1:.5}):move=SoftMove(guide,2,(100,100))
        result=move.move((2.5,0,.5))
        assert abs(result.positions[1][0])<1e-8
        assert abs(result.positions[2][0]+result.positions[0][0])<1e-8
        assert abs(result.positions[2][2]-result.positions[0][2])<1e-8
        assert result.splines==cn.splines
        with patch.object(relax,'brush_weights',return_value={0:.8,1:1.,2:.3}):move=SoftMove(guide,1,(100,100))
        result=move.move((1.,0,.5))
        assert abs(result.positions[1][0])<1e-8
        assert abs(result.positions[2][0]+result.positions[0][0])<1e-8
        assert abs(result.positions[2][2]-result.positions[0][2])<1e-8
        # Curved reference: every moved EP must remain on the actual polygonal surface.
        sym.set_axis('')
        sphere=cmds.polySphere(r=5,sx=24,sy=16)[0]
        from Aru_RetopoTool.editor.curvenet import curve_net_context as context
        surface_points=[context._project_on_mesh(sphere,p)[0] for p in ((-2,4,0),(0,5,0),(2,4,0))]
        points,splines=network(surface_points,[(0,1),(1,2)])
        guide=guides.create(sphere);edit.RetopoGuideAccessor(guide).write(RetopoGuideData.from_dict(dict(positions=points,splines=splines)))
        with patch.object(relax,'brush_weights',return_value={0:.4,1:1.,2:.4}):move=SoftMove(guide,1,(100,100))
        result=move.move((0,4,2),draft=False)
        for v in result.endpoint_indices():
            closest=context._project_on_mesh(sphere,result.positions[v])[0]
            assert sum((closest[k]-result.positions[v][k])**2 for k in range(3))<1e-10
        assert result.splines==splines
        print('PASS soft move falloff, absolute/idempotent drag, surface projection, fixed weights, seam, symmetry, topology')
    finally:sym.set_axis(axis);sym.set_space(space)


if __name__=='__main__':
    result=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();result=1
    finally:
        cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(result)
