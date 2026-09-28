from pathlib import Path
s=Path('cpp/maya_projector.cpp').read_text(encoding='utf-8')
s+='\n'+Path('tests/visibility_kernel.inc').read_text(encoding='utf-8-sig')
Path('cpp/maya_visibility_candidate.cpp').write_text(s,encoding='utf-8')
s=Path('cpp/build_maya_projector.ps1').read_text().replace('$PSScriptRoot/maya_projector.cpp','$PSScriptRoot/maya_visibility_candidate.cpp')
Path('cpp/build_visibility_candidate.ps1').write_text(s)
