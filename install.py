"""Drag this file into Maya's viewport to install the downloaded repository."""
from pathlib import Path
import shutil
import sys
import subprocess


def ensure_numpy(target):
    deps=Path(target)/'_deps'/('py{}{}'.format(*sys.version_info[:2]))
    if deps.is_dir() and str(deps) not in sys.path:sys.path.insert(0,str(deps))
    try:
        import numpy
        return
    except ImportError:
        pass
    mayapy=Path(sys.executable).with_name('mayapy.exe' if sys.platform=='win32' else 'mayapy')
    version='numpy==1.26.4' if sys.version_info[:2]<(3,13) else 'numpy>=2.1,<3'
    subprocess.run([str(mayapy),'-m','pip','install','--only-binary=:all:','--target',str(deps),version],
                   check=True,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    if str(deps) not in sys.path:sys.path.insert(0,str(deps))
    import numpy


def install():
    from maya import cmds,mel
    source=Path(__file__).resolve().parent
    scripts=Path(cmds.internalVar(userScriptDir=True))
    target=scripts/'Aru_RetopoTool'
    if source!=target.resolve():
        shutil.copytree(source,target,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git','_deps','__pycache__','*.pyc','*.obj','*.lib','*.exp'))
    ensure_numpy(target)
    modules=Path(cmds.internalVar(userAppDir=True))/'modules'
    modules.mkdir(parents=True,exist_ok=True)
    (modules/'Aru_RetopoTool.mod').write_text(
        '+ Aru_RetopoTool 0.1.0 '+target.as_posix()+'\n'
        'plug-ins: .\nMAYA_PLUG_IN_PATH +:= editor/curvenet\nscripts: ..\n',encoding='utf-8')
    shelf='AruRetopo'
    if not cmds.shelfLayout(shelf,exists=True):
        cmds.shelfLayout(shelf,parent=mel.eval('$tmp=$gShelfTopLevel'))
    button='aruRetopoLaunchButton'
    if not cmds.shelfButton(button,exists=True):
        cmds.shelfButton(button,parent=shelf,label='Retopo',image='commandButton.png',
                         sourceType='python',command='import Aru_RetopoTool; Aru_RetopoTool.show()')
    import Aru_RetopoTool
    Aru_RetopoTool.show()
    cmds.inViewMessage(amg='Aru Retopo installed — AruRetopo shelf',pos='topCenter',fade=True)
    return str(target)


def onMayaDroppedPythonFile(*args):
    install()


if __name__=='__main__':install()
