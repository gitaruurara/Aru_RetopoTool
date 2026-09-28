"""Run in Maya/mayapy with Aru_RetopoTool available; no scene writes."""
from Aru_RetopoTool import core
from Aru_RetopoTool.regions_native import spline_aliases, canonical_keys
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.curve_net_context import _merge_two_eps


def run():
    cn = RetopoGuideData()
    for p in [(-1,0,0),(0,0,0),(0,1,0),(-1,1,0),
              (0,0,0),(1,0,0),(1,1,0),(0,1,0)]:
        cn.add_cv(list(p))
    for a,b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4)]:
        pa,pb=cn.positions[a],cn.positions[b]
        h=cn.add_cv([(2*x+y)/3 for x,y in zip(pa,pb)])
        j=cn.add_cv([(x+2*y)/3 for x,y in zip(pa,pb)])
        cn.add_spline(a,h,j,b)
    normal=lambda p:(0,0,1)
    old=core.regions(cn.positions,cn.splines,normal)
    keys={core.patch_key(loop) for loop in old}
    assert len(keys)==2
    # Legacy saved scene: duplicate boundaries remain after endpoint-only welding.
    cn.splines=[tuple({4:1,7:2}.get(v,v) if j in (0,3) else v
                      for j,v in enumerate(sp)) for sp in cn.splines]
    before=cn.to_json()
    aliases=spline_aliases(cn.positions,cn.splines)
    assert aliases[7]==(1,-1), aliases
    loops=core.regions(cn.positions,cn.splines,normal)
    assert len(loops)==2, loops
    plan=core.Plan(cn.positions,cn.splines,normal,2,selected=keys)
    assert plan.region_count==2 and len(plan.faces)==32
    assert len(plan.evaluate(cn.positions,cn.splines))==plan.count
    for key in keys:
        single=core.Plan(cn.positions,cn.splines,normal,2,selected={key})
        assert single.region_count==1 and len(single.faces)==16
    from Aru_RetopoTool.patch_transfer import transfer
    assert transfer(cn,cn,keys,normal)==canonical_keys(cn.positions,cn.splines,keys)
    assert cn.to_json()==before
    assert len(canonical_keys(cn.positions,cn.splines,keys))==2
    # Exercise the actual generator and fill/remove commands in an isolated scene.
    from maya import cmds
    from Aru_RetopoTool import guides, maya_api as api, patch_context
    from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit, curve_net_symmetry as sym
    from Aru_RetopoTool.tests.mesh_assertions import face_count
    axis=sym.get_axis()
    sym.set_axis('off')
    mesh=cmds.polyPlane(w=6,h=6,axis=(0,0,1))[0]
    guide=guides.create(mesh)
    edit.RetopoGuideAccessor(guide).write(cn)
    output,node=api.create(guide,mesh)
    try:
        ordered=sorted(canonical_keys(cn.positions,cn.splines,keys))
        patch_context.confirm(node,ordered[0])
        assert face_count(output)>0
        first=face_count(output)
        patch_context.confirm(node,ordered[1])
        assert face_count(output)==2*first
        patch_context.confirm(node,ordered[1],remove=True)
        assert face_count(output)==first
        cmds.undo();assert face_count(output)==2*first
        cmds.redo();assert face_count(output)==first
        print('PASS merged seam fill, remove, Undo/Redo through actual generator')
    finally:
        cmds.delete(output,node,cmds.listRelatives(guide,parent=True)[0],mesh)
        sym.set_axis(axis)
    # Same endpoints do not imply the same curve.
    h=cn.splines[7][1]
    cn.positions[h][0]+=.1
    assert spline_aliases(cn.positions,cn.splines)[7]==(7,1)
    # Normal, unmerged networks retain every original boundary ID.
    assert all(i==v[0] for i,v in spline_aliases(cn.positions,cn.splines).items())
    return {'merged_regions':2,'quads':len(plan.faces),'reverse_duplicate':True,
            'distinct_curves_preserved':True,'guide_unmodified':True}

if __name__=='__main__':
    print(run())
