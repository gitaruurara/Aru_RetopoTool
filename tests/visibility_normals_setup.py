from pathlib import Path
p=Path('tests/visibility_candidate.py');s=p.read_text()
old="    source=source.replace(old,'''"
new="""    source=source.replace('from .maya_projector import surface_hits','from .maya_projector import normals_array')
    source=source.replace('normals=[hit[1] for hit in surface_hits(mesh_fn,points)]','normals=normals_array(mesh_fn,points)')
    source=source.replace(old,'''"""
assert old in s;s=s.replace(old,new);p.write_text(s)
p=Path('tests/gui_visibility.py');s=p.read_text().replace("    before=cmds.getAttr", "    call_start=visibility_candidate.native_calls\n    before=cmds.getAttr").replace("report['native_calls']=visibility_candidate.native_calls", "report['native_calls']=visibility_candidate.native_calls-call_start")
s=s.replace("'gui_visibility_reverse.json' if reverse else 'gui_visibility.json'", "'gui_visibility_normals_reverse.json' if reverse else 'gui_visibility_normals.json'");p.write_text(s)
