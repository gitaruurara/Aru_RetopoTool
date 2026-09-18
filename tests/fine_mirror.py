"""Fine guide loops must mirror independently of a large reference bounding box."""
import os,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.test_core import network


def run():
    for size in (1.,1000.):
        cmds.file(new=True,force=True)
        mesh=cmds.polyPlane(w=size,h=size)[0]
        for center in (.05,.00002):
            radius=center*.2;n=12
            points=[(center+radius*math.cos(i*2*math.pi/n),0,radius*math.sin(i*2*math.pi/n)) for i in range(n)]
            points,splines=network(points,[(i,(i+1)%n) for i in range(n)])
            guide=guides.create(mesh);acc=edit.RetopoGuideAccessor(guide)
            acc.write(RetopoGuideData.from_dict(dict(positions=points,splines=splines)))
            original=cmds.getAttr(guide+'.netData')
            assert edit.mirror_curvenet(guide,axis='x',space='world',direction='positive',mode='add',quiet=True)==n
            mirrored=acc.read();assert len(mirrored.splines)==2*n
            eps=mirrored.endpoint_indices();assert len(eps)==2*n
            for p in points[:n]:
                target=(-p[0],p[1],p[2])
                assert min(math.dist(target,mirrored.positions[v]) for v in eps)<1e-8,(size,center,target,min((math.dist(target,mirrored.positions[v]),mirrored.positions[v]) for v in eps))
            cmds.undo();assert cmds.getAttr(guide+'.netData')==original
            cmds.redo();assert len(acc.read().splines)==2*n
            assert edit.mirror_curvenet(guide,axis='x',space='world',direction='positive',mode='add',quiet=True)==0
            assert len(acc.read().splines)==2*n
            edit.mirror_curvenet(guide,axis='x',space='world',direction='positive',mode='replace',quiet=True)
            assert len(acc.read().splines)==2*n
    print('PASS fine loops, near-center details, large reference, repeat add/replace, Undo/Redo')

if __name__=='__main__':
    code=0
    try:run()
    except Exception:
        import traceback;traceback.print_exc();code=1
    finally:cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(code)
