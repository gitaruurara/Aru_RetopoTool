"""Renumbered regions preserve local UV edits; changed boundaries resample."""
import json
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import core,local_fields,local_edit_transfer as transfer,maya_api as api
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.tests.curve_edit_features import fixture

def run():
    mesh,guide,node,_,_=fixture();acc=edit.RetopoGuideAccessor(guide);before=acc.read()
    key=json.loads(cmds.getAttr(node+'.selectedPatches'))[0]
    field={};local_fields.paint(field,.25,.4,.73,.2)
    fields={key:field};reductions=[{'patch':key,'edge':[[.5,.25],[.5,.5]]}]
    cmds.setAttr(node+'.influenceField',json.dumps(fields),type='string')
    cmds.setAttr(node+'.loopReductions',json.dumps(reductions),type='string')
    new=acc.read();dummy=tuple(new.add_cv(p) for p in ((-4,0,-4),(-3.7,0,-4),(-3.3,0,-4),(-3,0,-4)))
    new.splines.insert(0,dummy)
    with patch.object(transfer,'Atlas',side_effect=AssertionError('Renumbering rebuilt an atlas')):
        rows=transfer.prepare(guide,new)
    assert len(rows)==1
    _,result_fields,result_reductions=rows[0];new_key=next(iter(result_fields))
    assert new_key!=key
    assert json.loads(json.dumps(result_fields[new_key]))==json.loads(json.dumps(field))
    assert result_reductions==[dict(reductions[0],patch=new_key)]
    original_atlas=transfer.Atlas
    changed=acc.read();changed.splines.insert(0,dummy);changed.positions=list(new.positions)
    changed.positions=[list(p) for p in changed.positions];changed.positions[changed.splines[1][1]][2]+=.15
    with patch.object(transfer,'Atlas',wraps=original_atlas) as atlas:
        assert transfer.prepare(guide,changed);assert atlas.call_count>=2
    rotated=acc.read();rotated.positions=list(new.positions);rotated.splines=[dummy]+rotated.splines[1:]+rotated.splines[:1]
    with patch.object(transfer,'Atlas',wraps=original_atlas) as atlas:
        assert transfer.prepare(guide,rotated);assert atlas.call_count>=2
    with api.undo_chunk('renumber painted patch'):acc.write(new)
    assert json.loads(cmds.getAttr(node+'.influenceField'))==json.loads(json.dumps(result_fields))
    assert json.loads(cmds.getAttr(node+'.loopReductions'))==result_reductions
    cmds.undo();assert json.loads(cmds.getAttr(node+'.influenceField'))==json.loads(json.dumps(fields))
    cmds.redo();assert json.loads(cmds.getAttr(node+'.loopReductions'))==result_reductions
    print('PASS exact paint/reduction preservation for renumbering, changed-shape and rotated-UV fallback, Undo/Redo')
