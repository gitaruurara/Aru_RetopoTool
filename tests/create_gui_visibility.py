from pathlib import Path
s=Path('tests/gui_draw_array.py').read_text().replace('draw_array_candidate','visibility_candidate').replace('gui_draw_array_reverse.json','gui_visibility_reverse.json').replace('gui_draw_array.json','gui_visibility.json')
s=s.replace("report['exact_outputs']=True", "report['exact_outputs']=True\n        report['native_calls']=visibility_candidate.native_calls\n        assert report['native_calls']>0")
Path('tests/gui_visibility.py').write_text(s)
