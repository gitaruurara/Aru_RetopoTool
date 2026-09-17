"""Compare native visibility with the previous Maya ray implementation."""
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.display_native import Wire


def prepare_probe(mesh, repeats=3, detailed=False):
    """Exercise the real draw callback (including camera API) without rendering."""
    import os,time,types
    from Aru_RetopoTool import aru_retopo_draw_plugin as plugin
    if not cmds.pluginInfo('aru_retopo_draw_plugin.py',query=True,loaded=True):
        cmds.loadPlugin(plugin.__file__)
    overlay=cmds.createNode('aruRetopoOverlay')
    shape=(cmds.listRelatives(mesh,shapes=True,fullPath=True) or [mesh])[0]
    cmds.connectAttr(shape+'.outMesh',overlay+'.inputMesh')
    sel=om.MSelectionList();sel.add(overlay);path=sel.getDagPath(0)
    sel=om.MSelectionList();sel.add('perspShape');camera=sel.getDagPath(0)
    probe=types.SimpleNamespace(_draw_data={});times=[]
    mesh_fn=om.MFnMesh(om.MSelectionList().add(shape).getDagPath(0))
    original=mesh_fn.getPoints();camera_parent=om.MDagPath(camera);camera_parent.pop()
    camera_fn=om.MFnTransform(camera_parent);camera_matrix=camera_fn.transformation()
    try:
        for i in range(repeats):
            probe._draw_data.clear()
            start=time.perf_counter();data=plugin.Draw.prepareForDraw(probe,path,camera,None,None)
            times.append((time.perf_counter()-start)*1000)
            assert len(data.lines)>0,'Camera callback returned no visible edges'
        if not detailed:return times
        import cProfile,pstats,io
        report={'cold_ms':times}
        for mode in ('idle','orbit','deform'):
            samples=[];prof=cProfile.Profile()
            for i in range(repeats):
                if mode=='orbit':camera_fn.setTranslation(om.MVector(28+i,21,28),om.MSpace.kWorld)
                if mode=='deform':
                    changed=om.MPointArray(original);changed[0]=changed[0]+om.MVector(.001*(i+1),0,0);mesh_fn.setPoints(changed)
                start=time.perf_counter();prof.enable()
                data=plugin.Draw.prepareForDraw(probe,path,camera,None,None)
                prof.disable();samples.append((time.perf_counter()-start)*1000)
                assert len(data.lines)>0
            stream=io.StringIO();pstats.Stats(prof,stream=stream).sort_stats('cumtime').print_stats(10)
            report[mode+'_ms']=samples;report[mode+'_profile']=stream.getvalue()
        return report
    finally:
        mesh_fn.setPoints(original);camera_fn.setTransformation(camera_matrix)
        probe._draw_data.clear();cmds.delete(cmds.listRelatives(overlay,parent=True)[0])


def run():
    outer=cmds.polyCube(w=4,h=4,d=4)[0];inner=cmds.polyCube(w=1,h=1,d=1)[0]
    mesh=cmds.polyUnite(outer,inner,ch=False)[0]
    sel=om.MSelectionList();sel.add(mesh);path=sel.getDagPath(0);path.extendToShape();fn=om.MFnMesh(path)
    points=fn.getPoints();counts,ids=fn.getVertices();edges={};offset=0
    for fi,count in enumerate(counts):
        face=list(ids[offset:offset+count]);offset+=count
        for a,b in zip(face,face[1:]+face[:1]):edges.setdefault(tuple(sorted((a,b))),[]).append(fi)
    edges=sorted(edges.items());normals=[fn.getPolygonNormal(i) for i in range(fn.numPolygons)];_,tri=fn.getTriangles()
    wire=Wire([tuple(p)[:3] for p in points],list(tri),edges,[tuple(n) for n in normals])
    for orthographic in (False,True):
        eye=om.MPoint(9,7,11);direction=om.MVector(-9,-7,-11).normal();expected=[]
        for (a,b),faces in edges:
            for step in range(4):
                p=points[a]+(points[b]-points[a])*(step/4.);q=points[a]+(points[b]-points[a])*((step+1)/4.)
                mid=p+(q-p)*.5;to_eye=-direction if orthographic else eye-mid
                if not any(normals[f]*to_eye>0 for f in faces):continue
                distance=to_eye.length();ray=to_eye.normal();eps=max((points[a]-points[b]).length()*1e-4,1e-6)
                hit=fn.closestIntersection(om.MFloatPoint(mid+ray*eps),om.MFloatVector(ray),om.MSpace.kObject,1e10 if orthographic else distance-eps,False,tolerance=1e-7)
                if hit is None:expected.extend((tuple(p)[:3],tuple(q)[:3]))
        actual=wire.visible(tuple(eye)[:3],tuple(direction),orthographic)
        assert actual==expected,(len(actual),len(expected))
        compact=wire.visible(tuple(eye)[:3],tuple(direction),orthographic,compact=True)
        def length(lines):
            return sum((om.MPoint(*a)-om.MPoint(*b)).length() for a,b in zip(lines[::2],lines[1::2]))
        assert abs(length(compact)-length(actual))<1e-10
        for p in actual:
            point=om.MPoint(*p);covered=False
            for a,b in zip(compact[::2],compact[1::2]):
                a=om.MPoint(*a);v=om.MPoint(*b)-a;t=((point-a)*v)/(v*v)
                if -1e-10<=t<=1+1e-10 and (point-(a+v*t)).length()<1e-10:
                    covered=True;break
            assert covered,p
    moved=[(p.x*1.2+p.y*.15,p.y*.8,p.z*1.1) for p in points]
    fn.setPoints(om.MPointArray([om.MPoint(*p) for p in moved]))
    normals=[tuple(fn.getPolygonNormal(i)) for i in range(fn.numPolygons)]
    wire.update(moved,normals)
    rebuilt=Wire(moved,list(tri),edges,normals)
    try:
        for orthographic in (False,True):
            assert wire.visible((9,7,11),tuple(direction),orthographic)==rebuilt.visible((9,7,11),tuple(direction),orthographic)
    finally:rebuilt.close()
    wire.close()
    prepare_probe(mesh,1)
    cmds.delete(mesh)
    print('PASS native wire visibility matches Maya perspective/ortho rays with occluded inner mesh')
