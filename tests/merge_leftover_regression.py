"""Physical weld cleanup, filled boundary ancestry, compaction and undo."""
import sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from maya import cmds
from Aru_RetopoTool import core,guides,maya_api as api,patch_context,patch_transfer
from Aru_RetopoTool.editor.curvenet import curve_net_context as c,curve_net_edit as e,curve_net_symmetry as sym
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.test_core import network
from Aru_RetopoTool.tests.mesh_assertions import face_count


def run():
    sym.set_axis('')
    for selected_count in (1,2):
        cmds.file(new=True,force=True)
        mesh=cmds.polyPlane(w=10,h=10)[0]
        points,splines=network([(-2,0,0),(0,0,0),(0,0,2),(-2,0,2),
                               (.2,0,0),(2,0,0),(2,0,2),(.2,0,2)],
                              [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4)])
        cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
        # Differently shaped incoming boundary still becomes one edge after weld.
        cn.positions[splines[7][1]][0]+=.3
        guide=guides.create(mesh);acc=e.RetopoGuideAccessor(guide);acc.write(cn)
        output,node=api.create(guide,mesh)
        loops=core.regions(cn.positions,cn.splines,lambda p:(0,1,0))
        keys=sorted(core.patch_key(loop) for loop in loops)
        cmds.setAttr(node+'.selectedPatches',json.dumps(keys[:selected_count]),type='string')
        original=cmds.getAttr(guide+'.netData');oldkeys=cmds.getAttr(node+'.selectedPatches')
        with api.undo_chunk('weld adjoining patch borders'):
            cn=acc.read()
            c._merge_two_eps(cn,1,4);c._merge_two_eps(cn,2,7)
            assert len(cn.splines)==7
            assert cn.splines[1]==splines[1], 'destination curve must survive'
            assert len({tuple(sorted((sp[0],sp[3]))) for sp in cn.splines})==7
            c._commit_net_data(guide,cn)
        result=acc.read()
        assert not result.orphan_cv_indices()
        assert len(patch_context.selected(node))==selected_count
        assert face_count(output)>0
        merged=cmds.getAttr(guide+'.netData')
        cmds.undo();assert cmds.getAttr(guide+'.netData')==original
        assert cmds.getAttr(node+'.selectedPatches')==oldkeys
        cmds.redo();assert cmds.getAttr(guide+'.netData')==merged
        assert len(patch_context.selected(node))==selected_count
        print('PASS actual merge, distinct duplicate cleanup, patch fill, compact, Undo/Redo',selected_count)
    # A direct edge between merged endpoints is removed, unrelated edges survive.
    points,splines=network([(0,0,0),(1,0,0),(2,0,0)],[(0,1),(1,2)])
    cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
    c._merge_two_eps(cn,0,1)
    assert len(cn.splines)==1 and cn.splines[0][0]==0 and cn.splines[0][3]==2
    print('PASS collapsed curve removal')
    sym.set_axis('x');sym.set_space('world')
    points,splines=network([(1,0,0),(2,0,0),(2,0,2),(-1,0,0),(-2,0,0),(-2,0,2)],
                          [(0,1),(0,2),(1,2),(3,4),(3,5),(4,5)])
    cn=RetopoGuideData.from_dict(dict(positions=points,splines=splines))
    cn.positions[0]=list(cn.positions[1]);cn.positions[3]=list(cn.positions[4])
    guide=guides.create(mesh);acc=e.RetopoGuideAccessor(guide);acc.write(cn)
    cmds.optionVar(sv=('retopoGuideContext_node',guide))
    from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
    state=RetopoGuideState();ctx=c.RetopoGuideContext(state)
    state.drag_ep=0;state.drag_mirror_ep=3;state.merge_target=1
    ctx._release_impl()
    result=acc.read()
    assert len(result.splines)==2,result.splines
    print('PASS real release welds both symmetry sides despite coincident dragged endpoints')

if __name__=='__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
    code=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();code=1
    finally:
        cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
