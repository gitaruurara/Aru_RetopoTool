# -*- coding: utf-8 -*-
"""
RetopoGuide Symmetry -- カーブネットの対称作成

編集コンテキストで点やカーブを作ったとき、指定した対称面の反対側にも
同じものを自動で作るための補助モジュール。

論文 (de Goes et al. 2022) には対称化の記述は無い。純粋に作業効率のための
拡張で、既定はオフ。

設定はツール設定 (Tool Settings) から optionVar に保存される。

    retopoGuideSymmetryAxis   "" / "x" / "y" / "z"   (既定 "" = オフ)
    retopoGuideSymmetrySpace  "object" / "world"     (既定 "object")

"object" はメッシュのローカル空間で反転する (メッシュを回しても対称面が
一緒に回る)。"world" はワールド空間で反転する。

対応関係は保存しない。「反転位置に既にある EP を探し、無ければ作る」という
その場限りの探索で解決する。こうしておくと、あとから片側を消したり動かしたり
しても壊れた対応が残らない。
"""

from maya import cmds
import maya.OpenMaya as om

# optionVar 名
OPT_AXIS  = "retopoGuideSymmetryAxis"
OPT_SPACE = "retopoGuideSymmetrySpace"
OPT_MIRROR_MODE = "retopoGuideMirrorMode"
OPT_MIRROR_DIR  = "retopoGuideMirrorDirection"

# 軸名 → positions のインデックス
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# ツール設定のプルダウン用 (表示ラベル, 値)
AXIS_CHOICES = [
    (u"オフ",            ""),
    (u"X (YZ 面で反転)",  "x"),
    (u"Y (XZ 面で反転)",  "y"),
    (u"Z (XY 面で反転)",  "z"),
]

SPACE_CHOICES = [
    (u"オブジェクト", "object"),
    (u"ワールド",     "world"),
]

#: 左右反転作成のやり方
MIRROR_MODE_CHOICES = [
    (u"作り直す (反対側を消す)", "replace"),
    (u"足すだけ",               "add"),
]

#: どちら側を反転元にするか
MIRROR_DIR_CHOICES = [
    (u"+ から − へ", "positive"),
    (u"− から + へ", "negative"),
]

_MIRROR_MODES = {v for _l, v in MIRROR_MODE_CHOICES}
_MIRROR_DIRS  = {v for _l, v in MIRROR_DIR_CHOICES}


# ---------------------------------------------------------------------------
# 設定の読み書き
# ---------------------------------------------------------------------------

def get_axis() -> str:
    """対称軸を返す。オフなら空文字。"""
    try:
        v = cmds.optionVar(q=OPT_AXIS) or ""
    except Exception:
        return ""
    v = str(v).lower()
    return v if v in _AXIS_INDEX else ""


def set_axis(axis: str) -> None:
    axis = str(axis or "").lower()
    cmds.optionVar(sv=(OPT_AXIS, axis if axis in _AXIS_INDEX else ""))


def get_space() -> str:
    """対称空間を返す ("object" または "world")。"""
    try:
        v = cmds.optionVar(q=OPT_SPACE) or ""
    except Exception:
        return "object"
    return "world" if str(v).lower() == "world" else "object"


def set_space(space: str) -> None:
    cmds.optionVar(sv=(OPT_SPACE,
                       "world" if str(space).lower() == "world" else "object"))


def is_enabled() -> bool:
    return bool(get_axis())


def get_mirror_mode() -> str:
    """左右反転作成のやり方 ("replace" または "add")。"""
    try:
        v = str(cmds.optionVar(q=OPT_MIRROR_MODE) or "").lower()
    except Exception:
        return "replace"
    return v if v in _MIRROR_MODES else "replace"


def set_mirror_mode(mode: str) -> None:
    mode = str(mode or "").lower()
    cmds.optionVar(sv=(OPT_MIRROR_MODE,
                       mode if mode in _MIRROR_MODES else "replace"))


def get_mirror_direction() -> str:
    """どちら側を反転元にするか ("positive" または "negative")。

    "positive" なら対称面から見て + 側を正として − 側へ写す。
    """
    try:
        v = str(cmds.optionVar(q=OPT_MIRROR_DIR) or "").lower()
    except Exception:
        return "positive"
    return v if v in _MIRROR_DIRS else "positive"


def set_mirror_direction(direction: str) -> None:
    direction = str(direction or "").lower()
    cmds.optionVar(sv=(OPT_MIRROR_DIR,
                       direction if direction in _MIRROR_DIRS else "positive"))


def mirror_source_sign(direction: str = None) -> float:
    """反転元の側の符号 (+1.0 / -1.0) を返す。"""
    d = get_mirror_direction() if direction is None else direction
    return 1.0 if d == "positive" else -1.0


# ---------------------------------------------------------------------------
# 反転計算
# ---------------------------------------------------------------------------

def _object_matrices(mesh_name: str):
    """メッシュの (world 行列, その逆行列) を返す。取れなければ (None, None)。"""
    if not mesh_name or not cmds.objExists(mesh_name):
        return None, None
    try:
        sel = om.MSelectionList()
        sel.add(mesh_name)
        dag = om.MDagPath()
        sel.getDagPath(0, dag)
        m = dag.inclusiveMatrix()
        return m, m.inverse()
    except Exception:
        return None, None


def mirror_point(pos, mesh_name: str,
                 axis: str = None, space: str = None) -> list:
    """ワールド座標 *pos* を対称面で反転したワールド座標を返す。

    axis が空 (オフ) の場合は *pos* をそのまま返す。
    """
    axis = get_axis() if axis is None else (axis or "").lower()
    if axis not in _AXIS_INDEX:
        return list(pos)
    k = _AXIS_INDEX[axis]
    space = get_space() if space is None else space

    if space == "world":
        out = list(pos)
        out[k] = -out[k]
        return out

    wm, wim = _object_matrices(mesh_name)
    if wm is None:
        # トランスフォームが取れないならワールド反転にフォールバックせず、
        # 何もしない (意図しない位置に点を作らないため)
        return list(pos)

    p = om.MPoint(pos[0], pos[1], pos[2]) * wim
    local = [p.x, p.y, p.z]
    local[k] = -local[k]
    q = om.MPoint(local[0], local[1], local[2]) * wm
    return [q.x, q.y, q.z]


def on_symmetry_plane(pos, mesh_name: str, tol: float,
                      axis: str = None, space: str = None) -> bool:
    """*pos* が対称面の上 (= 反転しても動かない) かどうか。"""
    m = mirror_point(pos, mesh_name, axis=axis, space=space)
    d2 = sum((m[i] - pos[i]) ** 2 for i in range(3))
    return d2 <= tol * tol


def plane_coord(pos, mesh_name: str,
                axis: str = None, space: str = None):
    """対称面からの符号付き距離を返す。対称化がオフなら None。

    符号が対称面のどちら側にいるかを表す。
    """
    axis = get_axis() if axis is None else (axis or "").lower()
    if axis not in _AXIS_INDEX:
        return None
    k = _AXIS_INDEX[axis]
    space = get_space() if space is None else space

    if space == "world":
        return float(pos[k])

    wm, wim = _object_matrices(mesh_name)
    if wm is None:
        return None
    p = om.MPoint(pos[0], pos[1], pos[2]) * wim
    return float([p.x, p.y, p.z][k])


def project_to_plane(pos, mesh_name: str,
                     axis: str = None, space: str = None) -> list:
    """*pos* を対称面の上へ落としたワールド座標を返す。

    対称化がオフ、または座標変換が取れない場合は *pos* をそのまま返す。
    """
    axis = get_axis() if axis is None else (axis or "").lower()
    if axis not in _AXIS_INDEX:
        return list(pos)
    k = _AXIS_INDEX[axis]
    space = get_space() if space is None else space

    if space == "world":
        out = list(pos)
        out[k] = 0.0
        return out

    wm, wim = _object_matrices(mesh_name)
    if wm is None:
        return list(pos)
    p = om.MPoint(pos[0], pos[1], pos[2]) * wim
    local = [p.x, p.y, p.z]
    local[k] = 0.0
    q = om.MPoint(local[0], local[1], local[2]) * wm
    return [q.x, q.y, q.z]


# ---------------------------------------------------------------------------
# EP の対応付け
# ---------------------------------------------------------------------------

def find_mirror_ep(cn, mesh_name: str, ep: int, tol: float):
    """*ep* の反転位置にある既存 EP を探す。見つからなければ None。

    対称面の上にある EP は自分自身を返す。
    """
    if not is_enabled() or ep is None or ep >= len(cn.positions):
        return None
    pos = cn.positions[ep]
    mpos = mirror_point(pos, mesh_name)
    d2 = sum((mpos[i] - pos[i]) ** 2 for i in range(3))
    if d2 <= tol * tol:
        return ep
    found = cn.find_nearest_cv(mpos, tol, exclude=ep)
    if found is None:
        return None
    return found if found in cn.endpoint_indices() else None
