"""Exact native/Python Maya pixel coordinates and live camera refresh."""
import json,random,time,statistics,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_relax as relax,maya_screen


def run():
    report={};opened=False;pending=False
    try:
        cn,_=relax._world_data('aruRetopoGuideShape1')
        rng=random.Random(982)
        points=cn.positions+[[rng.uniform(-100,100) for _ in range(3)] for _ in range(200)]
        camera=cmds.modelPanel('modelPanel4',q=True,camera=True)
        if cmds.nodeType(camera)=='camera':camera=cmds.listRelatives(camera,parent=True,fullPath=True)[0]
        camera_shape=cmds.listRelatives(camera,shapes=True,fullPath=True)[0]
        original_y=cmds.getAttr(camera+'.rotateY')
        cases=[]
        cmds.undoInfo(openChunk=True,chunkName='Retopo screen projection diagnostic');opened=True;pending=True
        for turn,ortho in ((0,False),(13,False),(-21,True)):
            cmds.setAttr(camera+'.rotateY',original_y+turn)
            cmds.setAttr(camera_shape+'.orthographic',ortho);cmds.refresh(force=True)
            start=time.perf_counter();a=edit._world_to_screen_many_python(points);python_ms=(time.perf_counter()-start)*1000
            start=time.perf_counter();b=maya_screen.project(points);native_ms=(time.perf_counter()-start)*1000
            assert a==b,[(i,x,y) for i,(x,y) in enumerate(zip(a,b or [])) if x!=y][:3]
            cases.append({'turn':turn,'orthographic':ortho,'count':len(points),'python_ms':python_ms,'native_ms':native_ms})
        assert maya_screen.project([])==[]
        report['cases']=cases
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if opened:cmds.undoInfo(closeChunk=True)
        if pending:cmds.undo()
        cmds.refresh(force=True)
        Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
