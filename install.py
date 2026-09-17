"""Drag this file into Maya's viewport to install the downloaded repository."""
from pathlib import Path
import shutil


def install():
    from maya import cmds,mel
    source=Path(__file__).resolve().parent
    scripts=Path(cmds.internalVar(userScriptDir=True))
    target=scripts/'Aru_RetopoTool'
    if source!=target.resolve():
        shutil.copytree(source,target,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','*.obj','*.lib','*.exp'))
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
