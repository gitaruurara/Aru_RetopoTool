"""retopoGuideNode の Attribute Editor テンプレート登録。

テンプレート本体は ``mel/AEretopoGuideNodeTemplate.mel``。AE は対話的に定義した
グローバル proc を拾わないので、ファイルのあるディレクトリを
MAYA_SCRIPT_PATH に足して ``rehash`` する (プラグインロード時)。
"""
from __future__ import annotations

import os

import maya.cmds as cmds
import maya.mel as mel

_MEL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "mel"))


def install() -> None:
    if not os.path.isdir(_MEL_DIR):
        return
    paths = os.environ.get("MAYA_SCRIPT_PATH", "").split(os.pathsep)
    if _MEL_DIR not in paths:
        os.environ["MAYA_SCRIPT_PATH"] = os.pathsep.join(
            p for p in [_MEL_DIR] + paths if p)
        try:
            mel.eval('putenv "MAYA_SCRIPT_PATH" "%s"'
                     % os.environ["MAYA_SCRIPT_PATH"].replace("\\", "/"))
        except Exception:
            pass
    try:
        mel.eval("rehash")
    except Exception:
        pass
    if cmds.about(batch=True):
        return
    try:
        mel.eval('source "%s"' % os.path.join(
            _MEL_DIR, "AEretopoGuideNodeTemplate.mel").replace("\\", "/"))
        # 既に AE がこのノード型を表示済みなら作り直させる
        mel.eval("refreshEditorTemplates")
    except Exception:
        pass
