"""Filled patches survive boundary splits and inserted internal edges."""
from maya import cmds
from Aru_RetopoTool.tests.mesh_assertions import face_count
from Aru_RetopoTool import guides,maya_api as api,core,patch_context
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_context as context
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    mesh=cmds.polyPlane(w=10,h=10)[0];guide=guides.create(mesh)
    cn=RetopoGuideData()
    for p in [(-2,0,-2),(2,0,-2),(2,0,2),(-2,0,2),(4,0,-2),(4,0,2)]:cn.add_cv(p)
    for a,b in [(0,1),(1,2),(2,3),(3,0),(1,4),(4,5),(5,2)]:context._add_spline_to_cn(cn,mesh,a,b)
    acc=edit.RetopoGuideAccessor(guide);acc.write(cn)
    output,node=api.create(guide,mesh)
    loops=core.regions(cn.positions,cn.splines,lambda p:(0,1,0))
    key=next(core.patch_key(loop) for loop in loops if any(si==3 for side in loop for si,_ in side))
    patch_context.confirm(node,key)
    assert len(patch_context.selected(node))==1
    original=cmds.getAttr(guide+'.netData');original_keys=cmds.getAttr(node+'.selectedPatches')
    with api.undo_chunk('divide filled patch'):
        cn=acc.read()
        a=context._split_spline_at(cn,0,.5,mesh)
        b=context._split_spline_at(cn,2,.5,mesh)
        context._add_spline_to_cn(cn,mesh,a,b)
        edit._commit_net_data(guide,cn)
    assert len(patch_context.selected(node))==2
    assert '2 ' in cmds.getAttr(node+'.status'),cmds.getAttr(node+'.status')
    cmds.undo()
    assert cmds.getAttr(guide+'.netData')==original
    assert cmds.getAttr(node+'.selectedPatches')==original_keys
    cmds.redo();assert len(patch_context.selected(node))==2
    with api.undo_chunk('split boundary again'):
        cn=acc.read();context._split_spline_at(cn,0,.5,mesh);edit._commit_net_data(guide,cn)
    assert len(patch_context.selected(node))==2
    assert face_count(output)>0
    print('PASS filled child patches, adjacent unfilled patch preserved, boundary resplit, Undo/Redo')
    cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],mesh)
