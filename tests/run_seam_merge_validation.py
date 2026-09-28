import sys,os,traceback,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import maya.standalone
maya.standalone.initialize(name='python')
code=0
try:
    from Aru_RetopoTool.tests.seam_merge_patches import run
    print(run())
    from Aru_RetopoTool.tests import test_regions,test_core
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_regions,test_core))
    assert unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    from Aru_RetopoTool.tests.patch_transfer import run as transfer
    transfer()
except Exception:
    traceback.print_exc();code=1
finally:
    from maya import cmds
    cmds.file(new=True,force=True)
    maya.standalone.uninitialize()
sys.stdout.flush();sys.stderr.flush();os._exit(code)
