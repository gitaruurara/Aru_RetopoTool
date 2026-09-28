"""Initialize Maya before importing tests, isolating userSetup globals."""
import os,sys,traceback,importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import maya.standalone
maya.standalone.initialize(name='python')
status=0
try:
    importlib.import_module('Aru_RetopoTool.tests.'+sys.argv[1]).run()
except BaseException:
    traceback.print_exc();status=1
finally:
    from maya import cmds
    cmds.file(new=True,force=True)
    maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)