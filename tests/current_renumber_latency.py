"""Saved-scene local-edit transfer with every spline ID shifted once."""
import json,time
from pathlib import Path
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool import guides,maya_api as api,local_edit_transfer as transfer,local_fields,patch_transfer,core
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
ROOT=Path(__file__).resolve().parents[1]
def run():
    (ROOT/'tests/current_renumber_latency.json').write_text(json.dumps({'status':'running'}),encoding='utf-8')
    guides.load();api.load_plugin();cmds.file(str(ROOT/'tests/current_curve_latency_scene.mb'),open=True,force=True)
    guide=cmds.ls(type='retopoGuideNode')[0];node=cmds.ls(type='aruRetopoMesh')[0]
    fields=json.loads(cmds.getAttr(node+'.influenceField') or '{}');reductions=json.loads(cmds.getAttr(node+'.loopReductions') or '[]')
    new=RetopoGuideData.from_json(cmds.getAttr(guide+'.outNetData'));x=max(p[0] for p in new.positions)+10
    dummy=tuple(new.add_cv((x+i,0,0)) for i in range(4));new.splines.insert(0,dummy)
    # The snapshot contains obsolete saved paint keys. Seed 20 existing regions
    # with a nonuniform field so this actually measures transfer of useful data.
    context=patch_transfer.SceneTransfer(guide,new)
    loops=core.regions(context.before.positions,context.before.splines,context.normal)
    fields={}
    for loop in loops[:20]:
        field={};local_fields.paint(field,.3,.4,.73,.4);fields[core.patch_key(loop)]=field
    reductions=[]
    fields=json.loads(json.dumps(fields))
    cmds.setAttr(node+'.influenceField',json.dumps(fields),type='string')
    cmds.setAttr(node+'.loopReductions','[]',type='string')
    def shifted(key):return json.dumps([(i+1,d) for i,d in json.loads(key)],separators=(',',':'))
    expected={shifted(key):value for key,value in fields.items()}
    expected_reductions=[dict(row,patch=shifted(row['patch'])) for row in reductions]
    rows=[]
    for baseline in (True,False,False):
        t=time.perf_counter()
        if baseline:
            try:
                with patch.object(transfer,'parameter_boundary',side_effect=lambda *args:object()):updates=transfer.prepare(guide,new)
            except ValueError as exc:
                rows.append({'resampling_baseline':True,'error':str(exc),'ms':(time.perf_counter()-t)*1000});continue
        else:updates=transfer.prepare(guide,new)
        elapsed=(time.perf_counter()-t)*1000
        assert len(updates)==1
        assert set(updates[0][1])==set(expected), (len(updates[0][1]),len(expected))
        if not baseline:
            assert updates[0][1]==expected
            assert updates[0][2]==expected_reductions
        rows.append({'resampling_baseline':baseline,'ms':elapsed})
    result={'seeded_nonuniform_paint':True,'retained_fields':len(expected),'stale_fields_discarded_by_both':len(fields)-len(expected),'fields':len(fields),'reductions':len(reductions),'splines':len(new.splines),'rows':rows}
    (ROOT/'tests/current_renumber_latency.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS exact saved-scene local-edit transfer:',json.dumps(result))
