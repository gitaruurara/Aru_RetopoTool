"""論文 §5 の点単位ソフト拘束 (ピン留め) を扱うツール群。

論文 §5「制限」より::

    点単位のハンドルも重心座標でウェイト付けされたソフト拘束を通じて
    formulation に組み込むのが簡単である。

カーブネットは「カーブで囲まれた領域」を単位に変形を伝播させるため、
自前のカーブを持たないブロックは隣のカーブの変形勾配を定数として受け取り、
まるごとアフィン変換で運ばれる (これは論文の定式化どおりの挙動)。
「そこは動かさない」と明示したいときにこのピン留めを使う。

ピンは ``profileCurveDeformer.pinWeights`` に ``{"頂点index": 重み}`` の
JSON として保存される。重みは Eq.6 の左辺に ``+ λW`` として加算され、
ラプラシアンの代表スケールで正規化されるのでメッシュ解像度に依存しない。

  重み 0.01 … ゆるく引き戻す
  重み 1.0  … ほぼ固定 (推奨)
  重み 100  … 実質ハード拘束
"""
from __future__ import annotations

import json
import re

import maya.cmds as cmds

from Aru_RetopoTool.editor.logger import get_logger

_log = get_logger(__name__)

_DEFAULT_WEIGHT = 1.0
_VTX_RE = re.compile(r"^(?P<obj>.+)\.vtx\[(?P<a>\d+)(?::(?P<b>\d+))?\]$")


def find_deformer(mesh: str | None = None) -> str | None:
    """*mesh* に付いた profileCurveDeformer を探す。

    Parameters
    ----------
    mesh : str, optional
        メッシュ名。省略時は選択から探し、それでも見つからなければ
        シーン中の profileCurveDeformer を 1 つ返す。

    Returns
    -------
    str | None
        デフォーマ名。
    """
    if mesh:
        hist = cmds.listHistory(mesh, pdo=True) or []
        for n in hist:
            if cmds.nodeType(n) == "profileCurveDeformer":
                return n

    for sel in cmds.ls(sl=True, o=True) or []:
        hist = cmds.listHistory(sel, pdo=True) or []
        for n in hist:
            if cmds.nodeType(n) == "profileCurveDeformer":
                return n

    all_dfm = cmds.ls(type="profileCurveDeformer") or []
    return all_dfm[0] if all_dfm else None


def deformed_mesh(deformer: str) -> str | None:
    """*deformer* が変形しているメッシュシェイプを返す。"""
    for n in cmds.listHistory(deformer, future=True, af=True) or []:
        if cmds.nodeType(n) == "mesh":
            return n
    return None


def get_pins(deformer: str) -> dict[int, float]:
    """*deformer* に設定されたピンを ``{頂点index: 重み}`` で返す。"""
    if not cmds.objExists(deformer + ".pinWeights"):
        return {}
    s = cmds.getAttr(deformer + ".pinWeights") or ""
    if not s:
        return {}
    try:
        return {int(k): float(v) for k, v in json.loads(s).items()}
    except Exception as e:
        _log.warning("pinWeights の読み取りに失敗: %s", e)
        return {}


def set_pins(deformer: str, pins: dict[int, float]) -> None:
    """*deformer* のピンを ``pins`` で置き換える。空 dict で全解除。"""
    pins = {int(k): float(v) for k, v in (pins or {}).items() if float(v) > 0.0}
    payload = json.dumps({str(k): v for k, v in sorted(pins.items())}) if pins else ""
    cmds.setAttr(deformer + ".pinWeights", payload, type="string")
    _log.info("%s: ピン %d 頂点", deformer, len(pins))


def selected_vertex_indices() -> tuple[str | None, list[int]]:
    """選択中の頂点を ``(メッシュ名, インデックス列)`` で返す。"""
    sel = cmds.ls(sl=True, fl=True, long=False) or []
    obj = None
    idx: list[int] = []
    for s in sel:
        m = _VTX_RE.match(s)
        if not m:
            continue
        obj = obj or m.group("obj")
        a = int(m.group("a"))
        b = m.group("b")
        idx.extend(range(a, int(b) + 1) if b else [a])
    return obj, sorted(set(idx))


def pin_selected(weight: float = _DEFAULT_WEIGHT,
                 deformer: str | None = None) -> int:
    """選択中の頂点をピン留めする。既存のピンには追加される。

    Returns
    -------
    int
        ピン留めした頂点数。
    """
    obj, idx = selected_vertex_indices()
    if not idx:
        cmds.warning("頂点が選択されていません。")
        return 0
    dfm = deformer or find_deformer(obj)
    if not dfm:
        cmds.warning("profileCurveDeformer が見つかりません。")
        return 0

    pins = get_pins(dfm)
    for i in idx:
        pins[i] = float(weight)
    set_pins(dfm, pins)
    return len(idx)


def unpin_selected(deformer: str | None = None) -> int:
    """選択中の頂点のピンを外す。

    Returns
    -------
    int
        実際に外れた頂点数。
    """
    obj, idx = selected_vertex_indices()
    if not idx:
        cmds.warning("頂点が選択されていません。")
        return 0
    dfm = deformer or find_deformer(obj)
    if not dfm:
        cmds.warning("profileCurveDeformer が見つかりません。")
        return 0

    pins = get_pins(dfm)
    removed = sum(1 for i in idx if pins.pop(i, None) is not None)
    set_pins(dfm, pins)
    return removed


def clear_pins(deformer: str | None = None) -> None:
    """すべてのピンを解除する。"""
    dfm = deformer or find_deformer()
    if not dfm:
        cmds.warning("profileCurveDeformer が見つかりません。")
        return
    set_pins(dfm, {})


def select_pinned(deformer: str | None = None) -> int:
    """ピン留めされている頂点を選択する。

    Returns
    -------
    int
        選択した頂点数。
    """
    dfm = deformer or find_deformer()
    if not dfm:
        cmds.warning("profileCurveDeformer が見つかりません。")
        return 0
    pins = get_pins(dfm)
    shape = deformed_mesh(dfm)
    if not pins or not shape:
        cmds.select(clear=True)
        return 0
    cmds.select(["%s.vtx[%d]" % (shape, i) for i in sorted(pins)], r=True)
    return len(pins)


def pin_shell_of_selected(weight: float = _DEFAULT_WEIGHT,
                          deformer: str | None = None) -> int:
    """選択頂点が属する連結シェル全体をピン留めする。

    「胴体はまるごと動かしたくない」というときに、頂点を 1 つ選ぶだけで
    済むようにするためのショートカット。
    """
    obj, idx = selected_vertex_indices()
    if not idx:
        cmds.warning("頂点が選択されていません。")
        return 0
    cmds.select(cmds.polySelect(obj, extendToShell=idx[0], ass=True) or [],
                r=True)
    return pin_selected(weight, deformer)


# ----------------------------------------------------------------------
# §5 プロジェクション対レスト
# ----------------------------------------------------------------------

def set_use_input_as_rest(enabled=True, deformer=None):
    """上流の変形をレストポーズとして使うかを切り替える (論文 §5)。

    ON にすると skinCluster / blendShape など上流のデフォーマの結果の上に
    カーブネット変形が乗る (レイヤードリグ)。OFF にするとバインド時の
    メッシュ形状が常にレストになる (従来動作)。
    """
    dfm = deformer or find_deformer()
    if not dfm:
        cmds.warning("profileCurveDeformer が見つからないわ")
        return False
    cmds.setAttr(dfm + ".useInputAsRest", 1 if enabled else 0)
    print("[RetopoGuide] %s.useInputAsRest = %s" % (dfm, bool(enabled)))
    return True


def get_use_input_as_rest(deformer=None):
    """``useInputAsRest`` の現在値を返す。"""
    dfm = deformer or find_deformer()
    if not dfm:
        return None
    return bool(cmds.getAttr(dfm + ".useInputAsRest"))

# ----------------------------------------------------------------------
# カーブネットの効果範囲 (falloffMode / restFalloff)
# ----------------------------------------------------------------------

def rest_size(deformer=None):
    """バインド時のメッシュの大きさ (バウンディングボックス対角) を返す。

    ``poissonBindData`` に保存されたレスト頂点から測るので、今の
    ポーズにも上流の変形にも左右されない。バインドデータが読めない
    ときだけ ``exactWorldBoundingBox`` にフォールバックする。
    """
    dfm = deformer or find_deformer()
    if not dfm:
        return 0.0
    try:
        import json as _json
        import numpy as _np
        s = cmds.getAttr(dfm + ".poissonBindData") or ""
        if s:
            rv = _np.asarray(_json.loads(s).get("rest_verts") or [],
                             dtype=float)
            if rv.ndim == 2 and len(rv) > 1:
                ext = rv.max(axis=0) - rv.min(axis=0)
                return float(_np.linalg.norm(ext))
    except Exception:
        pass
    mesh = deformed_mesh(dfm)
    if not mesh:
        return 0.0
    bb = cmds.exactWorldBoundingBox(mesh)
    return ((bb[3] - bb[0]) ** 2 + (bb[4] - bb[1]) ** 2
            + (bb[5] - bb[2]) ** 2) ** 0.5


def suggest_rest_falloff(deformer=None):
    """メッシュの大きさから妥当な効果範囲 (標準モード相当) を見積もる。

    論文 式(5) はカットフェイスの勾配しか目標に持たないため、ブロックの
    絶対位置はそのブロックに触れているカーブ拘束だけで決まる。カーブに
    覆われていない領域は何にも固定されておらず、離れたカーブが動くと
    まるごと引きずられてしまう。効果範囲はその引きずりを断ち切る距離。
    """
    from Aru_RetopoTool.editor.deformer import poisson_solve as ps
    return round(ps.falloff_from_mode(
        ps.FALLOFF_MODE_NORMAL, rest_size(deformer)), 3)


def set_falloff_mode(mode, deformer=None):
    """効果範囲のプリセットを切り替える。

    ``mode`` は :mod:`poisson_solve` の ``FALLOFF_MODE_*``。
    """
    from Aru_RetopoTool.editor.deformer import poisson_solve as ps
    dfm = deformer or find_deformer()
    if not dfm:
        cmds.warning("profileCurveDeformer が見つからないわ")
        return False
    if not cmds.objExists(dfm + ".falloffMode"):
        cmds.warning("このデフォーマには falloffMode がないわ。"
                     "プラグインを読み込み直してね。")
        return False
    cmds.setAttr(dfm + ".falloffMode", int(mode))
    print("[RetopoGuide] %s.falloffMode = %s (効果範囲 %.3f)"
          % (dfm, ps.FALLOFF_MODE_LABELS.get(int(mode), mode),
             effective_rest_falloff(dfm)))
    return True


def get_falloff_mode(deformer=None):
    """``falloffMode`` の現在値を返す。"""
    dfm = deformer or find_deformer()
    if not dfm or not cmds.objExists(dfm + ".falloffMode"):
        return None
    return int(cmds.getAttr(dfm + ".falloffMode"))


def effective_rest_falloff(deformer=None):
    """今のモードで実際に使われる効果範囲 (距離) を返す。"""
    from Aru_RetopoTool.editor.deformer import poisson_solve as ps
    dfm = deformer or find_deformer()
    if not dfm:
        return 0.0
    mode = get_falloff_mode(dfm)
    if mode is None:
        return float(get_rest_falloff(dfm) or 0.0)
    return ps.falloff_from_mode(mode, rest_size(dfm),
                                float(get_rest_falloff(dfm) or 0.0))


def set_rest_falloff(distance=None, deformer=None):
    """カーブネットの影響が届く距離をカスタム指定する。

    0 以下で無制限 (論文そのままの挙動)。``distance`` を省略すると
    :func:`suggest_rest_falloff` の見積もりを使う。モードは自動的に
    「カスタム」(0 のときは「無制限」) に切り替わる。
    """
    from Aru_RetopoTool.editor.deformer import poisson_solve as ps
    dfm = deformer or find_deformer()
    if not dfm:
        cmds.warning("profileCurveDeformer が見つからないわ")
        return False
    if not cmds.objExists(dfm + ".restFalloff"):
        cmds.warning("このデフォーマには restFalloff がないわ。"
                     "プラグインを読み込み直してね。")
        return False
    if distance is None:
        distance = suggest_rest_falloff(dfm)
    distance = float(distance)
    cmds.setAttr(dfm + ".restFalloff", distance)
    if cmds.objExists(dfm + ".falloffMode"):
        cmds.setAttr(dfm + ".falloffMode",
                     ps.FALLOFF_MODE_OFF if distance <= 0.0
                     else ps.FALLOFF_MODE_CUSTOM)
    print("[RetopoGuide] %s.restFalloff = %s" % (dfm, distance))
    return True


def get_rest_falloff(deformer=None):
    """``restFalloff`` (カスタムモードで使う距離) の現在値を返す。"""
    dfm = deformer or find_deformer()
    if not dfm or not cmds.objExists(dfm + ".restFalloff"):
        return None
    return float(cmds.getAttr(dfm + ".restFalloff"))
