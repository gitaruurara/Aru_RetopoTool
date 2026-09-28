from pathlib import Path
s=Path('tests/visibility_accel.py').read_text()
s=s.replace('status=1','from Aru_RetopoTool.tests import visibility_candidate as candidate\nrestore=candidate.install()\nstatus=1')
s=s.replace("    print('VISIBILITY GRID", "    assert candidate.native_calls>=9,candidate.native_calls\n    print('VISIBILITY NATIVE")
s=s.replace('    edit._invalidate_mesh_accel();','    restore()\n    edit._invalidate_mesh_accel();')
Path('tests/visibility_candidate_cases.py').write_text(s)
s=Path('tests/run_visibility_accel.bat').read_text().replace('visibility_accel.py','visibility_candidate_cases.py')
Path('tests/run_visibility_candidate_cases.bat').write_text(s)
