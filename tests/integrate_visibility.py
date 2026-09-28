from pathlib import Path
p=Path('editor/curvenet/curve_net_edit.py');s=p.read_text(encoding='utf-8')
a='''            from .maya_projector import surface_hits
            normals=[hit[1] for hit in surface_hits(mesh_fn,points)]'''
b='''            from .maya_projector import normals_array
            normals=normals_array(mesh_fn,points)'''
assert a in s;s=s.replace(a,b)
a='        return [_visible(p,n) for p,n in zip(points,normals)]'
b='''        try:
            from .maya_visibility import native_many
            result=native_many(mesh_fn,points,normals,eye,vdir,ortho,occlusion,lift,use_acceleration)
        except (ImportError,OSError,AttributeError,RuntimeError,ValueError):
            result=None
        if result is not None:return result
'''+a
assert s.count(a)==1;s=s.replace(a,b);p.write_text(s,encoding='utf-8')
s=Path('tests/visibility_accel.py').read_text()
s=s.replace("    print('VISIBILITY GRID", '''    from Aru_RetopoTool.editor.curvenet import maya_visibility as native
    from unittest.mock import patch
    assert native._LIB is not None
    # Exercise legacy fallback when the optional native DLL is unavailable.
    saved=native._LIB;native._LIB=None
    try:
        with patch.object(native.C,'PyDLL',side_effect=OSError('missing test DLL')):
            assert edit.make_visibility_test(mesh,view_info=views[0]).many(queries.tolist())==[edit.make_visibility_test(mesh,view_info=views[0])(p) for p in queries]
    finally:native._LIB=saved
    print('VISIBILITY RELEASE''')
Path('tests/visibility_release_cases.py').write_text(s)
s=Path('tests/run_visibility_accel.bat').read_text().replace('visibility_accel.py','visibility_release_cases.py')
Path('tests/run_visibility_release_cases.bat').write_text(s)
