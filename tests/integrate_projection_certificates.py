from pathlib import Path
base=Path('cpp/retopo.cpp');candidate=Path('cpp/retopo_certificates_candidate.cpp')
s=base.read_text();c=candidate.read_text()
assert 'V projectCertified(' not in s
assert 'V projectCertified(' in c
assert 'std::vector<double> cachedSeparation;' in c
base.write_text(c)
p=Path('tests/create_projection_certificates.py');s=p.read_text().replace('s=p.read_text()', "s=p.read_text()\nif 'V projectCertified(' in s: raise SystemExit('Certificate solver is already integrated; use build_interactive.ps1.')");p.write_text(s)
Path('cpp/build_interactive.ps1').write_text('''param([string]$MayaVersion = "2027")
$ErrorActionPreference = 'Stop'
# Keep the ordinary UI backend reproducible with all adopted fast paths.
& "$PSScriptRoot/build_mesh_buffer.ps1" -MayaVersion $MayaVersion -NativeThreads 16 -BinaryName aru_retopo_mesh_buffer_certified.mll -NumericPipeline -ReuseScratch -IncrementalStencil -InputCache
if (-not $?) { throw 'Interactive mesh backend build failed.' }
''')
