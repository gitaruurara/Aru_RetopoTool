import json,time,statistics,random,traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool.editor.curvenet import maya_screen as screen,curve_net_relax as relax

def run():
    root=Path(__file__).resolve().parents[1];report={};previous=screen._LIB
    camera='persp';shape='perspShape';rotation=cmds.getAttr(camera+'.rotateY');ortho=cmds.getAttr(shape+'.orthographic')
    try:
        libraries=[screen.load_library(root/'bin/2027'/('aru_retopo_maya_screen_'+n+'.dll')) for n in ('segments','hull')]
        cn,_=relax._world_data('aruRetopoGuideShape1');rng=random.Random(8917)
        positions=list(cn.positions);curves=list(cn.splines)
        for i in range(80):
            start=len(positions);positions.extend([[rng.uniform(-100,100) for _ in range(3)] for _ in range(4)]);curves.append(tuple(range(start,start+4)))
        count=0;times=[[],[]]
        for angle,orthographic in ((0,False),(13,False),(-21,True),(180,False)):
            cmds.setAttr(camera+'.rotateY',rotation+angle);cmds.setAttr(shape+'.orthographic',orthographic);cmds.refresh(force=True)
            screen._LIB=libraries[0]
            queries=[(rng.uniform(-100,3100),rng.uniform(-100,1700)) for _ in range(60)]
            queries+=screen.project(cn.positions[:40])
            for x,y in queries:
                results=[]
                for i,lib in enumerate(libraries):
                    screen._LIB=lib;start=time.perf_counter();result=list(screen.segment_candidates(positions,curves,x,y,144.));elapsed=(time.perf_counter()-start)*1000
                    results.append(result)
                    if angle==0:times[i].append(elapsed)
                assert results[0]==results[1],(angle,orthographic,x,y)
                count+=1
        report.update(exact_cases=count,before_ms=statistics.median(times[0]),after_ms=statistics.median(times[1]))
        cmds.setAttr(camera+'.rotateY',rotation);cmds.setAttr(shape+'.orthographic',ortho);cmds.refresh(force=True)
        from Aru_RetopoTool import viewport_session
        viewport_session.start('modelPanel4')
        from Aru_RetopoTool.tests import gui_point_drag
        for name,lib in zip(('baseline','hull'),libraries):
            viewport_session.ensure_display();cmds.refresh(force=True)
            screen._LIB=lib;gui_point_drag.run(numeric=True)
            result=json.loads((root/'tests/gui_point_drag.json').read_text());assert not result.get('error'),result.get('error')
            assert result['restored'];report[name]=result
        assert report['baseline']['final_hash']==report['hull']['final_hash']
    except BaseException:report['error']=traceback.format_exc()
    finally:
        screen._LIB=previous;cmds.setAttr(camera+'.rotateY',rotation);cmds.setAttr(shape+'.orthographic',ortho);cmds.refresh(force=True)
        (root/'tests/gui_screen_hull.json').write_text(json.dumps(report,indent=2))
    return report
