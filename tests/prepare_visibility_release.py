from pathlib import Path
header='''// Serial Maya ray queries. Python wrapper restricts calls to the main thread.
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MFnMesh.h>
#include <maya/MString.h>
#include <maya/MStatus.h>
#include <maya/MVector.h>
#include <cmath>
#include <limits>
#define API extern "C" __declspec(dllexport)
'''
s=Path('tests/visibility_kernel.inc').read_text(encoding='utf-8-sig')
s=s.replace('if(!path||count<0||', 'if(!path||count<0||count>std::numeric_limits<int>::max()/3||')
Path('cpp/maya_visibility.cpp').write_text(header+s,encoding='utf-8')
s=Path('cpp/build_maya_projector.ps1').read_text().replace('aru_retopo_maya_projector_tangents.dll','aru_retopo_maya_visibility.dll').replace('$PSScriptRoot/maya_projector.cpp','$PSScriptRoot/maya_visibility.cpp')
Path('cpp/build_maya_visibility.ps1').write_text(s)
s=Path('tests/visibility_candidate.py').read_text();start=s.index('def native_many(');end=s.index('\ndef install():',start)
body=s[start:end].replace('global _LIB,native_calls','global _LIB').replace('Path(__file__).resolve().parents[1]', 'Path(__file__).resolve().parents[2]').replace('aru_retopo_maya_visibility_candidate.dll','aru_retopo_maya_visibility.dll').replace('    native_calls+=1\n','')
body=body.replace('''        _LIB=C.PyDLL(str(Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/'aru_retopo_maya_visibility.dll'))''','''        try:
            _LIB=C.PyDLL(str(Path(__file__).resolve().parents[2]/'bin'/cmds.about(version=True)/'aru_retopo_maya_visibility.dll'))
        except OSError:return None''')
Path('editor/curvenet/maya_visibility.py').write_text('''"""Owned batch visibility output; scene ray calls stay on the main thread.

None asks the caller to use the original per-point Maya/Python implementation.
PyDLL retains the GIL, matching those existing main-thread API calls.
"""
import ctypes as C
from pathlib import Path
import threading
import numpy as np
from maya import cmds
_LIB=None

'''+body,encoding='utf-8')
