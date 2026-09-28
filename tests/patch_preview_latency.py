"""Patch hover cache and symmetry correspondence parity under real Maya."""
import json,types
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import patch_context as pc,symmetry_ops as so,maya_api as api
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,curve_net_symmetry as sym
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.curve_edit_features import fixture,network
ROOT=Path(__file__).resolve().parents[1]

def reference(name):
    module=types.ModuleType('Aru_RetopoTool._reference_'+name);module.__package__='Aru_RetopoTool'
    exec((ROOT/('tests/'+name+'_before_latency.py.txt')).read_text(encoding='utf-8'),module.__dict__)
    return module

def run():
    old=reference('patch_context');old_sym=reference('symmetry_ops')
    mesh,guide,node,_,_=fixture()
    p,s=network([(-4,0,-1),(-2,0,-1),(-2,0,1),(-4,0,1),(2,0,-1),(4,0,-1),(4,0,1),(2,0,1)],[(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4)])
    cn=RetopoGuideData.from_dict(dict(positions=p,splines=s));acc=edit.RetopoGuideAccessor(guide)
    acc.write(cn)
    actual=types.SimpleNamespace(node=node,cache=None,surface=None)
    expected=types.SimpleNamespace(node=node,cache=None,surface=None)
    from Aru_RetopoTool.maya_data import ReferenceMeshSnapshot
    actual._reference_snapshot=ReferenceMeshSnapshot(pc.om.MFnDependencyNode(pc._object(node)).findPlug("referenceMesh",False))
    def compare():
        import numpy as np
        old.PatchTool.rebuild(expected);pc.PatchTool.rebuild(actual)
        assert len(actual.candidates)==len(expected.candidates)==2
        for a,b in zip(actual.candidates,expected.candidates):
            assert a[0]==b[0]
            assert np.allclose(a[3],b[3],atol=1e-12,rtol=1e-12)
        assert actual.paired==expected.paired
    try:
        compare();first=[row[2] for row in actual.candidates];surface=actual.surface
        actual.cache=None;compare()
        assert all(row[2] is obj for row,obj in zip(actual.candidates,first))
        with api.undo_chunk('preview renumber CVs'):
            shifted=acc.read();shifted.positions.insert(0,[0.,0.,0.]);shifted.splines=[tuple(v+1 for v in sp) for sp in shifted.splines];acc.write(shifted)
        compare();assert all(row[2] is obj for row,obj in zip(actual.candidates,first))
        cmds.undo();compare()
        with api.undo_chunk('preview renumber splines'):
            shifted=acc.read();dummy=tuple(shifted.add_cv(p) for p in ((-4,0,-4),(-3.7,0,-4),(-3.3,0,-4),(-3,0,-4)));shifted.splines.insert(0,dummy);acc.write(shifted)
        compare();assert {id(row[2]) for row in actual.candidates}=={id(obj) for obj in first}
        cmds.undo();compare()
        with api.undo_chunk('preview changed handle'):
            changed=acc.read();changed.positions[s[0][1]][2]+=.2;acc.write(changed)
        compare()
        assert sum(row[2] is obj for row,obj in zip(actual.candidates,first))==1
        assert actual.surface is surface
        cmds.undo();compare()
        cmds.redo();compare()
        cmds.move(0,.3,0,mesh+'.vtx[0]',relative=True);compare()
        assert actual.surface is not surface
        cmds.setAttr(mesh+'.translate',.3,-.2,.1,type='double3')
        cmds.setAttr(mesh+'.rotate',13.,27.,-11.,type='double3')
        cmds.setAttr(mesh+'.scale',1.2,.8,1.4,type='double3')
        for space in ('object','world'):
            sym.set_space(space)
            for axis in ('x','y','z',''):
                sym.set_axis(axis);compare()
                for create in (False,True):
                    before=acc.read();a=RetopoGuideData.from_dict(before.to_dict());b=RetopoGuideData.from_dict(before.to_dict())
                    a.manual_handles.add(a.splines[0][1]);b.manual_handles.add(b.splines[0][1])
                    assert old_sym.mirrored_splines(a,mesh,range(len(a.splines)),create)==so.mirrored_splines(b,mesh,range(len(b.splines)),create)
                    assert a.to_dict()==b.to_dict()
        print('PASS patch preview geometry, changed-only reuse, reference invalidation, Undo/Redo, symmetry and manual handles')
    finally:
        actual._reference_snapshot.close()
        if actual.surface:actual.surface.close()
        if expected.surface:expected.surface.close()
