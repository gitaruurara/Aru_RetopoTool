"""Fused native picker versus existing NumPy picker across cameras and tolerances."""
import json,random,time,statistics,traceback
from pathlib import Path
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool.editor.curvenet import screen_hit,maya_screen,curve_net_edit as edit,curve_net_relax as relax

def run():
    report={};opened=False
    try:
        cn,_=relax._world_data('aruRetopoGuideShape1');mesh=edit.RetopoGuideAccessor('aruRetopoGuideShape1').mesh_name
        camera=cmds.modelPanel('modelPanel4',q=True,camera=True)
        if cmds.nodeType(camera)=='camera':camera=cmds.listRelatives(camera,parent=True,fullPath=True)[0]
        shape=cmds.listRelatives(camera,shapes=True,fullPath=True)[0]
        rotation=cmds.getAttr(camera+'.rotateY');eps=sorted(cn.endpoint_indices());cases=[]
        cmds.undoInfo(openChunk=True,chunkName='Fused hit verification');opened=True
        for turn,ortho in ((0,False),(13,False),(-21,True)):
            cmds.setAttr(camera+'.rotateY',rotation+turn);cmds.setAttr(shape+'.orthographic',ortho);cmds.refresh(force=True)
            pixels=edit._world_to_screen_many([cn.positions[ep] for ep in eps])
            rng=random.Random(271);timings=[[],[]];exact=0
            for index in range(120):
                pixel=pixels[rng.randrange(len(pixels))]
                if pixel is None:continue
                sx,sy=pixel[0]+rng.randint(-14,14),pixel[1]+rng.randint(-14,14)
                tolerance=(1.,4.,10.,20.)[index%4];exclude={eps[index%len(eps)]} if index%2 else set()
                start=time.perf_counter();actual=screen_hit.find_spline(cn,sx,sy,tolerance,exclude,mesh);timings[0].append((time.perf_counter()-start)*1000)
                with patch.object(maya_screen,'segment_candidates',return_value=None):
                    start=time.perf_counter();expected=screen_hit.find_spline(cn,sx,sy,tolerance,exclude,mesh);timings[1].append((time.perf_counter()-start)*1000)
                assert actual==expected,(turn,ortho,index,actual,expected)
                exact+=1
            cases.append(dict(turn=turn,orthographic=ortho,exact=exact,fused_ms=statistics.median(timings[0]),numpy_ms=statistics.median(timings[1])))
        report['cases']=cases
    except BaseException:report['error']=traceback.format_exc()
    finally:
        if opened:cmds.undoInfo(closeChunk=True);cmds.undo()
        cmds.refresh(force=True)
        Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
