"""Camera-only refresh stability on the isolated certificate GUI session."""
import os,json,time,math,hashlib,struct,traceback
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
ROOT=Path(__file__).resolve().parents[1]
def run():
    assert os.getpid()==38780
    report={'pid':os.getpid(),'scope':'camera-only synchronous redraw; not editing FPS','samples':[]}
    saved={name:cmds.getAttr('persp.'+name)[0] for name in ('translate','rotate')}
    try:
        from Aru_RetopoTool import viewport_session
        from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw,curve_net_edit as edit,curve_net_relax as relax
        viewport_session.ensure_display()
        assert draw._gpu_world_guides and cmds.getAttr('aruRetopoGuideShape1.xray')
        sel=om.MSelectionList();sel.add('aruRetopoNative1');dep=om.MFnDependencyNode(sel.getDependNode(0))
        plug=dep.findPlug('outPositions',False)
        def mesh_hash():
            values=list(om.MFnDoubleArrayData(plug.asMObject()).array())
            report['vertices']=len(values)//3
            return hashlib.sha256(struct.pack('='+str(len(values))+'d',*values)).hexdigest()
        before=mesh_hash()
        report['faces']=len(om.MFnIntArrayData(dep.findPlug('faceCounts',False).asMObject()).array())
        guide_before=cmds.getAttr('aruRetopoGuideShape1.outNetData')
        cn,_=relax._world_data('aruRetopoGuideShape1');point=cn.positions[645]
        screens=[]
        for i in range(48):
            angle=math.sin(i*math.pi/24)*35.;radians=math.radians(angle)
            x,y,z=saved['translate'];rx,ry,rz=saved['rotate']
            cmds.setAttr('persp.translate',x*math.cos(radians)+z*math.sin(radians),y,z*math.cos(radians)-x*math.sin(radians))
            cmds.setAttr('persp.rotate',rx,ry+angle,rz)
            start=time.perf_counter();cmds.refresh(force=True)
            report['samples'].append((time.perf_counter()-start)*1000)
            screens.append(edit._world_to_screen(point))
        assert mesh_hash()==before
        assert cmds.getAttr('aruRetopoGuideShape1.outNetData')==guide_before
        assert len({tuple(p) for p in screens if p is not None})>10,screens
        report['projected_screen_positions']=screens;report['geometry_unchanged']=True
    except BaseException:report['error']=traceback.format_exc()
    finally:
        for name,values in saved.items():cmds.setAttr('persp.'+name,*values)
        cmds.refresh(force=True)
        report['camera_restored']=all(tuple(cmds.getAttr('persp.'+name)[0])==tuple(values) for name,values in saved.items())
        (ROOT/'tests/projection_certificates_camera.json').write_text(json.dumps(report,indent=2))
