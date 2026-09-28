"""Regressions for off-origin preview bounds and symmetry-plane relaxation."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'

def run():
    import maya.api.OpenMaya as om
    from maya import cmds
    from unittest.mock import patch
    from Aru_RetopoTool import guides
    from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
    from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
    from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as sym
    from Aru_RetopoTool.editor.curvenet import curve_net_context as context
    from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
    from Aru_RetopoTool.tests.test_core import network
    from Aru_RetopoTool import preview_locator

    cmds.loadPlugin(str(Path(preview_locator.__file__).parent/'bin'/cmds.about(version=True)/preview_locator.BINARY), quiet=True)
    node=cmds.createNode(preview_locator.TYPE)
    points=[-5.,180.,11., 5.,193.,18., 0.,187.,15.]
    cmds.setAttr(node+'.positions',points,type='doubleArray')
    bounds=cmds.exactWorldBoundingBox(node)
    assert bounds==[-5.,180.,11.,5.,193.,18.],bounds
    moved=[v+20 if i%3==0 else v for i,v in enumerate(points)]
    cmds.setAttr(node+'.positions',moved,type='doubleArray')
    assert cmds.exactWorldBoundingBox(node)==[15.,180.,11.,25.,193.,18.]
    print('PASS off-origin preview bounds and position updates')
    cmds.delete(cmds.listRelatives(node,parent=True)[0])

    axis,space=sym.get_axis(),sym.get_space()
    try:
        sym.set_axis('x')
        for mode in ('world','object'):
            sym.set_space(mode)
            mesh=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
            if mode=='object':
                cmds.setAttr(mesh+'.translate',3,0,2,type='double3')
                cmds.setAttr(mesh+'.rotateY',32)
            matrix=om.MMatrix(cmds.xform(mesh,q=True,ws=True,m=True))
            pts,splines=network([(0,0,0),(2,0,1),(-1,0,1)],[(0,1),(0,2)])
            pts=[list(om.MPoint(*p)*matrix)[:3] for p in pts]
            guide=guides.create(mesh)
            cn=RetopoGuideData.from_dict(dict(positions=pts,splines=splines))
            edit.RetopoGuideAccessor(guide).write(cn)
            raw=cmds.getAttr(guide+'.netData')
            world,world_matrix=relax._world_data(guide)
            out=[]
            relax.relax(guide,{0:1.},strength=.2,_world=(world,world_matrix),_writer=out.append)
            assert len(out)==1
            assert abs(sym.plane_coord(out[0].positions[0],mesh))<1e-8,out[0].positions[0]
            assert out[0].splines==cn.splines
            assert cmds.getAttr(guide+'.netData')==raw
            print('PASS center EP stays on seam during asymmetric relax:',mode)
        sym.set_space('world')
        for sign in (1.,-1.):
            with patch.object(context,'_project_on_mesh',return_value=([-sign*.1,0,1],0,[])), patch.object(context,'_snap_pos_to_plane',return_value=([0,0,1],0,[])):
                p,_,_,on=context._apply_symmetry_constraint('',[sign*.1,0,1],side=sign)
                assert on and p[0]==0
        print('PASS projection cannot cross symmetry plane in either direction')
    finally:
        sym.set_axis(axis);sym.set_space(space)

if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
    code=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();code=1
    finally:
        from maya import cmds
        cmds.file(new=True,force=True)
        maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
