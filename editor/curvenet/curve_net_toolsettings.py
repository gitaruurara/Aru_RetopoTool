# -*- coding: utf-8 -*-
"""
RetopoGuide Tool Settings -- 編集コンテキストのツール設定 (Tool Settings)

Maya のツール設定は、現在のコンテキストのクラス名 (``contextInfo -c``) から
``<クラス名>Properties`` / ``<クラス名>Values`` という MEL proc を呼び出して
中身を作る。draggerContext のクラス名は常に ``defaultTool`` で変更できないため、
``defaultToolValues`` を差し替えて「自分のコンテキストのときだけ自前のシートを
出す」ようにする。

差し替え後も他のコンテキストでは元と同じ挙動 (defaultTool シートを選択) を
保つので、他ツールのツール設定は壊れない。
"""

from maya import cmds
import maya.mel as mel

from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _DRAGGER_CTX

# ツール設定内に作る自前シートのレイアウト名
_SHEET = "retopoGuideProfileRigToolSheet"

# 差し替え済みかどうか
_HOOK_INSTALLED = False

_AXIS_LABELS  = [lbl for lbl, _ in _sym.AXIS_CHOICES]
_AXIS_VALUES  = [val for _, val in _sym.AXIS_CHOICES]
_SPACE_LABELS = [lbl for lbl, _ in _sym.SPACE_CHOICES]
_SPACE_VALUES = [val for _, val in _sym.SPACE_CHOICES]

_AXIS_MENU  = "retopoGuideSymAxisMenu"
_SPACE_MENU = "retopoGuideSymSpaceMenu"
_MIRROR_MODE_MENU = "retopoGuideMirrorModeMenu"
_MIRROR_DIR_MENU  = "retopoGuideMirrorDirMenu"
_MIRROR_BUTTON    = "retopoGuideMirrorButton"

_MMODE_LABELS = [lbl for lbl, _ in _sym.MIRROR_MODE_CHOICES]
_MMODE_VALUES = [val for _, val in _sym.MIRROR_MODE_CHOICES]
_MDIR_LABELS  = [lbl for lbl, _ in _sym.MIRROR_DIR_CHOICES]
_MDIR_VALUES  = [val for _, val in _sym.MIRROR_DIR_CHOICES]

#: 「カーブネットの編集」に並べるボタン
#: (ラベル, curve_net_edit の関数名, 説明)
_EDIT_ACTIONS = [
    (u"制御点を削除", "delete_selected_eps",
     u"選択した制御点とそこに繋がるカーブを消します。\n"
     u"カーブの途中の通過点を消した場合は、両隣のカーブを 1 本に繋ぎ直します。\n"
     u"コンポーネントモードで点を選んで Delete キーを押しても同じです。\n"
     u"対称化がオンなら反対側も一緒に消えます。"),
    (u"制御点をブレーク (分離)", "break_selected_eps",
     u"ウェルドの逆。選択した制御点に集まっているカーブを別々の点に\n"
     u"切り離します。切り離した直後は同じ位置に重なっているので、\n"
     u"そのまま引き離してください。スキンウェイトは引き継がれます。\n"
     u"カーブの繋がりが変わるので Poisson デフォーマは再バインドが必要です。"),
    (u"タンジェントをフラット化", "flatten_tangents",
     u"ハンドルをメッシュの表面に沿うよう寝かせます (法線方向の成分を抜く)。\n"
     u"カーブがメッシュから浮いてしまったときに使います。\n"
     u"制御点を選ぶとそこだけ、選択なしなら全体が対象です。"),
    (u"手動ハンドルを自動に戻す", "reset_manual_handles",
     u"編集コンテキストで中ボタンドラッグしたハンドル (オレンジ表示) は\n"
     u"自動フィットで上書きされません。この固定を外して測地線に沿う\n"
     u"自動フィットを掛け直します。選択した点だけ、選択なしなら全体が対象です。"),
    (u"CP をベイク", "bake_control_points",
     u"スカルプトした差分 (controlPoints) を制御点の位置そのものへ\n"
     u"焼き込みます。"),
    (u"孤立 CV を掃除", "cleanup_orphan_cvs",
     u"制御点の削除やマージで参照が外れたまま残っている CV を削除して\n"
     u"インデックスを詰めます (スキンウェイトは引き継がれます)。"),
]

#: 対象ノードを表示するテキスト
_TARGET_TEXT = "retopoGuideToolSheetTarget"

#: 選択変更を拾う scriptJob の id
_SEL_JOB = [-1]


# ---------------------------------------------------------------------------
# コールバック
# ---------------------------------------------------------------------------

def _on_axis_changed(*_a):
    try:
        idx = cmds.optionMenuGrp(_AXIS_MENU, q=True, select=True) - 1
        _sym.set_axis(_AXIS_VALUES[idx])
    except Exception:
        pass
    _sync_enable()


def _on_space_changed(*_a):
    try:
        idx = cmds.optionMenuGrp(_SPACE_MENU, q=True, select=True) - 1
        _sym.set_space(_SPACE_VALUES[idx])
    except Exception:
        pass


def _sync_enable():
    """対称化オフのときは空間プルダウンと反転作成を無効にする。"""
    on = _sym.is_enabled()
    try:
        cmds.optionMenuGrp(_SPACE_MENU, e=True, enable=on)
    except Exception:
        pass
    for name, fn in ((_MIRROR_MODE_MENU, cmds.optionMenuGrp),
                     (_MIRROR_DIR_MENU, cmds.optionMenuGrp),
                     (_MIRROR_BUTTON, cmds.button)):
        try:
            fn(name, e=True, enable=on)
        except Exception:
            pass


def _on_mirror_mode_changed(*_a):
    try:
        idx = cmds.optionMenuGrp(_MIRROR_MODE_MENU, q=True, select=True) - 1
        _sym.set_mirror_mode(_MMODE_VALUES[idx])
    except Exception:
        pass


def _on_mirror_dir_changed(*_a):
    try:
        idx = cmds.optionMenuGrp(_MIRROR_DIR_MENU, q=True, select=True) - 1
        _sym.set_mirror_direction(_MDIR_VALUES[idx])
    except Exception:
        pass


def _run_mirror(*_a):
    """左右反転作成を実行する。"""
    from Aru_RetopoTool.editor.curvenet import curve_net_edit as _edit
    try:
        _edit.mirror_curvenet()
    finally:
        refresh_sheet()


def _run_edit_action(func_name: str) -> None:
    """カーブネットの編集コマンドを実行して、対象表示を更新する。"""
    from Aru_RetopoTool.editor.curvenet import curve_net_edit as _edit
    try:
        getattr(_edit, func_name)()
    finally:
        refresh_sheet()


def _target_label() -> str:
    from Aru_RetopoTool.editor.curvenet import curve_net_menu as _menu
    shape = ""
    try:
        shape = _menu._active_curvenet_shape()
    except Exception:
        pass
    if not shape:
        return u"対象: (カーブネットが選択されていません)"
    return u"対象: " + shape.split("|")[-1]


def _install_sel_job() -> None:
    """選択が変わったら対象表示を更新する scriptJob を仕込む。

    シートが消えたら自分で外れるように ``parent`` を指定する。
    """
    if _SEL_JOB[0] >= 0 and cmds.scriptJob(exists=_SEL_JOB[0]):
        return
    try:
        parent = mel.eval("toolPropertyWindow -q -location")
        _SEL_JOB[0] = cmds.scriptJob(
            event=["SelectionChanged", _on_selection_changed],
            parent=parent + "|" + _SHEET,
        )
    except Exception:
        _SEL_JOB[0] = -1


def _on_selection_changed(*_a) -> None:
    try:
        if cmds.text(_TARGET_TEXT, exists=True):
            cmds.text(_TARGET_TEXT, e=True, label=_target_label())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# シートの構築 / 更新
# ---------------------------------------------------------------------------

def build_sheet() -> str:
    """ツール設定内に自前シートを作る (既にあれば再利用)。"""
    parent = mel.eval("toolPropertyWindow -q -location")
    full = parent + "|" + _SHEET
    if cmds.columnLayout(full, exists=True):
        refresh_sheet()
        return full

    cmds.setParent(parent)
    mel.eval("setUITemplate -pushTemplate OptionsTemplate")
    cmds.columnLayout(_SHEET, adjustableColumn=True)

    cmds.frameLayout(label=u"カーブネット編集の設定",
                     collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.separator(style="none")

    cmds.optionMenuGrp(_AXIS_MENU, label=u"対称化",
                       changeCommand=_on_axis_changed)
    for lbl in _AXIS_LABELS:
        cmds.menuItem(label=lbl)

    cmds.optionMenuGrp(_SPACE_MENU, label=u"対称空間",
                       changeCommand=_on_space_changed)
    for lbl in _SPACE_LABELS:
        cmds.menuItem(label=lbl)

    cmds.separator(style="none")
    cmds.text(align="left", label=(
        u"対称化を有効にすると、点とカーブを作ったときに\n"
        u"反対側にも同じものを作るわ。"))
    cmds.separator(style="none")

    cmds.setParent("..")
    cmds.setParent("..")

    # --- カーブネットの編集 ---
    cmds.frameLayout(label=u"カーブネットの編集",
                     collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.separator(style="none")

    cmds.text(_TARGET_TEXT, align="left", label=_target_label())
    cmds.separator(style="none")

    for label, func_name, ann in _EDIT_ACTIONS:
        cmds.button(
            label=label, annotation=ann, align="center",
            command=("import Aru_RetopoTool.editor.curvenet."
                     "curve_net_toolsettings as _ts; "
                     "_ts._run_edit_action('{}')".format(func_name)),
        )

    cmds.separator(style="none")
    cmds.text(align="left", label=(
        u"どれもコンポーネントモードで選んだ制御点が対象よ。\n"
        u"選択なしのときは「タンジェントをフラット化」だけ\n"
        u"カーブネット全体にかかるわ。"))
    cmds.separator(style="none")

    cmds.setParent("..")
    cmds.setParent("..")

    # --- 左右反転作成 ---
    cmds.frameLayout(label=u"左右反転して作成",
                     collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.separator(style="none")

    cmds.optionMenuGrp(_MIRROR_MODE_MENU, label=u"やり方",
                       changeCommand=_on_mirror_mode_changed)
    for lbl in _MMODE_LABELS:
        cmds.menuItem(label=lbl)

    cmds.optionMenuGrp(_MIRROR_DIR_MENU, label=u"反転の向き",
                       changeCommand=_on_mirror_dir_changed)
    for lbl in _MDIR_LABELS:
        cmds.menuItem(label=lbl)

    cmds.separator(style="none")
    cmds.button(
        _MIRROR_BUTTON, label=u"左右反転して作成", align="center",
        annotation=(u"上の「対称化」で選んだ面でカーブネットを反転します。\n"
                    u"対称面を跨いでいるカーブは面の上で 2 本に切ってから\n"
                    u"処理するので、はみ出したカーブがあっても大丈夫です。"),
        command=("import Aru_RetopoTool.editor.curvenet."
                 "curve_net_toolsettings as _ts; _ts._run_mirror()"),
    )
    cmds.separator(style="none")
    cmds.text(align="left", label=(
        u"「作り直す」は反転先の側を一度消してから作るわ。\n"
        u"「足すだけ」は今あるものを残して、反対側に無いぶん\n"
        u"だけ足すの。対称面の上の点は 1 個のままよ。"))
    cmds.separator(style="none")

    cmds.setParent("..")
    cmds.setParent("..")

    cmds.setParent("..")
    mel.eval("setUITemplate -popTemplate")

    refresh_sheet()
    return full


def refresh_sheet() -> None:
    """optionVar の現在値をプルダウンに反映する。"""
    try:
        axis = _sym.get_axis()
        cmds.optionMenuGrp(_AXIS_MENU, e=True,
                           select=_AXIS_VALUES.index(axis) + 1)
    except Exception:
        pass
    try:
        space = _sym.get_space()
        cmds.optionMenuGrp(_SPACE_MENU, e=True,
                           select=_SPACE_VALUES.index(space) + 1)
    except Exception:
        pass
    try:
        cmds.text(_TARGET_TEXT, e=True, label=_target_label())
    except Exception:
        pass
    try:
        cmds.optionMenuGrp(_MIRROR_MODE_MENU, e=True,
                           select=_MMODE_VALUES.index(
                               _sym.get_mirror_mode()) + 1)
    except Exception:
        pass
    try:
        cmds.optionMenuGrp(_MIRROR_DIR_MENU, e=True,
                           select=_MDIR_VALUES.index(
                               _sym.get_mirror_direction()) + 1)
    except Exception:
        pass
    _install_sel_job()
    _sync_enable()


# ---------------------------------------------------------------------------
# defaultToolValues の差し替え
# ---------------------------------------------------------------------------

# 差し替え後の defaultToolValues。
# 自分のコンテキスト以外では Maya 標準の defaultToolValues.mel と同じ処理をする。
_HOOK_MEL = u'''
global proc defaultToolValues(string $toolName) {{
    if ($toolName == "{ctx}") {{
        python("import Aru_RetopoTool.editor.curvenet.curve_net_toolsettings as _ts; _ts.build_sheet()");
        toolPropertySetCommon $toolName "" "";
        toolPropertySelect "{sheet}";
        return;
    }}

    string $parent = (`toolPropertyWindow -q -location` + "|defaultTool");
    setParent $parent;

    string $xpmName = "";
    string $currentTool = `currentCtx`;
    if (`superCtx -exists $currentTool`) {{
        if (`toolCollection -exists toolCluster`) {{
            string $currentButton = `toolCollection -query -select toolCluster`;
            if (`toolButton -exists $currentButton`) {{
                $xpmName = `toolButton -query -image1 $currentButton`;
            }}
        }}
    }} else if (`contextInfo -q -exists $currentTool`) {{
        $xpmName = `contextInfo -q -i1 $currentTool`;
    }}

    toolPropertySetCommon $toolName $xpmName "";
    toolPropertySelect "defaultTool";
}}
'''


def install_hook(force: bool = False) -> bool:
    """defaultToolValues を差し替える。既に差し替え済みなら何もしない。"""
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED and not force:
        return False
    try:
        # 先に本物を読み込ませてから上書きする。
        # 後から autoload されて上書きが取り消されるのを防ぐため。
        mel.eval("source defaultToolValues")
    except Exception:
        pass
    try:
        mel.eval(_HOOK_MEL.format(ctx=_DRAGGER_CTX, sheet=_SHEET))
    except Exception:
        return False
    _HOOK_INSTALLED = True
    return True


def show() -> None:
    """ツール設定を開く。"""
    install_hook()
    mel.eval("toolPropertyWindow")
