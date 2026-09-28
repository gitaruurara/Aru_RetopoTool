"""Run before Maya standalone initialization to reproduce GUI PYTHONPATH order."""
import sys,os,tempfile
from pathlib import Path
import maya
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
assert 'numpy' not in sys.modules, 'Need a fresh interpreter for dependency resolution'
with tempfile.TemporaryDirectory() as folder:
    package=Path(folder)/'numpy';package.mkdir()
    (package/'__init__.py').write_text("raise RuntimeError('wrong Python ABI shadow package')")
    sys.path.insert(0,folder)
    before=list(sys.path)
    import Aru_RetopoTool
    import numpy
    assert 'site-packages' in numpy.__file__ or '_deps' in numpy.__file__,numpy.__file__
    # Existing per-version bundled deps may be prepended by the tool.
    assert [p for p in sys.path if '_deps' not in p]==[p for p in before if '_deps' not in p]
    assert numpy.asarray([1.,2.]).sum()==3.
    print('PASS ABI-compatible NumPy with shadow package:',numpy.__file__)
