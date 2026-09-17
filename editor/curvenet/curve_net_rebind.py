"""
RetopoGuide 自動リバインド
======================
カーブネット (``netData`` = レスト形状) が変わったら、繋がっている
profileCurveDeformer のバインドデータをその場で作り直す。デフォーマノード・
接続・envelope・falloff・ピン重み・カーブネット側の skinCluster は残る。

バインドは netData とレストメッシュ (Orig) の純関数なので、Undo/Redo で
netData が戻ればここも追従して作り直す (attributeChange scriptJob)。

ドラッグ中はマウス移動ごとに netData が書かれるので、コンテキストが
:func:`suspend` / :func:`resume` で囲んでリリース時にまとめて 1 回だけ回す。
"""
from __future__ import annotations

import traceback

import maya.cmds as cmds
import maya.OpenMaya as om

_OPTVAR = "retopoGuideAutoRebind"

_pending: set[str] = set()
_scheduled = False
_suspend_depth = 0
_watch_jobs: dict[str, int] = {}
_rebinding = False
#: 編集中に黙らせたデフォーマと元の envelope
_muted: dict[str, float] = {}
#: 編集ツール (draggerContext) に入っている間はリバインドを保留する。
#: レストポーズではデフォーマの出力は恒等なので、編集のたびに作り直すのは無駄。
#: ツールを抵けた時 / タイムが動いた時 / 手動 でまとめて 1 回だけ回す。
_tool_active = False
_time_job = None


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    if not cmds.optionVar(exists=_OPTVAR):
        return True
    return bool(cmds.optionVar(q=_OPTVAR))


def set_enabled(state: bool) -> None:
    cmds.optionVar(iv=(_OPTVAR, 1 if state else 0))
    if state:
        for n in cmds.ls(type="retopoGuideNode", noIntermediate=True) or []:
            ensure_watch(n)


def suspend(node: str = "") -> None:
    """ドラッグ開始。リリースまでリバインドを止める。

    その間は古いバインドで新しいカーブを評価してメッシュが引っ張られるので、
    繋がるデフォーマの envelope を 0 にしてレスト形状のまま編集させる。
    """
    global _suspend_depth
    _suspend_depth += 1
    node = node or (cmds.optionVar(q="retopoGuideContext_node") or "")
    if node and cmds.objExists(node):
        mute_deformers(node)


def resume() -> None:
    """ドラッグ終了。溢まっていた分をまとめて流す (ツール中は保留のまま)。"""
    global _suspend_depth
    _suspend_depth = max(0, _suspend_depth - 1)
    if _suspend_depth > 0:
        return
    if _pending:
        if _tool_active:
            _show_pending_hint()
        else:
            _schedule()          # リバインド後に flush() が envelope を戻す
    else:
        unmute_deformers()


def tool_entered(node: str = "") -> None:
    """編集ツールに入った。ツールを抵けるまでリバインドを保留する。"""
    global _tool_active
    _tool_active = True
    _ensure_time_watch()


def tool_exited() -> None:
    """編集ツールを抵けた。保留分をまとめてリバインドする。"""
    global _tool_active
    _tool_active = False
    if _pending:
        _schedule()
    elif _suspend_depth == 0:
        unmute_deformers()


def _ensure_time_watch() -> None:
    """ツール中にタイムスライダを動かしたら (ポーズを見たい合図) 保留分を流す。"""
    global _time_job
    if _time_job is not None and cmds.scriptJob(exists=_time_job):
        return
    try:
        _time_job = cmds.scriptJob(event=["timeChanged", _on_time_changed],
                                   killWithScene=True)
    except Exception:
        _time_job = None


def _on_time_changed() -> None:
    if _pending and _suspend_depth == 0:
        _schedule(force=True)


def _show_pending_hint() -> None:
    try:
        cmds.inViewMessage(
            amg="retopoGuide: リバインド保留中 (ツールを抵けるか「今リバインド」で反映)",
            pos="botCenter", fade=True, fadeStayTime=1500)
    except Exception:
        pass


def mute_deformers(node: str) -> None:
    for d in deformers_of(node):
        if d in _muted or not cmds.objExists(d + ".envelope"):
            continue
        _muted[d] = float(cmds.getAttr(d + ".envelope"))
    _set_envelopes({d: 0.0 for d in _muted})


def unmute_deformers() -> None:
    if not _muted:
        return
    _set_envelopes(dict(_muted))
    _muted.clear()


def _set_envelopes(values: dict) -> None:
    # 編集の Undo と絡まないように履歴には残さない
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for d, v in values.items():
            if cmds.objExists(d + ".envelope"):
                try:
                    cmds.setAttr(d + ".envelope", v)
                except Exception:
                    pass
    finally:
        cmds.undoInfo(stateWithoutFlush=True)


# ---------------------------------------------------------------------------
# 要求 / 実行
# ---------------------------------------------------------------------------

def deformers_of(node: str) -> list[str]:
    """``node.outNetData`` の下流にある profileCurveDeformer を返す。"""
    if not node or not cmds.objExists(node):
        return []
    out = []
    for d in (cmds.listConnections(node + ".outNetData", source=False,
                                   destination=True) or []):
        if cmds.nodeType(d) == "profileCurveDeformer" and d not in out:
            out.append(d)
    return out


def request(node: str) -> None:
    """netData が変わった。デフォーマがあれば遅延リバインドを予約する。"""
    if _rebinding or not node:
        return
    node = node.split(".")[0]
    if not cmds.objExists(node) or cmds.nodeType(node) != "retopoGuideNode":
        return
    if not is_enabled():
        return
    if not deformers_of(node):
        return
    _pending.add(node)
    ensure_watch(node)
    if _suspend_depth == 0:
        # ドラッグ外の単発編集 (削除キーなど): リバインドまでの 1 フレームも歪ませない
        mute_deformers(node)
        if _tool_active:
            _show_pending_hint()
        else:
            _schedule()


def _schedule(force: bool = False) -> None:
    global _scheduled
    if _scheduled:
        return
    _scheduled = True
    cmds.evalDeferred(lambda f=force: flush(f), lowestPriority=True)


def flush(force: bool = False) -> None:
    """予約済みノードを全部リバインドする (evalDeferred から呼ばれる)。

    編集ツール中は *force* でない限り保留する (ツールを抵けた時にまとめて回す)。
    """
    global _scheduled
    _scheduled = False
    if _suspend_depth > 0 or (_tool_active and not force):
        return
    nodes = list(_pending)
    _pending.clear()
    try:
        for n in nodes:
            rebind_now(n, quiet=True)
    finally:
        unmute_deformers()


def rebind_now(node: str, quiet: bool = False) -> int:
    """*node* に繋がるデフォーマを今すぐリバインドする。作り直した数を返す。"""
    global _rebinding
    from Aru_RetopoTool.editor.deformer.curve_profile_rig import ProfileCurveRig

    _pending.discard(node)
    dfms = deformers_of(node)
    if not dfms:
        if not quiet:
            om.MGlobal.displayWarning(
                "[RetopoGuide] '%s' に profileCurveDeformer が繋がっていません" % node)
        return 0
    _rebinding = True
    n_ok = 0
    # バインドデータは netData の派生物なので Undo の対象にしない
    # (netData の Undo で scriptJob が再び走り、追従して作り直す)。
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        rig = ProfileCurveRig()
        for d in dfms:
            try:
                if rig.rebind_in_place(d, node):
                    n_ok += 1
            except Exception:
                om.MGlobal.displayWarning(
                    "[RetopoGuide] リバインド失敗 (%s): %s"
                    % (d, traceback.format_exc().strip().splitlines()[-1]))
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
        _rebinding = False
    if not _pending and _suspend_depth == 0:
        unmute_deformers()
    if n_ok and not quiet:
        cmds.inViewMessage(
            amg="retopoGuide: <hl>%d</hl> deformer(s) rebound" % n_ok,
            pos="topCenter", fade=True)
    return n_ok


# ---------------------------------------------------------------------------
# netData の監視 (Undo/Redo 追従)
# ---------------------------------------------------------------------------

def ensure_watch(node: str) -> None:
    job = _watch_jobs.get(node)
    if job is not None and cmds.scriptJob(exists=job):
        return
    if not cmds.objExists(node + ".netData"):
        return
    try:
        _watch_jobs[node] = cmds.scriptJob(
            attributeChange=[node + ".netData", lambda n=node: request(n)],
            killWithScene=True)
    except Exception:
        pass
