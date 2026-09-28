"""Compare scalar/batched hit results in the current camera, without editing."""
import json,time,statistics,traceback
from pathlib import Path
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_relax as relax,curve_net_edit as edit

def run():
    report={}
    try:
        cn,_=relax._world_data('aruRetopoGuideShape1')
        mesh=edit.RetopoGuideAccessor('aruRetopoGuideShape1').mesh_name
        eps=sorted(cn.endpoint_indices())
        screens=edit._world_to_screen_many([cn.positions[i] for i in eps])
        queries=[(1546+2*i,1145) for i in range(8)]
        queries += [(p[0]+7,p[1]+4) for p in screens[::max(1,len(screens)//20)] if p]
        timings=[[],[]];exact=0
        for index,(x,y) in enumerate(queries):
            excluded={eps[index%len(eps)]} if index%2 else set()
            results=[]
            for mode,fn in enumerate((context._find_spline_under_screen_scalar,context._find_spline_under_screen)):
                start=time.perf_counter();results.append(fn(cn,x,y,exclude_eps=excluded,mesh_name=mesh))
                timings[mode].append((time.perf_counter()-start)*1000)
            assert results[0]==results[1],(x,y,results)
            exact+=1
        report={'exact_cases':exact,'scalar_median_ms':statistics.median(timings[0]),'batched_median_ms':statistics.median(timings[1])}
    except BaseException:report['error']=traceback.format_exc()
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
