"""Explicit GUI-only benchmark; launch in a new, empty Maya process."""
import os,json,time,statistics,traceback,cProfile,pstats,io
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import guides,maya_api as api,native_backend,gpu_preview
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.core import regions,patch_key,unit
ROOT=Path(__file__).parent
REPORT=ROOT/'gui_native_report.json'

def save(data):
    REPORT.write_text(json.dumps(data,indent=2),encoding='utf-8')

def schedule():
    save(dict(pid=os.getpid(),stage='GUI startup',time=time.time()))
    cmds.evalDeferred(run,lowestPriority=True)

def run():
    report=dict(pid=os.getpid(),stage='setup',time=time.time(),version=cmds.about(version=True))
    save(report)
    def checkpoint(stage):
        report.update(stage=stage,checkpoint_time=time.time());save(report)
    try:
        if cmds.file(q=True,sn=True) or cmds.ls(type='mesh'):
            raise RuntimeError('Benchmark requires a new empty Maya process')
        checkpoint('create reference')
        reference=cmds.polySphere(r=3,sx=64,sy=32,ch=False,name='nativeTestReference')[0]
        checkpoint('create guide')
        guide=guides.create(reference)
        checkpoint('build fixture')
        p,s=fixture()
        checkpoint('assign guide topology')
        cmds.setAttr(guide+'.netData',json.dumps(dict(positions=p,splines=s)),type='string')
        checkpoint('create generator')
        output,node=api.create(guide,reference,subdivisions=3,iterations=5)
        checkpoint('detect patches')
        keys=[patch_key(r) for r in regions(p,s,unit)]
        cmds.setAttr(node+'.selectedPatches',json.dumps(keys),type='string')
        checkpoint('connect native backend')
        native_backend.enable(node)
        report.update(guide=guide,node=node,output=output,patches=len(keys),faces=cmds.polyEvaluate(output,face=True))
        measure(guide,node,report)
    except BaseException:
        report.update(stage='error',error=traceback.format_exc());save(report)


def measure(guide,node,report=None):
    report=report or dict(pid=os.getpid(),version=cmds.about(version=True),guide=guide,node=node)
    try:
        panel='modelPanel4';cmds.lookThru(panel,'persp');cmds.select('nativeTestReference');cmds.viewFit('persp');cmds.select(clear=True)
        gpu_preview.enable(panel);cmds.refresh(force=True)
        from Aru_RetopoTool.editor.curvenet import curve_net_draw,gpu_guides
        def conditions():
            return dict(xray=cmds.getAttr(guide+'.xray'),world_guides=curve_net_draw._gpu_world_guides,
                        gpu_points=gpu_guides.GPU_CONTROLS,
                        renderer=cmds.modelEditor(panel,q=True,rendererOverrideName=True),
                        source=api.output_plug(node))
        report['conditions_start']=conditions()
        base=cmds.getAttr('persp.rotateY')
        for mode in ('idle','camera_rotation','deform'):
            report['stage']=mode;save(report);times=[]
            for i in range(24):
                t=time.perf_counter()
                if mode=='camera_rotation':cmds.setAttr('persp.rotateY',base+i*.1)
                if mode=='deform':cmds.setAttr(guide+'.controlPoints[0]',i*.0001,0,0,type='double3')
                cmds.refresh(force=True);times.append((time.perf_counter()-t)*1000)
            report[mode]=dict(samples_ms=times,median_ms=statistics.median(times[4:]),max_ms=max(times[4:]));save(report)
        profile=cProfile.Profile();profile.enable()
        for i in range(5):
            cmds.setAttr(guide+'.controlPoints[0]',i*.0002,0,0,type='double3');cmds.refresh(force=True)
        profile.disable();stream=io.StringIO();pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(45)
        (ROOT/'gui_native_profile.txt').write_text(stream.getvalue())
        report['conditions_end']=conditions()
        if report['conditions_end']!=report['conditions_start']:
            raise RuntimeError('Benchmark display/backend settings changed during measurement')
        report['status']=api.read_status(node)
        report['stage']='finished';save(report)
        # Leave the fixture available; MCP is owned by the regular Maya launcher.
    except BaseException:
        report.update(stage="error",error=traceback.format_exc());save(report)
        raise
    return report
