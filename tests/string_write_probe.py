"""Isolate Maya command string marshaling from DG dirty propagation."""
import time,json
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides,maya_api as api
ROOT=Path(__file__).resolve().parents[1]

def run():
    guides.load();api.load_plugin()
    cmds.file(str(ROOT/'tests/current_curve_latency_scene.mb'),open=True,force=True)
    node=cmds.ls(type='retopoGuideNode')[0];attribute=node+'.netData'
    value=cmds.getAttr(attribute)
    plug=om.MSelectionList().add(attribute).getPlug(0)
    generator=cmds.ls(type='aruRetopoMesh')[0]
    output=om.MSelectionList().add(api.output_plug(generator)).getPlug(0)
    cmds.evaluationManager(mode='parallel')
    def evaluate():return om.MFnMesh(output.asMObject()).numVertices
    evaluate()
    decoded=json.loads(value)
    rows=[]
    for i in range(5):
        decoded['positions'][0][0]+=1e-5
        changed=json.dumps(decoded,separators=(',',':'))
        start=time.perf_counter();cmds.setAttr(attribute,changed,type='string');command=(time.perf_counter()-start)*1000
        evaluate()
        decoded['positions'][0][0]+=1e-5
        changed=json.dumps(decoded,separators=(',',':'))
        modifier=om.MDGModifier();start=time.perf_counter();modifier.newPlugValueString(plug,changed);modifier.doIt();direct=(time.perf_counter()-start)*1000
        assert plug.asString()==changed
        evaluate()
        modifier.undoIt();evaluate()
        rows.append({'cmds_ms':command,'modifier_ms':direct})
    result={'chars':len(value),'rows':rows}
    (ROOT/'tests/string_write_probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
