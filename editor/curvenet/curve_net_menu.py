# -*- coding: utf-8 -*-
"""
RetopoGuide Menu — dagMenu / 右クリックマーキングメニュー
=====================================================
retopoGuideNode の右クリックメニュー、draggerContext の作成、
``__main__`` への参照登録を行う。
"""

from __future__ import annotations

from functools import partial

import maya.OpenMaya as om
import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import (
    kPluginNodeName, _DRAGGER_CTX,
)
from Aru_RetopoTool.editor.curvenet.curve_net_edit import _find_shape_node


# ---------------------------------------------------------------------------
_CURVENET_MENU = "retopoGuideRMBMenu"

#: Shift + 右クリックの元コマンドの目印
_SHIFT_MM_MARK = "contextToolsMM "


def _install_dag_menu():
    """retopoGuideNode 用マーキングメニュー proc を MEL に登録する。

    Maya の MPxSurfaceShape 規約: ノードタイプ名 + "DagMenuProc" という
    名前の MEL グローバル proc を定義するだけでよい。
    右クリック時に Maya が自動的にこの proc を呼び出す。
    """
    mel_proc = r'''
global proc retopoGuideNodeDagMenuProc(string $parent, string $child) {
    setParent -m $parent;

    // Python 経由でメニュー項目を追加
    python("import __main__; __main__.__retopoGuideMenu__._build_rmb_menu('" + $parent + "', '" + $child + "')");
}
'''
    try:
        import maya.mel as mel
        mel.eval(mel_proc)
    except Exception:
        pass


def _build_rmb_menu(parent, obj):
    """Python 側: 右クリックメニュー項目を構築する。

    ここに置くのは「モードの切り替え」「設定」「ウィンドウを開く」だけ。
    カーブネットそのものを書き換える操作はツール設定
    (``curve_net_toolsettings``) の「カーブネットの編集」に分けてある。
    """
    # RMB 対象ノードを optionVar に記録
    shape = _find_shape_node(obj)
    if shape:
        cmds.optionVar(sv=("retopoGuideContext_node", shape))

    # --- コンポーネントモード (ラジアル) ---
    cmds.menuItem(
        label="ポイント",
        radialPosition="N",
        command=("import __main__; "
                 "__main__.__retopoGuideCtx__.enter_component_mode('ep')"),
    )
    cmds.menuItem(
        label="ハンドル",
        radialPosition="S",
        command=("import __main__; "
                 "__main__.__retopoGuideCtx__.enter_component_mode('handle')"),
    )
    cmds.menuItem(
        label="オブジェクトモード",
        radialPosition="W",
        command=("import __main__; "
                 "__main__.__retopoGuideCtx__.exit_component_mode()"),
    )
    cmds.menuItem(
        label="ポイント+ハンドル",
        radialPosition="E",
        command=("import __main__; "
                 "__main__.__retopoGuideCtx__.enter_component_mode('all')"),
    )

    # --- ツール / 設定 ---
    cmds.menuItem(divider=True, label="ツール")
    xray_on = True
    try:
        xray_on = bool(cmds.getAttr(shape + ".xray")) if shape else True
    except Exception:
        pass
    cmds.menuItem(
        label="X 線表示 (メッシュより前に描画)",
        checkBox=xray_on,
        annotation=("ジョイントの X 線表示と同じく、カーブ・ポイント・ハンドルを"
                    "メッシュに埋もれさせず常に手前に描きます"),
        command=("import Aru_RetopoTool.editor.curvenet.curve_net_menu as _m; "
                 "_m.toggle_xray()"),
    )
    cmds.menuItem(
        label="RetopoGuide コンテキスト",
        annotation="カーブネットを描く編集ツールに入ります",
        command=("import __main__; "
                 "__main__.__retopoGuideMenu__._enter_curvenet_context()"),
    )
    cmds.menuItem(
        label="ツール設定を開く (対称化・カーブネットの編集)",
        annotation=("編集コンテキストのツール設定を開きます。"
                    "対称化 (XYZ 面) の切り替えと、制御点の削除・ブレーク"
                    "などカーブネットを書き換える操作はここにまとめてあります。"),
        command=("import Aru_RetopoTool.editor.curvenet.curve_net_toolsettings "
                 "as _ts; _ts.show()"),
    )
    cmds.menuItem(
        label="カーブネットの編集 → Shift + 右クリック",
        annotation=("制御点の削除・ブレーク・タンジェントの整えなど、"
                    "カーブネットそのものを書き換える操作は "
                    "Shift を押しながら右クリックしても出せます "
                    "(ツール設定と同じ内容です)"),
        enable=False,
    )


def _active_curvenet_shape() -> str:
    """いま操作対象になっている retopoGuideNode を返す。無ければ空文字。

    コンポーネント (``transform1.vtx[0]`` など) が選択されている場合も、
    そのシェイプ名だけを返す。
    """
    for s in (cmds.ls(selection=True, long=True) or []):
        # コンポーネント部分を落としてノード名にする
        node = s.split(".")[0]
        if not cmds.objExists(node):
            continue
        if cmds.nodeType(node) == "retopoGuideNode":
            return node
        shapes = cmds.listRelatives(
            node, shapes=True, type="retopoGuideNode", fullPath=True) or []
        if shapes:
            return shapes[0]
    # 選択に出てこないケースの保険として、直近に右クリックしたノードも見る
    node = cmds.optionVar(q="retopoGuideContext_node") or ""
    if node and cmds.objExists(node) and cmds.nodeType(node) == "retopoGuideNode":
        # そのノードが選択に絡んでいるときだけ採用する。
        # 無条件に返すと、別のオブジェクトを触っているのに
        # カーブネットのメニューが出てしまう。
        tr = (cmds.listRelatives(node, parent=True, fullPath=True) or [""])[0]
        sel = set(cmds.ls(selection=True, long=True, objectsOnly=True) or [])
        if node in sel or (tr and tr in sel):
            return node
    return ""


def toggle_xray(node: str = "", state=None) -> bool:
    """カーブネットの X 線表示 (メッシュより前に描画) を切り替える。

    *state* が None なら反転。変更後の値を返す。
    """
    node = node or _active_curvenet_shape() or (
        cmds.optionVar(q="retopoGuideContext_node") or "")
    if not (node and cmds.objExists(node + ".xray")):
        return False
    cur = bool(cmds.getAttr(node + ".xray"))
    new = (not cur) if state is None else bool(state)
    cmds.setAttr(node + ".xray", new)
    return new


# ---------------------------------------------------------------------------
# Shift + 右クリック — カーブネットを直接書き換える操作
# ---------------------------------------------------------------------------
# Maya の Shift + 右クリックは通常の右クリックとは別の popupMenu が受けていて、
# retopoGuideNodeDagMenuProc は呼ばれない。そこで既存の popupMenu を探し、
# postMenuCommand が ``contextToolsMM ...`` になっているものを差し替える。
#
# postMenuCommand には **文字列ではなく Python の callable を渡す**。
# 文字列で渡すと MEL か Python かの解釈でつまずくが、callable なら無関係。
# 元のコマンドは partial の keywords に持たせておき、カーブネットが対象で
# ないときはそれをそのまま実行する (= Maya 標準のメニューが出る)。

def _build_shift_menu(menu) -> bool:
    """Shift + 右クリックのメニューを組み立てる。

    retopoGuideNode を触っていなければ False を返す
    (呼び出し側が Maya 標準のコマンドに流す)。
    """
    shape = _active_curvenet_shape()
    if not shape:
        return False
    cmds.optionVar(sv=("retopoGuideContext_node", shape))

    cmds.menuItem(
        parent=menu,
        label="制御点を削除",
        radialPosition="N",
        annotation=("選択した制御点とそこに繋がるカーブを消します。"
                    "カーブの途中の通過点を消した場合は、両隣のカーブを"
                    "1 本に繋ぎ直します。コンポーネントモードで点を選んで "
                    "Delete キーを押しても同じです。"
                    "対称化がオンなら反対側も一緒に消えます"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.delete_selected_eps()"),
    )
    cmds.menuItem(
        parent=menu,
        label="制御点をブレーク (分離)",
        radialPosition="W",
        annotation=("ウェルドの逆。選択した制御点に集まっているカーブを"
                    "別々の点に切り離します。切り離した直後は同じ位置に"
                    "重なっているので、そのまま引き離してください。"
                    "スキンウェイトは引き継がれます。"
                    "カーブの繋がりが変わるので Poisson デフォーマは"
                    "再バインドが必要です"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.break_selected_eps()"),
    )
    cmds.menuItem(
        parent=menu,
        label="タンジェントをフラット化",
        radialPosition="E",
        annotation=("ハンドルをメッシュの表面に沿うよう寝かせます "
                    "(法線方向の成分を抜く)。カーブがメッシュから"
                    "浮いてしまったときに使います。制御点を選ぶと"
                    "そこだけ、選択なしなら全体が対象です"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.flatten_tangents()"),
    )
    cmds.menuItem(
        parent=menu,
        label="CP をベイク",
        radialPosition="S",
        annotation=("スカルプトした差分 (controlPoints) を制御点の"
                    "位置そのものへ焼き込みます"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.bake_control_points()"),
    )

    cmds.menuItem(parent=menu, divider=True, label="カーブネットの編集")
    cmds.menuItem(
        parent=menu,
        label="左右反転して作成",
        annotation=("ツール設定の「対称化」で選んだ面でカーブネットを"
                    "反転します。やり方 (作り直す / 足すだけ) と"
                    "反転の向きはツール設定で選べます"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.mirror_curvenet()"),
    )
    cmds.menuItem(
        parent=menu,
        label="孤立 CV を掃除",
        annotation=("制御点の削除やマージで参照が外れたまま残っている CV を "
                    "削除してインデックスを詰める "
                    "(スキンウェイトは引き継がれます)"),
        command=("import __main__; "
                 "__main__.__retopoGuidePlugin__.cleanup_orphan_cvs()"),
    )
    cmds.menuItem(
        parent=menu,
        label="ツール設定を開く (対称化など)",
        annotation=("同じ操作はツール設定の「カーブネットの編集」"
                    "からも実行できます"),
        command=("import Aru_RetopoTool.editor.curvenet.curve_net_toolsettings "
                 "as _ts; _ts.show()"),
    )
    return True


def _shift_mm_callback(menu, *args, **kwargs):
    """差し替えた postMenuCommand の本体。

    Maya はクエリ時などに bool を渡して呼ぶことがあるので、
    そのときは何もせずに戻る。
    """
    if len(args) > 1 and isinstance(args[1], bool):
        return menu

    menu_cmd = kwargs.get("cmd")
    if menu_cmd is None:
        return menu

    # 先に中身を空にする
    try:
        cmds.popupMenu(menu, e=True, deleteAllItems=True)
    except Exception:
        return menu

    built = False
    try:
        built = _build_shift_menu(menu)
    except Exception:
        import traceback
        traceback.print_exc()

    if not built and menu_cmd:
        # カーブネットが対象でなければ Maya 標準へ流す
        import maya.mel as mel
        try:
            mel.eval(menu_cmd)
        except Exception:
            pass
    return menu


def install_shift_menu() -> int:
    # Retopo uses its own shape RMB and settings; leave global Maya/CurveNet
    # popup callbacks untouched when both editors are loaded.
    return 0


def uninstall_shift_menu() -> int:
    return 0


def _enter_curvenet_context(*_args):
    """RetopoGuide 編集コンテキストを有効にする (ラッパー)。"""
    ctx = _get_or_create_dragger_ctx()
    # パネルは後から作られることがあるので、ここでも差し込みを試みる
    try:
        install_shift_menu()
    except Exception:
        pass
    cmds.setToolTo(ctx)


def _register_in_main() -> None:
    """``__main__`` に編集モジュール・メニューモジュール・コンテキストインスタンスを格納する。"""
    import __main__
    from Aru_RetopoTool.editor.curvenet import curve_net_edit
    from Aru_RetopoTool.editor.curvenet import curve_net_menu
    from Aru_RetopoTool.editor.curvenet.curve_net_context import RetopoGuideContext
    from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx
    __main__.__retopoGuidePlugin__ = curve_net_edit
    __main__.__retopoGuideMenu__ = curve_net_menu
    if not hasattr(__main__, '__retopoGuideCtx__') or __main__.__retopoGuideCtx__ is None:
        __main__.__retopoGuideCtx__ = RetopoGuideContext(_ctx)


def _get_or_create_dragger_ctx() -> str:
    """draggerContext を取得または作成して名前を返す。

    コールバック文字列を常に最新に保つため、既存コンテキストがあれば
    一度削除してから再作成する。
    """
    # コンテキストを再作成する前に __main__ 参照を必ず更新
    _register_in_main()
    try:
        if cmds.contextInfo(_DRAGGER_CTX, exists=True):
            cmds.deleteUI(_DRAGGER_CTX)
    except Exception:
        pass
    _cb = "import __main__ as _m; _m.__retopoGuideCtx__."
    cmds.draggerContext(
        _DRAGGER_CTX,
        pressCommand=   _cb + "press()",
        dragCommand=    _cb + "drag()",
        releaseCommand= _cb + "release()",
        initialize=     _cb + "enter()",
        finalize=       _cb + "exit()",
        space="screen",
        cursor="crossHair",
    )
    # ツール設定 (Tool Settings) に自前のシートを出せるようにする
    try:
        from Aru_RetopoTool.editor.curvenet import curve_net_toolsettings
        curve_net_toolsettings.install_hook()
    except Exception:
        pass
    return _DRAGGER_CTX
