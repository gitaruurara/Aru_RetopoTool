"""
RetopoGuide Data Model
===================
Pixar SIGGRAPH 2022 §3 に基づく cubic Bézier カーブネット データ構造。

設計ポイント
-----------
- **共有 CV プール** : 全 CV を positions リストで管理。
  各 spline は 4 つのインデックスのタプル (i0, i1, i2, i3) で参照。
  交点（endpoint）を共有する spline は同じ CV インデックスを使う。
- **Intersection / Anchor 分類** :
    intersection : 3 本以上の spline の端点で共有される endpoint
    anchor       : 1 本の spline にのみ属する endpoint
-  **Curve** : anchor/intersection 間を繋ぐ連続 spline 列。
- シリアライズ : JSON で round-trip 可能。

データ構造
----------
positions : list[list[float, float, float]]   # CV の 3D 位置
splines   : list[tuple[int,int,int,int]]      # (i0,i1,i2,i3) インデックス
surfaces  : list[tuple[int,int,int]]   # スプラインのメッシュ投影情報 (face, u, v)
                                        # 省略可、None で未投影

用語
----
spline   : 4 点の cubic Bézier 1 区間
curve    : anchor/intersection 間を繋いだ spline の列
endpoint : spline の端点 CV (index 0 or 3)
interior : spline の内側ハンドル CV (index 1 or 2)
"""

from __future__ import annotations

import json
import math
import weakref
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# 小さなベクトルユーティリティ (Maya なしでも動くように純 Python)
# ---------------------------------------------------------------------------

def _v3_add(a, b):
    return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]

def _v3_sub(a, b):
    return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]

def _v3_scale(a, s):
    return [a[0]*s, a[1]*s, a[2]*s]

def _v3_len(a):
    return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])

def _v3_dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _v3_cross(a, b):
    return [
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    ]

def _v3_normalize(a):
    l = _v3_len(a)
    if l < 1e-12:
        return [0.0, 0.0, 1.0]
    return [a[0]/l, a[1]/l, a[2]/l]

def _v3_lerp(a, b, t):
    return [a[0]+(b[0]-a[0])*t,
            a[1]+(b[1]-a[1])*t,
            a[2]+(b[2]-a[2])*t]


# ---------------------------------------------------------------------------
# EP / Handle classes
# ---------------------------------------------------------------------------

class EP:
    """RetopoGuide endpoint (spline index 0 or 3)."""

    __slots__ = ("_cn", "cv_idx", "__weakref__")

    def __init__(self, cn: "RetopoGuideData", cv_idx: int):
        self._cn = cn
        self.cv_idx = cv_idx

    # -- position ----------------------------------------------------------

    @property
    def position(self) -> list[float]:
        return self._cn.positions[self.cv_idx]

    @position.setter
    def position(self, pos: list[float]) -> None:
        self._cn.move_cv(self.cv_idx, pos)

    # -- classification ----------------------------------------------------

    @property
    def ep_type(self) -> str:
        return self._cn._endpoint_type.get(self.cv_idx, "unknown")

    @property
    def is_intersection(self) -> bool:
        return self.ep_type == "intersection"

    @property
    def is_anchor(self) -> bool:
        return self.ep_type == "anchor"

    @property
    def is_node(self) -> bool:
        return self.ep_type == "node"

    # -- topology ----------------------------------------------------------

    @property
    def spline_indices(self) -> list[int]:
        return list(self._cn._endpoint_to_splines.get(self.cv_idx, []))

    @property
    def spline_count(self) -> int:
        return len(self._cn._endpoint_to_splines.get(self.cv_idx, []))

    @property
    def neighbors(self) -> list["EP"]:
        result = []
        for si in self.spline_indices:
            sp = self._cn.splines[si]
            other = sp[3] if sp[0] == self.cv_idx else sp[0]
            ep = self._cn.ep_at(other)
            if ep is not None:
                result.append(ep)
        return result

    @property
    def handles(self) -> list["Handle"]:
        result = []
        for si in self.spline_indices:
            h = self._cn._handle_for_ep_spline(self.cv_idx, si)
            if h is not None:
                result.append(h)
        return result

    @property
    def surface_binding(self):
        return self._cn.surface_binding[self.cv_idx]

    @surface_binding.setter
    def surface_binding(self, value) -> None:
        self._cn.surface_binding[self.cv_idx] = value

    def __repr__(self) -> str:
        return "EP(cv={}, type={})".format(self.cv_idx, self.ep_type)

    def __eq__(self, other) -> bool:
        if isinstance(other, EP):
            return self._cn is other._cn and self.cv_idx == other.cv_idx
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.cv_idx)


class Handle:
    """Spline interior control handle (spline index 1 or 2)."""

    __slots__ = ("_cn", "cv_idx", "spline_idx", "side", "__weakref__")

    def __init__(self, cn: "RetopoGuideData", cv_idx: int,
                 spline_idx: int, side: int):
        self._cn = cn
        self.cv_idx = cv_idx
        self.spline_idx = spline_idx
        self.side = side  # 0 = ep0 side (i1), 1 = ep3 side (i2)

    # -- position ----------------------------------------------------------

    @property
    def position(self) -> list[float]:
        return self._cn.positions[self.cv_idx]

    @position.setter
    def position(self, pos: list[float]) -> None:
        self._cn.move_cv(self.cv_idx, pos)

    # -- topology ----------------------------------------------------------

    @property
    def parent_ep(self) -> EP:
        sp = self._cn.splines[self.spline_idx]
        ep_cv = sp[0] if self.side == 0 else sp[3]
        return self._cn.ep_at(ep_cv)  # type: ignore[return-value]

    @property
    def opposite_ep(self) -> EP:
        sp = self._cn.splines[self.spline_idx]
        ep_cv = sp[3] if self.side == 0 else sp[0]
        return self._cn.ep_at(ep_cv)  # type: ignore[return-value]

    @property
    def partner(self) -> "Handle":
        sp = self._cn.splines[self.spline_idx]
        partner_cv = sp[2] if self.side == 0 else sp[1]
        partner_side = 1 if self.side == 0 else 0
        return self._cn.handle_at(partner_cv, self.spline_idx) or Handle(
            self._cn, partner_cv, self.spline_idx, partner_side)

    @property
    def surface_binding(self):
        return self._cn.surface_binding[self.cv_idx]

    @surface_binding.setter
    def surface_binding(self, value) -> None:
        self._cn.surface_binding[self.cv_idx] = value

    def __repr__(self) -> str:
        return "Handle(cv={}, sp={}, side={})".format(
            self.cv_idx, self.spline_idx, self.side)

    def __eq__(self, other) -> bool:
        if isinstance(other, Handle):
            return (self._cn is other._cn
                    and self.cv_idx == other.cv_idx
                    and self.spline_idx == other.spline_idx)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.cv_idx, self.spline_idx))


# ---------------------------------------------------------------------------
# Bézier closest-point (Newton-Raphson)
# ---------------------------------------------------------------------------
# MFnNurbsCurve.closestPoint() と同等の精度をベジェスプラインで得るための
# ユーティリティ。  粗探索 → Newton 反復 のハイブリッド。
#
# 原理:
#   距離² D(t) = |B(t) - Q|² を最小化する t を求める。
#   極値条件  f(t) = B'(t) · (B(t) - Q) = 0
#   Newton 更新  t ← t - f(t) / f'(t)
#     f'(t) = B''(t) · (B(t) - Q) + |B'(t)|²
# ---------------------------------------------------------------------------

def _bezier_eval(p0, p1, p2, p3, t):
    """Cubic Bézier evaluate — returns np (3,)."""
    u = 1.0 - t
    return u**3 * p0 + 3.0 * u**2 * t * p1 + 3.0 * u * t**2 * p2 + t**3 * p3


def _bezier_deriv1(p0, p1, p2, p3, t):
    """Cubic Bézier first derivative — returns np (3,)."""
    u = 1.0 - t
    return 3.0 * u**2 * (p1 - p0) + 6.0 * u * t * (p2 - p1) + 3.0 * t**2 * (p3 - p2)


def _bezier_deriv2(p0, p1, p2, p3, t):
    """Cubic Bézier second derivative — returns np (3,)."""
    u = 1.0 - t
    return 6.0 * u * (p2 - 2.0 * p1 + p0) + 6.0 * t * (p3 - 2.0 * p2 + p1)


def closest_point_on_bezier(
    p0, p1, p2, p3, query,
    n_init: int = 20,
    n_iter: int = 8,
    tol: float = 1e-10,
    t_hint: Optional[float] = None,
):
    """3 次ベジェカーブ上の最近接点を Newton-Raphson で求める。

    Parameters
    ----------
    p0, p1, p2, p3 : array-like (3,)
        ベジェ制御点。
    query : array-like (3,)
        問い合わせ点。
    n_init : int
        粗探索のサンプル数 (t_hint が None の場合に使用)。
    n_iter : int
        Newton 反復の最大回数。
    tol : float
        f(t) の収束判定閾値。
    t_hint : float or None
        粗探索をスキップして、この t を初期値にする。

    Returns
    -------
    (closest_pt, t, dist) : (np.ndarray(3,), float, float)
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    p3 = np.asarray(p3, dtype=float)
    Q  = np.asarray(query, dtype=float)

    # ---- 粗探索 (t_hint がなければ) ----
    if t_hint is None:
        ts = np.linspace(0.0, 1.0, n_init + 1)
        best_d2 = np.inf
        best_t  = 0.5
        for t in ts:
            pt = _bezier_eval(p0, p1, p2, p3, float(t))
            d2 = float(np.dot(pt - Q, pt - Q))
            if d2 < best_d2:
                best_d2 = d2
                best_t  = float(t)
    else:
        best_t = float(t_hint)

    # ---- Newton-Raphson 反復 ----
    t = best_t
    for _ in range(n_iter):
        B   = _bezier_eval(p0, p1, p2, p3, t)
        Bp  = _bezier_deriv1(p0, p1, p2, p3, t)
        Bpp = _bezier_deriv2(p0, p1, p2, p3, t)
        diff = B - Q
        f   = float(np.dot(Bp, diff))            # f(t) = B'·(B-Q)
        fp  = float(np.dot(Bpp, diff) + np.dot(Bp, Bp))  # f'(t)
        if abs(fp) < 1e-20:
            break
        dt = f / fp
        t  = t - dt
        t  = max(0.0, min(1.0, t))               # [0,1] にクランプ
        if abs(dt) < tol:
            break

    # ---- 端点チェック (Newton が端点を見逃す場合のガード) ----
    pt_best = _bezier_eval(p0, p1, p2, p3, t)
    d_best  = float(np.linalg.norm(pt_best - Q))
    for t_end in (0.0, 1.0):
        pt_end = _bezier_eval(p0, p1, p2, p3, t_end)
        d_end  = float(np.linalg.norm(pt_end - Q))
        if d_end < d_best:
            d_best  = d_end
            pt_best = pt_end
            t       = t_end

    return pt_best, t, d_best


# ---------------------------------------------------------------------------
# RetopoGuideData
# ---------------------------------------------------------------------------

class RetopoGuideData:
    """
    Pixar 方式のカーブネット データコンテナ。

    Examples
    --------
    >>> cn = RetopoGuideData()
    >>> i0 = cn.add_cv([0, 0, 0])
    >>> i1 = cn.add_cv([1, 0, 0])
    >>> # ハンドルを自動計算して spline を追加
    >>> sp = cn.add_spline_two_endpoints(i0, i1)
    >>> cn.classify_endpoints()
    """

    def __init__(self):
        self._lazy_objects = False
        self._objects_dirty = False
        # CV プール
        self.positions: list[list[float]] = []   # [[x,y,z], ...]

        # mesh 面投影情報 (CV ごと)  (face_idx, bary_u, bary_v) or None
        self.surface_binding: list[Optional[tuple]] = []

        # spline リスト: 各要素は (i0, i1, i2, i3) の int タプル
        self.splines: list[tuple[int,int,int,int]] = []

        # まだどのスプラインにも繋がっていないが、ユーザーが意図して置いた
        # 単独ポイント (EP) の CV インデックス。
        #
        # 「EP 削除やマージで参照が外れた残骸 CV」と区別するために必要。
        # 残骸は書き込み時に掃除するが、作りかけの単独ポイントを一緒に
        # 消してしまうとメッシュ上に点を置けなくなる。
        self.standalone_eps: set[int] = set()

        # ユーザーが手で動かしたハンドル CV。自動フィットで上書きしない。
        self.manual_handles: set[int] = set()

        # ---- 派生データ (classify_endpoints() で更新) ----
        # endpoint index → このエンドポイントを端点に持つ spline インデックスリスト
        self._endpoint_to_splines: dict[int, list[int]] = {}
        # endpoint の分類 'intersection' / 'anchor' / 'interior'
        self._endpoint_type: dict[int, str] = {}
        # curve リスト: 各 curve は spline インデックスの順序付きリスト
        self.curves: list[list[int]] = []

        # ---- EP / Handle オブジェクト (classify_endpoints() で構築) ----
        self._eps: list[int] = []
        self._handles: list[tuple[int, int, int]] = []
        self._cv_to_ep: dict[int, EP] = {}
        # key = (cv_idx, spline_idx, side)
        self._cv_to_handle: dict[tuple[int, int, int], Handle] = {}

    # ------------------------------------------------------------------
    # CV 操作
    # ------------------------------------------------------------------

    def add_cv(self, pos: list[float], surface: Optional[tuple] = None) -> int:
        """
        CV を追加する。重複検出はしない（呼び出し元の責任）。

        Returns
        -------
        int : 追加した CV のインデックス
        """
        self.positions.append([float(pos[0]), float(pos[1]), float(pos[2])])
        self.surface_binding.append(surface)
        return len(self.positions) - 1

    def move_cv(self, idx: int, pos: list[float]) -> None:
        """CV の位置を更新する。"""
        self.positions[idx] = [float(pos[0]), float(pos[1]), float(pos[2])]

    def find_nearest_cv(self, pos: list[float], radius: float,
                        exclude: Optional[int] = None) -> Optional[int]:
        """
        pos に最も近い CV を radius 以内で探す。

        どのスプラインからも参照されていない残骸 CV は対象外にする。
        (EP 削除などで positions に残骸が残ることがあり、それにスナップ
         してしまうと画面上に無い点に吸着したように見える)
        まだ線を繋いでいない単独ポイントは画面に出ているので対象に含める。

        Returns
        -------
        int or None
        """
        used = self.used_cv_indices() | self.standalone_eps
        best_d2 = radius * radius
        best_i  = None
        for i, p in enumerate(self.positions):
            if i == exclude or i not in used:
                continue
            d = _v3_sub(pos, p)
            d2 = d[0]*d[0] + d[1]*d[1] + d[2]*d[2]
            if d2 < best_d2:
                best_d2 = d2
                best_i  = i
        return best_i

    # ------------------------------------------------------------------
    # 孤立 CV (どのスプラインからも参照されていない残骸) の扱い
    # ------------------------------------------------------------------

    def used_cv_indices(self) -> set[int]:
        """いずれかのスプラインから参照されている CV インデックスの集合。"""
        used: set[int] = set()
        for sp in self.splines:
            for i in sp:
                used.add(int(i))
        return used

    def orphan_cv_indices(self) -> list[int]:
        """どのスプラインからも参照されていない残骸 CV インデックス。

        ``_remove_ep`` / ``_merge_two_eps`` はスプラインだけを削除して
        ``positions`` は詰めないため、編集を繰り返すとここに残骸が溜まる。

        ``standalone_eps`` に印を付けた「まだ線を繋いでいない単独ポイント」は
        ユーザーが意図して置いたものなので残骸には含めない。
        """
        used = self.used_cv_indices() | self.standalone_eps
        return [i for i in range(len(self.positions)) if i not in used]

    # ------------------------------------------------------------------
    # 単独ポイント (まだ線が繋がっていない EP)
    # ------------------------------------------------------------------

    def mark_standalone(self, cv: int) -> None:
        """*cv* を「意図して置いた単独ポイント」として印を付ける。

        印が付いている間は書き込み時の残骸掃除で消えない。
        """
        self.standalone_eps.add(int(cv))

    def unmark_standalone(self, cv: int) -> None:
        """単独ポイントの印を外す。次の書き込みで残骸として掃除される。"""
        self.standalone_eps.discard(int(cv))

    def is_standalone(self, cv: int) -> bool:
        """*cv* が単独ポイントの印を持つか。"""
        return int(cv) in self.standalone_eps

    # ------------------------------------------------------------------
    # 手動ハンドル (自動フィットで上書きしない)
    # ------------------------------------------------------------------

    def mark_manual_handle(self, cv: int) -> None:
        self.manual_handles.add(int(cv))

    def clear_manual_handles(self, cvs=None) -> None:
        if cvs is None:
            self.manual_handles.clear()
        else:
            self.manual_handles.difference_update(int(c) for c in cvs)

    def spline_has_manual_handle(self, sp_idx: int) -> bool:
        sp = self.splines[sp_idx]
        return sp[1] in self.manual_handles or sp[2] in self.manual_handles

    def sync_manual_handles(self) -> None:
        """スプラインから外れた (残骸になった) ハンドルの印を落とす。"""
        handles = {int(sp[1]) for sp in self.splines} | {int(sp[2]) for sp in self.splines}
        self.manual_handles &= handles

    def endpoint_indices(self) -> set[int]:
        """描画・選択の対象になる EP の集合。

        スプラインの端点に加え、まだ線を繋いでいない単独ポイントも含む。
        ``{sp[0]} | {sp[3]}`` を直接書くと単独ポイントが漏れる。
        """
        eps = {int(sp[0]) for sp in self.splines}
        eps |= {int(sp[3]) for sp in self.splines}
        eps |= {i for i in self.standalone_eps if i < len(self.positions)}
        return eps

    def sync_standalone(self) -> None:
        """スプラインに繋がった CV / 存在しない CV の印を落とす。

        線を繋いだ時点で単独ポイントではなくなるので印は不要になる。
        残したままだと、その EP に繋がるスプラインを全部消しても
        残骸として掃除されなくなってしまう。
        """
        used = self.used_cv_indices()
        n = len(self.positions)
        self.standalone_eps = {i for i in self.standalone_eps
                               if i < n and i not in used}

    def compact_cvs(self) -> dict[int, int]:
        """孤立 CV を取り除いて CV インデックスを詰める。

        Returns
        -------
        dict[int, int]
            旧インデックス → 新インデックスの写像。削除された CV は
            キーに含まれない。孤立 CV が無い場合は恒等写像を返す。
        """
        orphans = self.orphan_cv_indices()
        if not orphans:
            return {i: i for i in range(len(self.positions))}

        keep = [i for i in range(len(self.positions))
                if i not in set(orphans)]
        remap = {old: new for new, old in enumerate(keep)}

        self.positions = [self.positions[i] for i in keep]
        if self.surface_binding:
            self.surface_binding = [
                self.surface_binding[i] if i < len(self.surface_binding)
                else None
                for i in keep]
        self.splines = [tuple(remap[int(c)] for c in sp)
                        for sp in self.splines]
        self.standalone_eps = {remap[i] for i in self.standalone_eps
                               if i in remap}
        self.manual_handles = {remap[i] for i in self.manual_handles
                               if i in remap}
        self.classify_endpoints()
        return remap

    # ------------------------------------------------------------------
    # Spline 操作
    # ------------------------------------------------------------------

    def add_spline(self, i0: int, i1: int, i2: int, i3: int) -> int:
        """
        spline を追加する（4 CV インデックスを直接指定）。

        Returns
        -------
        int : 追加した spline のインデックス
        """
        self.splines.append((i0, i1, i2, i3))
        return len(self.splines) - 1

    def add_spline_two_endpoints(
        self,
        ep0: int,
        ep3: int,
        surface_normal: Optional[list[float]] = None,
    ) -> int:
        """
        2 つの endpoint 間に spline を追加する。
        ハンドル (i1, i2) は endpoint 間の 1/3 位置に自動配置する。
        surface_normal が与えられた場合、ハンドルをそれに垂直な方向へ
        初期化する（Pixar 論文の「perpendicular to surface normals」）。

        Returns
        -------
        int : 追加した spline のインデックス
        """
        p0 = self.positions[ep0]
        p3 = self.positions[ep3]

        if surface_normal is not None:
            # 接線方向 = p3 - p0 を法線に垂直な平面へ投影
            tang = _v3_sub(p3, p0)
            n    = _v3_normalize(surface_normal)
            dot  = _v3_dot(tang, n)
            tang = _v3_sub(tang, _v3_scale(n, dot))
            l    = _v3_len(tang)
            if l > 1e-8:
                tang = _v3_scale(tang, 1.0 / l)
            else:
                tang = _v3_sub(p3, p0)
                l    = _v3_len(tang)
                tang = _v3_scale(tang, 1.0 / (l if l > 1e-8 else 1.0))
            seg_len = _v3_len(_v3_sub(p3, p0))
            h1 = _v3_add(p0, _v3_scale(tang,  seg_len / 3.0))
            h2 = _v3_add(p3, _v3_scale(tang, -seg_len / 3.0))
        else:
            h1 = _v3_lerp(p0, p3, 1.0/3.0)
            h2 = _v3_lerp(p0, p3, 2.0/3.0)

        i1 = self.add_cv(h1)
        i2 = self.add_cv(h2)
        return self.add_spline(ep0, i1, i2, ep3)

    def split_spline(self, sp_idx: int, t: float = 0.5) -> tuple[int, int, int]:
        """
        spline を t で 2 分割し、新しい CV インデックスと 2 本の新 spline インデックスを返す。
        元の spline は削除される（末尾と swap して削除）。

        Returns
        -------
        (new_ep_idx, new_sp0_idx, new_sp1_idx)
        """
        if not hasattr(self,"_retopo_parents"):
            self._retopo_parents={i:i for i in range(len(self.splines))}
        parent=self._retopo_parents.get(sp_idx)
        i0, i1, i2, i3 = self.splines[sp_idx]
        p0 = self.positions[i0]
        p1 = self.positions[i1]
        p2 = self.positions[i2]
        p3 = self.positions[i3]

        # de Casteljau
        q0 = _v3_lerp(p0, p1, t)
        q1 = _v3_lerp(p1, p2, t)
        q2 = _v3_lerp(p2, p3, t)
        r0 = _v3_lerp(q0, q1, t)
        r1 = _v3_lerp(q1, q2, t)
        m  = _v3_lerp(r0, r1, t)   # 分割点

        new_h0a = self.add_cv(q0)   # 左 spline のハンドル (移動)
        new_h0b = self.add_cv(r0)   # 左 spline のハンドル (先端)
        new_ep  = self.add_cv(m)    # 共有 endpoint
        new_h1a = self.add_cv(r1)   # 右 spline のハンドル (根元)
        new_h1b = self.add_cv(q2)   # 右 spline のハンドル (移動)

        # 元の ハンドル CV (i1, i2) は「空き」になる。
        # 簡易実装として既存 i1, i2 の位置だけ更新し再利用する。
        self.positions[i1] = list(q0)
        self.positions[i2] = list(r0)

        # 左 spline は元のインデックスを再利用
        self.splines[sp_idx] = (i0, i1, i2, new_ep)

        # 右 spline を新規追加
        new_h1a_idx = self.add_cv(r1)
        new_h1b_idx = self.add_cv(q2)
        sp1 = self.add_spline(new_ep, new_h1a_idx, new_h1b_idx, i3)

        # 使わなかった new_h0a 等は削除するより「孤立 CV」として放置
        # (classify_endpoints 後に不参照 CV は無視される)
        # 簡易化のため参照した CV を pop して詰め直すことはしない

        self._retopo_parents[sp1]=parent
        return new_ep, sp_idx, sp1

    def splines_at_ep(self, ep_cv: int) -> list[int]:
        """*ep_cv* を端点 (i0 または i3) に持つ spline インデックスのリスト。"""
        return [si for si, sp in enumerate(self.splines)
                if sp[0] == ep_cv or sp[3] == ep_cv]

    def break_ep(self, ep_cv: int,
                 spline_indices: Optional[list[int]] = None) -> list[int]:
        """共有された endpoint を分離する (ウェルドの逆操作)。

        論文 §3 のモデリング操作「制御点のブレーク」。ウェルド
        (``_merge_two_eps``) が複数の EP を 1 つに束ねるのに対し、
        こちらは 1 つの EP に集まったスプラインを別々の CV へ切り離す。

        新しい CV は元の CV と同じ位置・同じ ``surface_binding`` を持つ
        ので、実行直後の見た目は変わらない。分離した点をあとから
        引き離すことで、交点だった場所を独立した端点にできる。

        Parameters
        ----------
        ep_cv : int
            分離する endpoint の CV インデックス。
        spline_indices : list[int] or None
            None なら接続する全スプラインを 1 本ずつバラバラにする
            (valence n の交点 → n 個の anchor)。
            リストを渡すとそのスプラインだけをまとめて 1 つの新しい
            CV へ移す (部分ブレーク)。元の CV には最低 1 本を残す。

        Returns
        -------
        list[int]
            新しく作られた CV インデックスのリスト。分離が起きなかった
            場合は空リスト。
        """
        connected = self.splines_at_ep(ep_cv)
        if len(connected) < 2:
            # 端点が 1 本しか持たない (anchor) なら分離するものがない
            return []

        pos = list(self.positions[ep_cv])
        binding = None
        if ep_cv < len(self.surface_binding):
            binding = self.surface_binding[ep_cv]

        def _reassign(sp_idx: int, new_cv: int) -> None:
            sp = list(self.splines[sp_idx])
            # 両端が同じ CV のループスプラインは i0 側だけ移す
            if sp[0] == ep_cv:
                sp[0] = new_cv
            elif sp[3] == ep_cv:
                sp[3] = new_cv
            self.splines[sp_idx] = tuple(sp)

        new_cvs: list[int] = []

        if spline_indices is None:
            # 全分離: 先頭 1 本は元の CV に残し、残りを 1 本ずつ新 CV へ
            for sp_idx in connected[1:]:
                new_cv = self.add_cv(pos, binding)
                _reassign(sp_idx, new_cv)
                new_cvs.append(new_cv)
        else:
            targets = [si for si in spline_indices if si in set(connected)]
            if not targets:
                return []
            # 元の CV に最低 1 本残す (全部指定されたら 1 本だけ除外する)
            if len(targets) >= len(connected):
                targets = targets[1:]
            if not targets:
                return []
            new_cv = self.add_cv(pos, binding)
            for sp_idx in targets:
                _reassign(sp_idx, new_cv)
            new_cvs.append(new_cv)

        self.classify_endpoints()
        return new_cvs

    # ------------------------------------------------------------------
    # トポロジ分析
    # ------------------------------------------------------------------

    def classify_endpoints(self) -> None:
        """
        endpoint の種別 (intersection/anchor) と curves を更新する。
        add_spline / split_spline の後に呼ぶ。
        EP / Handle オブジェクトもここで再構築される。
        """
        topology = (len(self.positions), tuple(tuple(sp) for sp in self.splines),
                    frozenset(self.standalone_eps))
        if self._lazy_objects and getattr(self, '_classified_topology', None) == topology:
            # Numeric edits retain connectivity. Still invalidate wrappers to
            # preserve classify_endpoints' owner/lookup refresh contract.
            self._eps = []; self._handles = []
            self._cv_to_ep = {}; self._cv_to_handle = {}
            self._objects_dirty = True
            return
        ep2sp: dict[int, list[int]] = {}
        for si, sp in enumerate(self.splines):
            for ep in (sp[0], sp[3]):
                ep2sp.setdefault(ep, []).append(si)

        self._endpoint_to_splines = ep2sp
        self._endpoint_type = {}

        for ep, sps in ep2sp.items():
            n = len(sps)
            if n >= 3:
                self._endpoint_type[ep] = "intersection"
            elif n == 2:
                # 2 本が連続しているだけ → curve の途中ノード
                self._endpoint_type[ep] = "node"
            else:
                self._endpoint_type[ep] = "anchor"

        # まだ線が繋がっていない単独ポイントも anchor 扱いにしておく。
        # 描画・選択で他の EP と同じように扱えるようにするため。
        for ep in self.standalone_eps:
            if ep < len(self.positions) and ep not in self._endpoint_type:
                self._endpoint_type[ep] = "anchor"
                self._endpoint_to_splines.setdefault(ep, [])

        # ---- EP / Handle オブジェクトを構築 ----
        if self._lazy_objects:
            self._eps = []; self._handles = []
            self._cv_to_ep = {}; self._cv_to_handle = {}
            self._objects_dirty = True
        else:
            self._build_ep_handle_objects()

        # ---- curves を再構築 ----
        self._rebuild_curves()
        self._classified_topology = topology

    def _ensure_ep_handle_objects(self) -> None:
        if self._objects_dirty:
            self._build_ep_handle_objects()

    def _build_ep_handle_objects(self) -> None:
        """EP と Handle のオブジェクトリストおよびルックアップ辞書を構築する。"""
        # Metadata is owned; wrappers are weakly cached and own this data.
        # An externally held wrapper keeps its owner alive without a cycle.
        self._eps = list(self._endpoint_to_splines)
        self._handles = [(sp[side+1], si, side)
                         for si,sp in enumerate(self.splines) for side in (0,1)]
        self._cv_to_ep = weakref.WeakValueDictionary()
        self._cv_to_handle = weakref.WeakValueDictionary()
        self._objects_dirty = False

    # ------------------------------------------------------------------
    # EP / Handle アクセサ
    # ------------------------------------------------------------------

    @property
    def eps(self) -> list[EP]:
        """全 EP オブジェクトのリスト。"""
        self._ensure_ep_handle_objects()
        return [self.ep_at(cv) for cv in self._eps]

    @property
    def handles(self) -> list[Handle]:
        """全 Handle オブジェクトのリスト。"""
        self._ensure_ep_handle_objects()
        return [self._handle_object(*key) for key in self._handles]

    @property
    def intersections(self) -> list[EP]:
        """intersection EP のみ (3本以上の spline が交わる点)。"""
        self._ensure_ep_handle_objects()
        return [e for e in self.eps if e.is_intersection]

    @property
    def anchors(self) -> list[EP]:
        """anchor EP のみ (1本の spline の端)。"""
        self._ensure_ep_handle_objects()
        return [e for e in self.eps if e.is_anchor]

    @property
    def ep_indices(self) -> set[int]:
        """全 EP の cv_idx セット。"""
        if self._lazy_objects:
            return set(self._endpoint_to_splines)
        self._ensure_ep_handle_objects()
        return set(self._eps)

    @property
    def handle_indices(self) -> set[int]:
        """全 Handle の cv_idx セット。"""
        if self._lazy_objects:
            return {h for sp in self.splines for h in sp[1:3]}
        self._ensure_ep_handle_objects()
        return {key[0] for key in self._handles}

    def ep_at(self, cv_idx: int) -> Optional[EP]:
        """cv_idx から EP を引く。見つからなければ None。"""
        self._ensure_ep_handle_objects()
        if cv_idx not in self._endpoint_to_splines:return None
        ep=self._cv_to_ep.get(cv_idx)
        if ep is None:
            ep=EP(self,cv_idx);self._cv_to_ep[cv_idx]=ep
        return ep

    def handle_at(self, cv_idx: int, spline_idx: int) -> Optional[Handle]:
        """(cv_idx, spline_idx) から Handle を引く。"""
        self._ensure_ep_handle_objects()
        if spline_idx<0 or spline_idx>=len(self.splines):return None
        sp=self.splines[spline_idx]
        if cv_idx==sp[2]:side=1
        elif cv_idx==sp[1]:side=0
        else:return None
        return self._handle_object(cv_idx,spline_idx,side)

    def _handle_object(self, cv_idx, spline_idx, side):
        key=(cv_idx,spline_idx,side)
        handle=self._cv_to_handle.get(key)
        if handle is None:
            handle=Handle(self,cv_idx,spline_idx,side)
            self._cv_to_handle[key]=handle
        return handle

    def eps_of(self, sp_idx: int) -> tuple[EP, EP]:
        """spline の両端 EP を返す。"""
        sp = self.splines[sp_idx]
        self._ensure_ep_handle_objects()
        return (self.ep_at(sp[0]), self.ep_at(sp[3]))

    def handles_of(self, sp_idx: int) -> tuple[Handle, Handle]:
        """spline のハンドル (i1 側, i2 側) を返す。"""
        sp = self.splines[sp_idx]
        self._ensure_ep_handle_objects()
        return (self.handle_at(sp[1], sp_idx),
                self.handle_at(sp[2], sp_idx))

    def _handle_for_ep_spline(self, ep_cv: int, sp_idx: int) -> Optional[Handle]:
        """ep_cv 側のハンドルを返す (内部用)。"""
        sp = self.splines[sp_idx]
        if sp[0] == ep_cv:
            self._ensure_ep_handle_objects()
            return self.handle_at(sp[1], sp_idx)
        elif sp[3] == ep_cv:
            self._ensure_ep_handle_objects()
            return self.handle_at(sp[2], sp_idx)
        return None

    def _rebuild_curves(self) -> None:
        """
        intersection / anchor 間を繋ぐ curve リストを再構築する。
        """
        ep2sp = self._endpoint_to_splines
        ep_type = self._endpoint_type
        visited_splines: set[int] = set()
        curves: list[list[int]] = []

        def _starting_eps():
            """intersection / anchor の endpoint を走査開始点として返す。"""
            for ep, t in ep_type.items():
                if t in ("intersection", "anchor"):
                    yield ep

        def _walk(start_ep: int, first_sp: int) -> list[int]:
            """start_ep から first_sp 方向へ curve を伸ばす。"""
            chain = [first_sp]
            visited_splines.add(first_sp)
            sp = self.splines[first_sp]
            others = [x for x in (sp[0], sp[3]) if x != start_ep]
            if not others:
                return chain  # 退化スプライン (自己ループ)
            cur_ep = others[0]

            while True:
                cur_type = ep_type.get(cur_ep, "interior")
                if cur_type in ("intersection", "anchor"):
                    break  # curve の端に到達
                # この endpoint に繋がる未訪問 spline を探す
                next_sps = [s for s in ep2sp.get(cur_ep, [])
                            if s not in visited_splines]
                if not next_sps:
                    break
                next_sp = next_sps[0]
                chain.append(next_sp)
                visited_splines.add(next_sp)
                nsp = self.splines[next_sp]
                others = [x for x in (nsp[0], nsp[3]) if x != cur_ep]
                if not others:
                    break  # 退化スプライン
                cur_ep = others[0]
            return chain

        for start_ep in _starting_eps():
            for sp_idx in ep2sp.get(start_ep, []):
                if sp_idx in visited_splines:
                    continue
                chain = _walk(start_ep, sp_idx)
                if chain:
                    curves.append(chain)

        # 孤立した closed curve (anchors/intersections を持たない)
        for si in range(len(self.splines)):
            if si not in visited_splines:
                curves.append([si])
                visited_splines.add(si)

        self.curves = curves

    # ------------------------------------------------------------------
    # Bézier サンプリング
    # ------------------------------------------------------------------

    def sample_spline(self, sp_idx: int, n_samples: int = 10) -> list[list[float]]:
        """
        spline の均等サンプル点を返す（n_samples 個）。
        """
        i0, i1, i2, i3 = self.splines[sp_idx]
        p0, p1, p2, p3 = (self.positions[x] for x in (i0, i1, i2, i3))
        pts = []
        for k in range(n_samples):
            t = k / max(n_samples - 1, 1)
            mt = 1.0 - t
            # cubic Bézier
            x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
            y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
            z = mt**3*p0[2] + 3*mt**2*t*p1[2] + 3*mt*t**2*p2[2] + t**3*p3[2]
            pts.append([x, y, z])
        return pts

    def sample_curve(self, curve_idx: int, n_per_spline: int = 10) -> list[list[float]]:
        """
        curve 全体を弧長均等サンプルした点列を返す（重複端点を除く）。
        """
        pts = []
        for i, sp_idx in enumerate(self.curves[curve_idx]):
            seg = self.sample_spline(sp_idx, n_per_spline)
            if i > 0:
                seg = seg[1:]   # 前 spline との接続点を除く
            pts.extend(seg)
        return pts

    def closest_point_on_spline(
        self,
        sp_idx: int,
        query,
        n_init: int = 20,
        t_hint: Optional[float] = None,
    ):
        """spline 上の最近接点を Newton-Raphson で求める。

        Parameters
        ----------
        sp_idx : int
            スプラインインデックス。
        query : array-like (3,)
            問い合わせ点。
        n_init : int
            粗探索のサンプル数。
        t_hint : float or None
            初期推定値。

        Returns
        -------
        (closest_pt, t, dist) : (np.ndarray(3,), float, float)
        """
        i0, i1, i2, i3 = self.splines[sp_idx]
        p0 = np.asarray(self.positions[i0], dtype=float)
        p1 = np.asarray(self.positions[i1], dtype=float)
        p2 = np.asarray(self.positions[i2], dtype=float)
        p3 = np.asarray(self.positions[i3], dtype=float)
        return closest_point_on_bezier(p0, p1, p2, p3, query,
                                       n_init=n_init, t_hint=t_hint)

    # ------------------------------------------------------------------
    # シリアライズ  (JSON)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        self.sync_manual_handles()
        return {
            "version":         1,
            "positions":       self.positions,
            "surface_binding": [list(s) if s else None
                                for s in self.surface_binding],
            "splines":         [list(sp) for sp in self.splines],
            "standalone_eps":  sorted(self.standalone_eps),
            "manual_handles":  sorted(self.manual_handles),
        }

    @classmethod
    def from_dict(cls, d: dict, *, lazy_objects=False) -> "RetopoGuideData":
        cn = cls()
        cn._lazy_objects = lazy_objects
        cn.positions       = [list(p) for p in d["positions"]]
        cn.surface_binding = [tuple(s) if s else None
                              for s in d.get("surface_binding", [])]
        # 長さが一致しない場合 (古いデータ) は None で埋める
        while len(cn.surface_binding) < len(cn.positions):
            cn.surface_binding.append(None)
        cn.splines = [tuple(sp) for sp in d["splines"]]
        cn.standalone_eps = {int(i) for i in d.get("standalone_eps", [])
                             if 0 <= int(i) < len(cn.positions)}
        cn.manual_handles = {int(i) for i in d.get("manual_handles", [])
                             if 0 <= int(i) < len(cn.positions)}
        cn.sync_standalone()
        cn.sync_manual_handles()
        cn.classify_endpoints()
        return cn

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, s: str) -> "RetopoGuideData":
        return cls.from_dict(json.loads(s))

    # 同じ netData 文字列は 1 回の評価・再描画で何度もパースされる
    # (ノードの各 compute、バウンディングボックス、描画オーバーライド)。
    # 400 CV で 1 回 25 ms かかるので、直前の数件を共有インスタンスで持つ。
    _PARSE_CACHE: "dict[str, RetopoGuideData]" = {}
    _PARSE_CACHE_MAX = 6

    @classmethod
    def from_json_cached(cls, s: str) -> "RetopoGuideData":
        """共有のパース結果を返す。**変更してはいけない** (読み取り専用)。"""
        cache = cls._PARSE_CACHE
        cn = cache.get(s)
        if cn is None:
            # Evaluation/drawing often need numeric data only. Delay wrappers
            # (which own this data and form cycles) until an EP/Handle accessor
            # is used, so evicted numeric cache entries release immediately.
            cn = cls.from_dict(json.loads(s), lazy_objects=True)
            if len(cache) >= cls._PARSE_CACHE_MAX:
                cache.pop(next(iter(cache)))
            cache[s] = cn
        return cn
