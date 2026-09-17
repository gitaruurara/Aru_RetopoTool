# -*- coding: utf-8 -*-
"""
RetopoGuide Context -- draggerContext callbacks + spline operations
=================================================================
"""

from __future__ import annotations

import math
import traceback
from typing import Optional

import maya.OpenMaya as om
import maya.OpenMayaUI as omui
import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet import curve_net_rebind as _rebind
from Aru_RetopoTool.editor.curvenet.curve_net_data import closest_point_on_bezier
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import (
    kPluginNodeName, kEPNodeName, kHandleNodeName,
    _DRAGGER_CTX, _LOC_GRP_SUFFIX,
    _ctx, _nd_sj_map, _orphaned_loc_groups,
)

from Aru_RetopoTool.editor.curvenet.curve_net_edit import is_pose_driven
from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym
from Aru_RetopoTool.editor.curvenet.curve_net_edit import (
    _dirty_shape_view, _get_mesh_fn, _closest_point_on_mesh,
    _closest_bary_on_face, _get_normal_at_point,
    _commit_net_data as _edit_commit_net_data,
    _raycast_from_screen, _snap_radius, make_visibility_test,
    RetopoGuideAccessor,
    _find_shape_node, _get_net_data_positions, _world_to_screen,
    _get_net_transform,
)


def _commit_net_data(node: str, cn: RetopoGuideData) -> None:
    """netData を書き込み、CV が再採番されたら状態の CV インデックスも直す。

    書き込み時に孤立 CV が掃除されると CV 番号が詰められるため、
    ``sel_ep`` などのキャッシュを張り替えないと別の CV を指してしまう。
    """
    remap = _edit_commit_net_data(node, cn)
    if remap:
        try:
            _ctx.remap_cv_indices(remap)
        except AttributeError:
            pass

#: クリックとドラッグを区別する画面上の移動量 (ピクセル)
_CLICK_SLOP_PX = 4.0

#: LMB ドラッグ中のホバー判定用カーブネットキャッシュ {node: RetopoGuideData}
#: マウス移動のたびに netData の JSON を読み直すと重いため。
#: LMB ドラッグ中はネットを書き換えないので使い回して安全。
_DRAG_CN_CACHE: dict = {}


#: __slots__ に無いフィールドの退避先 (リロード前の古い state インスタンス用)
_state_extra: dict = {}


def _state_set(state, name, value) -> None:
    """state のフィールドを書く。古い state インスタンスでも落ちない。"""
    try:
        setattr(state, name, value)
    except AttributeError:
        _state_extra[name] = value


def _state_get(state, name, default=None):
    if name in _state_extra:
        return _state_extra[name]
    return getattr(state, name, default)


#: 測地線 (メッシュ表面上の最短経路) を求める緩和の反復回数
#:
#: 旧実装は「カーブ上の点をメッシュへ投影して目標にする」だけだった。
#: この目的関数は「面に載ってさえいれば誤差ゼロ」なので横方向がまったく
#: 拘束されず、しかも目標が自分自身から作られるため一度ずれると
#: そのずれが増幅される。結果カーブが横へ大きく膨らんでいた。
#: 目標を「両端だけで決まる測地線」にすると、この 2 つの穴が同時に塞がる。
_FIT_ITERS = 20
#: ハンドルフィッティングのサンプル数 (内部点のみ)
_FIT_SAMPLES = 21
#: 「収束した」とみなす誤差 (弦長に対する比)
_FIT_EPS_RATIO = 1.0e-4
#: ドラッグ中の下書き品質。最終品質だと 1 本 80ms 掛かることがあり、
#: 複数のスプラインが繋がった EP を動かすと目に見えてカクつく。
#: 離した時点で最終品質に張り直すので、ドラッグ中は粗くてよい。
_FIT_DRAFT_ITERS = 8
_FIT_DRAFT_SAMPLES = 11
#: 測地線を折れ線で表すときの分割数
_GEO_SEGMENTS = 24
_GEO_DRAFT_SEGMENTS = 10
#: 緩和の強さ。1.0 だと偶数点と奇数点で振動するので少し弱める
_GEO_RELAX = 0.7
#: 最小二乗の反復回数。目標が測地線に固定されメッシュへの問い合わせが
#: 不要になったので安い。実測では 12 回では足りず 40 回でようやく収束する
_FIT_PARAM_ROUNDS = 40
#: 接平面へ倒したハンドルの長さを元に戻す下限。
#: これより大きく倒れた場合は戻さない (横へ振れるのを防ぐ)
_TANGENT_RESTORE_MIN = 0.7


def _bezier_point(p0, p1, p2, p3, t):
    """3 次ベジェの点を返す。"""
    u = 1.0 - t
    a = u * u * u
    b = 3.0 * u * u * t
    c = 3.0 * u * t * t
    d = t * t * t
    return [a * p0[k] + b * p1[k] + c * p2[k] + d * p3[k] for k in range(3)]


def _resample_polyline(poly, count):
    """折れ線を弧長で等分し直して ``count`` 個の点にする。

    緩和 (ラプラシアン平滑化) は点を一箇所に寄せ集めてしまうので、
    毎回これで並べ直す。ここで得られる弧長パラメータは、そのまま
    ベジェのフィッティングに使えるので一石二鳥。
    """
    import math as _math

    n = len(poly)
    if n < 2 or count < 2:
        return [list(p) for p in poly]

    seg = [0.0]
    for i in range(n - 1):
        d = _math.dist(poly[i], poly[i + 1])
        seg.append(seg[-1] + d)
    total = seg[-1]
    if total < 1e-12:
        return [list(poly[0]) for _ in range(count)]

    out = [list(poly[0])]
    j = 0
    for k in range(1, count - 1):
        want = total * k / float(count - 1)
        while j < n - 2 and seg[j + 1] < want:
            j += 1
        span = seg[j + 1] - seg[j]
        u = 0.0 if span < 1e-12 else (want - seg[j]) / span
        out.append([poly[j][c] + (poly[j + 1][c] - poly[j][c]) * u
                    for c in range(3)])
    out.append(list(poly[-1]))
    return out


def _closest_on_polyline(poly, pt):
    """折れ線上でいちばん近い点を返す。"""
    return _PolylineProjector(poly).closest(pt)


class _PolylineProjector:
    """折れ線への最近接点を numpy で一括計算する。

    ハンドルのフィットは同じ測地線に対して数百回問い合わせるので、
    セグメント配列を一度作って使い回す (純 Python の 100 倍以上速い)。
    """

    def __init__(self, poly):
        import numpy as np
        P = np.asarray(poly, dtype=float).reshape(-1, 3)
        self._np = np
        self._P = P
        if len(P) < 2:
            self._A = self._V = self._VV = None
            return
        self._A = P[:-1]
        self._V = P[1:] - P[:-1]
        vv = (self._V * self._V).sum(axis=1)
        self._VV = np.where(vv < 1e-18, 1.0, vv)
        self._degenerate = vv < 1e-18

    def closest(self, pt):
        if self._A is None:
            return list(pt) if len(self._P) == 0 else self._P[0].tolist()
        return self.closest_many([pt])[0].tolist()

    def closest_many(self, pts):
        """(M,3) の点群ずつなとも近い折れ線上の点 (M,3) を返す。"""
        np = self._np
        Q = np.asarray(pts, dtype=float).reshape(-1, 3)
        if self._A is None:
            return Q.copy() if len(self._P) == 0 else np.repeat(self._P[:1], len(Q), axis=0)
        D = Q[:, None, :] - self._A[None, :, :]               # (M,S,3)
        u = (D * self._V[None, :, :]).sum(axis=2) / self._VV[None, :]
        u = np.where(self._degenerate[None, :], 0.0, np.clip(u, 0.0, 1.0))
        C = self._A[None, :, :] + u[:, :, None] * self._V[None, :, :]
        d2 = ((C - Q[:, None, :]) ** 2).sum(axis=2)
        best = d2.argmin(axis=1)
        return C[np.arange(len(Q)), best]


def _geodesic_on_mesh(mesh_fn, mesh_dag, seed, iters, relax=_GEO_RELAX):
    """メッシュ表面に沿った最短経路 (測地線) を折れ線で求める。

    ``seed`` の両端は固定したまま、

      1. 各点を両隣の中点へ寄せる (曲線を縮める向きの力)
      2. メッシュ表面へ投影して戻す (面から離れないようにする)
      3. 弧長で並べ直す (点が片寄るのを防ぐ)

    を繰り返すだけ。これは曲線短縮流そのもので、両端を固定していれば
    測地線 = 「面の上をまっすぐ進む線」に収束する。サブディビジョン
    サーフェスが折れ線を平滑化するのと同じ原理なので、仕上がりも滑らか。
    """
    import math as _math
    from .maya_projector import points as project_many

    pts = [list(p) for p in seed]
    n = len(pts)
    if n < 3:
        return pts

    # 移動量がこれ以下になったら収束とみなす
    tol = max(_math.dist(pts[0], pts[-1]), 1e-9) * 1e-4

    for _ in range(max(1, iters)):
        moved = 0.0
        cur = [list(pts[0])]
        for i in range(1, n - 1):
            prv = pts[i - 1]
            nxt = pts[i + 1]
            cur.append([pts[i][c] + relax
                        * ((prv[c] + nxt[c]) * 0.5 - pts[i][c])
                        for c in range(3)])
        cur.append(list(pts[-1]))

        # 平滑化と並べ直しはどちらも面から浮かせるので、投影は
        # まとめて 1 回で済ませる (投影がこの関数の実行時間のほぼ全部)
        cur = _resample_polyline(cur, n)
        nxt_pts = [list(cur[0])]
        projected = project_many(mesh_fn,cur[1:-1])
        for i, q in enumerate(projected,1):
            d = ((q[0] - pts[i][0]) ** 2 + (q[1] - pts[i][1]) ** 2
                 + (q[2] - pts[i][2]) ** 2)
            if d > moved:
                moved = d
            nxt_pts.append(q)
        nxt_pts.append(list(cur[-1]))
        pts = nxt_pts

        if moved < tol * tol:
            break

    return pts


def _fit_spline_handles_to_mesh(cn: RetopoGuideData, sp_idx: int,
                                mesh_name: str,
                                iters: int = _FIT_ITERS,
                                n_samples: int = _FIT_SAMPLES,
                                fixed: Optional[int] = None) -> float:
    """スプラインのハンドルを、カーブ本体がメッシュ表面に載るよう最適化する。

    まず両端を結ぶ **測地線** (メッシュ表面上の最短経路) を折れ線で求め、
    その折れ線を通るようにハンドルを最小二乗で解く。

    旧実装は「今のカーブ上の点をメッシュへ投影したもの」を目標にしていた。
    これには 2 つの穴があった。

    * 目的関数が「面に載っているか」しか見ないので、面の上を横に
      どう遠回りしても誤差はゼロ。まっすぐ進む理由がどこにも無い。
    * その目標を自分自身から作るので、一度横へずれるとそのずれが
      次の反復の目標になり、増幅されていく。

    測地線は両端とメッシュだけで決まるので、この 2 つが同時に消える。
    ハンドルは面から浮いてよい (``surface_binding`` は再構築には
    使われず、実際のサーフェス追従は ``surfaceBindData`` の
    ``rest_offset`` 方式が担うため)。

    Parameters
    ----------
    cn : RetopoGuideData
        カーブネット。
    sp_idx : int
        対象スプライン。
    mesh_name : str
        フィッティング先メッシュ。
    iters : int
        測地線を求める緩和の反復回数。
    n_samples : int
        最小二乗に使う目標点の数 (内部点のみ)。
    fixed : int | None
        1 なら h1 (p0 側)、2 なら h2 (p3 側) を動かさずもう一方だけを解く。
        ユーザーが手で置いたハンドルを尊重するため。

    Returns
    -------
    float
        フィッティング後の平均めり込み距離。メッシュが無い等で
        フィットしなかった場合は -1.0。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import (
        _v3_sub, _v3_add, _v3_scale, _v3_dot, _v3_len, _v3_normalize)

    if not (mesh_name and cmds.objExists(mesh_name)):
        return -1.0
    if sp_idx < 0 or sp_idx >= len(cn.splines):
        return -1.0

    sp = cn.splines[sp_idx]
    if any(i >= len(cn.positions) for i in sp):
        return -1.0
    if fixed is None:
        # 手で置かれたハンドルは動かさない。両方手動なら何もしない。
        m1 = sp[1] in cn.manual_handles
        m2 = sp[2] in cn.manual_handles
        if m1 and m2:
            return -1.0
        fixed = 1 if m1 else (2 if m2 else None)

    from .maya_projector import points as project_many
    from Aru_RetopoTool.hard_surface import straight_fit
    if straight_fit(cn,sp_idx,mesh_name):return 0.
    mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
    p0 = list(cn.positions[sp[0]])
    p3 = list(cn.positions[sp[3]])
    chord = _v3_len(_v3_sub(p3, p0))
    if chord < 1e-9:
        return -1.0

    n0 = _get_normal_at_point(mesh_fn, p0)
    n3 = _get_normal_at_point(mesh_fn, p3)

    h1 = list(cn.positions[sp[1]])
    h2 = list(cn.positions[sp[2]])

    def _tangential(vec, nrm, fallback):
        """vec から法線方向成分を除いて接ベクトルにする。

        旧実装はここで無条件に元の長さへ戻していたが、それが横揺れの
        一因だった。法線とほぼ平行なベクトルは接平面へ倒すとほぼ消える
        ので、そこへ元の長さを掛け戻すと横方向へ大きく振れてしまう。
        倒れた量が小さいときだけ長さを戻し (これをしないとカーブが
        内側に寄ってめり込む)、大きく倒れたときは代替の向きを使う。
        """
        L = _v3_len(vec)
        if L < 1e-9:
            return list(fallback)
        t = _v3_sub(vec, _v3_scale(nrm, _v3_dot(vec, nrm)))
        tl = _v3_len(t)
        if tl < L * 0.25:
            # ほぼ法線方向 = 向きの情報が無い。測地線の向きを使う
            return _v3_scale(_v3_normalize(fallback), L)
        if tl < L * _TANGENT_RESTORE_MIN:
            return t
        return _v3_scale(t, L / tl)

    def _mesh_error(a1, a2):
        """カーブ上のサンプルとメッシュ表面との平均距離 (戻り値用)。"""
        tot = 0.0
        samples = [_bezier_point(p0,a1,a2,p3,k/(n_samples+1.0)) for k in range(1,n_samples+1)]
        for b,q in zip(samples,project_many(mesh_fn,samples)):
            tot += _v3_len(_v3_sub(q, b))
        return tot / n_samples

    # --- 1. 今のカーブを種にして測地線を求める ------------------------
    n_seg = (_GEO_DRAFT_SEGMENTS if iters <= _FIT_DRAFT_ITERS
             else _GEO_SEGMENTS)
    seed = [list(p0)]
    samples = [_bezier_point(p0,h1,h2,p3,k/float(n_seg)) for k in range(1,n_seg)]
    seed.extend(project_many(mesh_fn,samples))
    seed.append(list(p3))

    path = _geodesic_on_mesh(mesh_fn, mesh_dag, seed, iters)
    from .path_fit import fit as native_path_fit
    fitted = native_path_fit([p0,h1,h2,p3],path,[n0,n3],n_samples,
                             _FIT_PARAM_ROUNDS,fixed,_FIT_EPS_RATIO,_TANGENT_RESTORE_MIN)
    if fitted is not None:
        best_h1,best_h2=fitted
        cn.positions[sp[1]]=best_h1;cn.positions[sp[2]]=best_h2
        for hi in (sp[1],sp[2]):
            _q,fi,bc=_closest_point_on_mesh(mesh_fn,mesh_dag,cn.positions[hi])
            cn.surface_binding[hi]=(fi,bc)
        return _mesh_error(best_h1,best_h2)
    proj = _PolylineProjector(path)
    ts = [k / (n_samples + 1.0) for k in range(1, n_samples + 1)]

    def _sample_and_project(a1, a2):
        """カーブ上のサンプルと、それぞれに最も近い測地線上の点をまとめて返す。"""
        bs = [_bezier_point(p0, a1, a2, p3, t) for t in ts]
        gs = proj.closest_many(bs).tolist()
        return bs, gs

    # 測地線の出だし / 終わりの向き。接線が潰れたときの代替に使う
    gd0 = _v3_sub(path[1], path[0]) if len(path) > 1 else _v3_sub(p3, p0)
    gd3 = _v3_sub(path[-2], path[-1]) if len(path) > 1 else _v3_sub(p0, p3)
    if _v3_len(gd0) < 1e-9:
        gd0 = _v3_sub(p3, p0)
    if _v3_len(gd3) < 1e-9:
        gd3 = _v3_sub(p0, p3)

    min_len = chord * 0.05
    max_len = chord * 0.75
    eps = chord * _FIT_EPS_RATIO

    def _path_error(a1, a2):
        """カーブと測地線との平均距離。

        測地線はメッシュの上にあるので、これを小さくすれば
        「面に載る」と「まっすぐ進む」が同時に満たされる。
        メッシュへの問い合わせが要らないので反復を安く回せる。
        """
        tot = 0.0
        bs, gs = _sample_and_project(a1, a2)
        for b, g in zip(bs, gs):
            tot += _v3_len(_v3_sub(g, b))
        return tot / n_samples

    def _consider(a1, a2):
        nonlocal best_err, best_h1, best_h2
        e = _path_error(a1, a2)
        if best_err is None or e < best_err:
            best_err = e
            best_h1, best_h2 = list(a1), list(a2)
        return e

    # --- 2. 測地線を目標に、ハンドルを反復で追い込む -------------------
    #
    # 目標点を「カーブ上の点にいちばん近い測地線上の点」にするのが要。
    # 旧実装のように「メッシュへ最近接投影」だと横方向が自由なままだが、
    # 測地線へ投影すれば横は釘付けになり、めり込みの補正だけが残る。
    #
    # ここでは接平面への引き戻しをしない。反復の中でやると
    # 「倒す → 次の目標がずれる → もっと倒れる」という暴走が起きて、
    # 片方のハンドルが潰れもう片方が上限に張り付く (実測)。
    best_h1, best_h2 = list(h1), list(h2)
    best_err = None

    for _ in range(_FIT_PARAM_ROUNDS):
        # 目標点と誤差を 1 回のなめで両方求める
        rows = []
        err = 0.0
        bs, gs = _sample_and_project(h1, h2)
        for t, b, g in zip(ts, bs, gs):
            err += _v3_len(_v3_sub(g, b))
            rows.append((t, g))
        err /= n_samples
        if best_err is None or err < best_err:
            best_err = err
            best_h1, best_h2 = list(h1), list(h2)
        if err <= eps:
            break

        a11 = a12 = a22 = 0.0
        r1 = [0.0, 0.0, 0.0]
        r2 = [0.0, 0.0, 0.0]
        for t, q in rows:
            u = 1.0 - t
            c1 = 3.0 * u * u * t
            c2 = 3.0 * u * t * t
            a11 += c1 * c1
            a12 += c1 * c2
            a22 += c2 * c2
            for k in range(3):
                rhs = q[k] - (u ** 3) * p0[k] - (t ** 3) * p3[k]
                r1[k] += c1 * rhs
                r2[k] += c2 * rhs
        det = a11 * a22 - a12 * a12
        if fixed == 1:
            # h1 固定: h2 だけを 1 未知数で解く
            if a22 < 1e-12:
                break
            d1 = _v3_sub(h1, p0)
            d2 = [(r2[k] - a12 * d1[k]) / a22 - p3[k] for k in range(3)]
        elif fixed == 2:
            if a11 < 1e-12:
                break
            d2 = _v3_sub(h2, p3)
            d1 = [(r1[k] - a12 * d2[k]) / a11 - p0[k] for k in range(3)]
        else:
            if abs(det) < 1e-12:
                break
            d1 = [(a22 * r1[k] - a12 * r2[k]) / det - p0[k] for k in range(3)]
            d2 = [(a11 * r2[k] - a12 * r1[k]) / det - p3[k] for k in range(3)]

        # 長さだけは常識的な範囲に収める (発散よけの安全弁)
        for d, is_fixed in ((d1, fixed == 1), (d2, fixed == 2)):
            if is_fixed:
                continue
            L = _v3_len(d)
            if L > max_len:
                s = max_len / L
                d[0] *= s
                d[1] *= s
                d[2] *= s
            elif L < min_len and L > 1e-9:
                s = min_len / L
                d[0] *= s
                d[1] *= s
                d[2] *= s
        nh1 = _v3_add(p0, d1)
        nh2 = _v3_add(p3, d2)
        if (_v3_len(_v3_sub(nh1, h1)) < eps
                and _v3_len(_v3_sub(nh2, h2)) < eps):
            h1, h2 = nh1, nh2
            break
        h1, h2 = nh1, nh2

    # 最後の解も候補に入れる
    _consider(h1, h2)

    # --- 3. 最後に一度だけ接平面へ引き戻す ----------------------------
    #
    # カーブが面に載っていれば端点の接線は自然にほぼ接平面上に来るので、
    # ここでの補正はごくわずか。悪化するなら採用しない。
    t1 = (_v3_sub(best_h1, p0) if fixed == 1
          else _tangential(_v3_sub(best_h1, p0), n0, gd0))
    t2 = (_v3_sub(best_h2, p3) if fixed == 2
          else _tangential(_v3_sub(best_h2, p3), n3, gd3))
    _consider(_v3_add(p0, t1), _v3_add(p3, t2))

    cn.positions[sp[1]] = list(best_h1)
    cn.positions[sp[2]] = list(best_h2)
    # surface_binding はメタデータとして最近接 face/bary を入れておく
    for hi in (sp[1], sp[2]):
        _q, fi, bc = _closest_point_on_mesh(
            mesh_fn, mesh_dag, cn.positions[hi])
        cn.surface_binding[hi] = (fi, bc)
    return _mesh_error(best_h1, best_h2)


def _translate_manual_handles(cn: RetopoGuideData, ep: int, delta) -> None:
    """EP が動いたとき、その側の手動ハンドルを平行移動で追従させる。"""
    if not cn.manual_handles:
        return
    for sp in cn.splines:
        for e, h in ((sp[0], sp[1]), (sp[3], sp[2])):
            if e == ep and h in cn.manual_handles and h < len(cn.positions):
                cn.positions[h] = [cn.positions[h][k] + delta[k] for k in range(3)]


def _find_mirror_handle(cn: RetopoGuideData, mesh_name: str, handle: int) -> Optional[int]:
    """*handle* の対称側にあるハンドルを返す。無ければ None。

    ハンドルは面から浮いているので位置では探さない。自分の EP と反対側の
    EP の対称 EP を求め、その 2 点を繋ぐスプラインの「対称 EP 側」の
    ハンドルを対応させる。自分自身が返る (面上の対称なスプライン) 場合は None。
    """
    if not _sym.is_enabled():
        return None
    tol = _mirror_tol(mesh_name)
    for sp in cn.splines:
        if handle == sp[1]:
            ep_own, ep_other = sp[0], sp[3]
        elif handle == sp[2]:
            ep_own, ep_other = sp[3], sp[0]
        else:
            continue
        m_own = _sym.find_mirror_ep(cn, mesh_name, ep_own, tol)
        m_other = _sym.find_mirror_ep(cn, mesh_name, ep_other, tol)
        if m_own is None or m_other is None:
            return None
        for sq in cn.splines:
            if sq[0] == m_own and sq[3] == m_other:
                cand = sq[1]
            elif sq[3] == m_own and sq[0] == m_other:
                cand = sq[2]
            else:
                continue
            return None if cand == handle else cand
        return None
    return None


def _add_spline_to_cn(cn: RetopoGuideData, mesh_name: str,
                      ep_a: int, ep_b: int) -> int:
    """ep_a → ep_b 間に spline を追加し、ハンドルをメッシュ接線方向で配置する。
    追加した spline のインデックスを返す。"""
    normal = None
    if mesh_name and cmds.objExists(mesh_name):
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
        # EP 中点での面法線を取得
        mid = [(cn.positions[ep_a][k] + cn.positions[ep_b][k]) * 0.5
               for k in range(3)]
        normal = _get_normal_at_point(mesh_fn, mid)
    sp_idx = cn.add_spline_two_endpoints(ep_a, ep_b, surface_normal=normal)
    _fit_spline_handles_to_mesh(cn, sp_idx, mesh_name)
    cn.classify_endpoints()
    return sp_idx


# ---------------------------------------------------------------------------
# 対称作成
# ---------------------------------------------------------------------------

def _mirror_tol(mesh_name: str) -> float:
    """対称位置の EP を「同じ点」とみなす許容距離。

    スナップ半径をそのまま使うと粗すぎて隣の EP を掴むので、その 1/4 にする。
    """
    return _snap_radius(mesh_name) * 0.25


def _project_on_mesh(mesh_name: str, pos):
    """*pos* をメッシュ面に落として (位置, face, bary) を返す。

    メッシュが無ければ *pos* をそのまま返す。
    """
    if mesh_name and cmds.objExists(mesh_name):
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
        return _closest_point_on_mesh(mesh_fn, mesh_dag, pos)
    return list(pos), -1, []


def _snap_pos_to_plane(mesh_name: str, pos):
    """*pos* を対称面の上へ落とし、メッシュ面にも載せ直して返す。

    対称面へ落とす → メッシュへ投影 → もう一度対称面へ落とす、を繰り返す。
    メッシュへの投影で面から少しずれるので、最後にもう一度面へ載せる。
    戻り値は (位置, face, bary)。
    """
    p = _sym.project_to_plane(pos, mesh_name)
    for _ in range(2):
        p, face_idx, bary = _project_on_mesh(mesh_name, p)
        p = _sym.project_to_plane(p, mesh_name)
    return p, face_idx, bary


def _apply_symmetry_constraint(mesh_name: str, pos, side=None):
    """対称化が有効なときの位置の補正。

    - 対称面に近いときは面の上へ吸着させる
    - *side* (ドラッグ開始時にいた側の符号) を跨ごうとしたら面の上で止める

    戻り値は (位置, face_idx, bary, 面の上か)。
    対称化がオフなら *pos* をメッシュに載せただけの結果を返す。
    """
    if not _sym.is_enabled():
        p, f, b = _project_on_mesh(mesh_name, pos)
        return p, f, b, False

    coord = _sym.plane_coord(pos, mesh_name)
    if coord is None:
        p, f, b = _project_on_mesh(mesh_name, pos)
        return p, f, b, False

    # 「面からの距離」の許容値。mirror 判定は往復距離なので半分にする。
    tol = _mirror_tol(mesh_name) * 0.5
    crossed = (side is not None and side != 0.0
               and coord * side < 0.0)
    if abs(coord) <= tol or crossed:
        p, f, b = _snap_pos_to_plane(mesh_name, pos)
        return p, f, b, True

    p, f, b = _project_on_mesh(mesh_name, pos)
    return p, f, b, False


def _mirror_ep_get_or_create(cn: RetopoGuideData, mesh_name: str, ep: int):
    """*ep* の対称位置にある EP を返す。無ければ作る。

    対称面の上にある EP は自分自身を返す (二重に作らない)。
    対称化がオフなら None。

    反転先が既存カーブの途中にあたる場合は、そのカーブを分割して
    交点 EP を作る。カーブの途中にホバーして点を足したときに、
    反対側だけカーブから浮いた点になってしまうのを防ぐため。
    """
    if not _sym.is_enabled() or ep is None or ep >= len(cn.positions):
        return None

    tol = _mirror_tol(mesh_name)
    found = _sym.find_mirror_ep(cn, mesh_name, ep, tol)
    if found is not None:
        return found

    mpos = _sym.mirror_point(cn.positions[ep], mesh_name)
    face_idx, bary = -1, []
    if mesh_name and cmds.objExists(mesh_name):
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
        mpos, face_idx, bary = _closest_point_on_mesh(mesh_fn, mesh_dag, mpos)

    hit = _nearest_spline_t_excluding(cn, mpos, tol * 2.0, exclude_ep=ep,
                                      mesh_name=mesh_name)
    if hit is not None:
        sp_idx, t = hit
        m_ep = _split_spline_at(cn, sp_idx, t, mesh_name)
        # 分割点はカーブ上の位置なので、左右が厳密には対応しない。
        # 反転位置そのものへ寄せておかないと、あとで相方を探すときに
        # 許容距離から外れて見つからなくなる。
        cn.move_cv(m_ep, mpos)
        if face_idx >= 0:
            cn.surface_binding[m_ep] = (face_idx, bary)
        _recompute_handles_for_ep(cn, m_ep, mesh_name)
        return m_ep

    if face_idx >= 0:
        return cn.add_cv(mpos, surface=(face_idx, bary))
    return cn.add_cv(mpos)


def _nearest_spline_t_excluding(cn: RetopoGuideData, point: list, radius: float,
                                exclude_ep: int = None,
                                mesh_name: str = ""):
    """*point* の近くを通るスプラインの (index, t) を返す。無ければ None。

    端点のごく近くで当たった場合は None を返す (分割すると元の EP と
    ほぼ同じ位置に無駄な点ができるため)。*exclude_ep* を端点に持つ
    スプラインは対象外にする。

    *mesh_name* を渡すと、太ももと尻尾のように密着した別パーツの
    カーブを掴まないよう法線の向きでも絞り込む。探索半径はメッシュ
    AABB 基準なので、パーツ間の隙間より広くなりうるため。
    """
    best_sp = -1
    best_t = 0.5
    best_d2 = radius * radius
    N = 32
    mesh_fn = None
    if mesh_name and cmds.objExists(mesh_name):
        try:
            mesh_fn, _dag = _get_mesh_fn(mesh_name)
        except Exception:
            mesh_fn = None
    for si, sp in enumerate(cn.splines):
        if any(i >= len(cn.positions) for i in sp):
            continue
        if exclude_ep is not None and (sp[0] == exclude_ep
                                       or sp[3] == exclude_ep):
            continue
        p0, p1, p2, p3 = [cn.positions[i] for i in sp]
        for k in range(N + 1):
            t = k / float(N)
            bp = _bezier_point(p0, p1, p2, p3, t)
            d2 = sum((bp[j] - point[j]) ** 2 for j in range(3))
            if d2 < best_d2:
                # 最良を更新するときだけ判定する (1 操作あたり数回で済む)
                if (mesh_fn is not None
                        and not _same_surface_side(mesh_fn, point, bp)):
                    continue
                best_d2 = d2
                best_sp = si
                best_t = t
    if best_sp < 0:
        return None

    import numpy as _np
    sp = cn.splines[best_sp]
    pts = [_np.asarray(cn.positions[i], dtype=float) for i in sp]
    _cp, t_ref, dist = closest_point_on_bezier(
        pts[0], pts[1], pts[2], pts[3],
        _np.asarray(point, dtype=float), t_hint=best_t)
    if dist > radius:
        return None
    if t_ref < 0.05 or t_ref > 0.95:
        return None
    return (best_sp, float(t_ref))


def _mirror_new_ep(cn: RetopoGuideData, mesh_name: str, ep: int):
    """単独ポイントを作ったときの対称側を作る。

    作った (または既にあった) 対称 EP のインデックスを返す。
    自分自身と同じなら None。
    """
    m = _mirror_ep_get_or_create(cn, mesh_name, ep)
    if m is None or m == ep:
        return None
    cn.mark_standalone(m)
    return m


def _mirror_spline(cn: RetopoGuideData, mesh_name: str,
                   ep_a: int, ep_b: int, split_tol: float):
    """*ep_a*-*ep_b* のスプラインの対称側を作る。

    対称化がオフ、または対称側が元と同一なら何もしない。
    """
    if not _sym.is_enabled():
        return None
    ma = _mirror_ep_get_or_create(cn, mesh_name, ep_a)
    mb = _mirror_ep_get_or_create(cn, mesh_name, ep_b)
    if ma is None or mb is None:
        return None
    if ma == mb:
        return None
    if ma == ep_a and mb == ep_b:
        # 対称面をまたがない = 元のスプラインと同じもの
        return None
    if _spline_exists(cn, ma, mb):
        return None
    sp_idx = _add_spline_to_cn(cn, mesh_name, ma, mb)
    _split_splines_at_intersections(cn, sp_idx, mesh_name, split_tol)
    cn.sync_standalone()
    return sp_idx


def _recompute_handles_for_ep(cn: RetopoGuideData, ep: int,
                              mesh_name: str, draft: bool = False) -> None:
    """
    EP に接続する全スプラインのハンドルを再計算する。
    Pixar 方式: EP→反対側EP 方向をメッシュ接平面に投影して、
    その方向にセグメント長の 1/3 だけオフセットする。
    そのうえで、カーブ本体がメッシュ表面に載るようハンドルを最適化する。

    *draft* が True のときはフィッティングを粗く済ませる (ドラッグ中用)。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import (_v3_sub, _v3_add, _v3_scale,
                                _v3_dot, _v3_len, _v3_lerp)
    have_mesh = mesh_name and cmds.objExists(mesh_name)
    mesh_fn = mesh_dag = None
    if have_mesh:
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)

    for sp_idx, sp in enumerate(cn.splines):
        if sp[0] != ep and sp[3] != ep:
            continue
        # 手で置いたハンドルは初期化しない (EP に追従する平行移動は
        # _translate_manual_handles が担う)。もう一方だけ初期化してフィットする。
        keep1 = sp[1] in cn.manual_handles
        keep2 = sp[2] in cn.manual_handles
        if keep1 and keep2:
            continue
        p0 = cn.positions[sp[0]]
        p3 = cn.positions[sp[3]]
        seg = _v3_sub(p3, p0)
        seg_len = _v3_len(seg)
        if seg_len < 1e-12:
            continue

        if have_mesh:
            # 各 EP での法線を取得し、接平面投影
            n0 = _get_normal_at_point(mesh_fn, p0)
            n3 = _get_normal_at_point(mesh_fn, p3)
            # p0 側ハンドル: seg を n0 の接平面に投影
            d0 = _v3_dot(seg, n0)
            tang0 = _v3_sub(seg, _v3_scale(n0, d0))
            l0 = _v3_len(tang0)
            if l0 > 1e-8:
                tang0 = _v3_scale(tang0, 1.0 / l0)
            else:
                tang0 = _v3_scale(seg, 1.0 / seg_len)
            # p3 側ハンドル: -seg を n3 の接平面に投影
            neg_seg = _v3_scale(seg, -1.0)
            d3 = _v3_dot(neg_seg, n3)
            tang3 = _v3_sub(neg_seg, _v3_scale(n3, d3))
            l3 = _v3_len(tang3)
            if l3 > 1e-8:
                tang3 = _v3_scale(tang3, 1.0 / l3)
            else:
                tang3 = _v3_scale(neg_seg, 1.0 / seg_len)
            # 初期値として接平面上に置き、そこからフィッティングで詰める
            if not keep1:
                cn.positions[sp[1]] = _v3_add(p0, _v3_scale(tang0, seg_len / 3.0))
            if not keep2:
                cn.positions[sp[2]] = _v3_add(p3, _v3_scale(tang3, seg_len / 3.0))
            if draft:
                _fit_spline_handles_to_mesh(
                    cn, sp_idx, mesh_name,
                    iters=_FIT_DRAFT_ITERS, n_samples=_FIT_DRAFT_SAMPLES)
            else:
                _fit_spline_handles_to_mesh(cn, sp_idx, mesh_name)
        else:
            if not keep1:
                cn.positions[sp[1]] = _v3_lerp(p0, p3, 1.0 / 3.0)
            if not keep2:
                cn.positions[sp[2]] = _v3_lerp(p0, p3, 2.0 / 3.0)


def _smooth_moved_ep_routes(cn, moved, mesh_name):
    """Finish an EP move with continuous surface tangents, without moving EPs.

    Include the other ends of the moved segments so their joins remain smooth
    too. Explicitly edited handles retain the existing manual-fit behavior.
    """
    if not mesh_name or not cmds.objExists(mesh_name):
        return
    from .curve_net_relax import _smooth_junctions
    moved = set(moved) & set(cn.endpoint_indices())
    affected = set(moved)
    for a, _, _, b in cn.splines:
        if a in moved or b in moved:
            affected.update((a, b))
    mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
    _smooth_junctions(cn, {ep: 1. for ep in affected}, mesh_fn, mesh_dag,
                      respect_manual=True)


def _sync_ep_positions_back(node_name: str) -> bool:
    """
    controlPoints デルタを読み取り、netData に焼き込んで controlPoints をゼロにする。
    変更があった場合 True を返す。
    """
    acc = RetopoGuideAccessor(node_name)
    if not acc.exists:
        return False

    # デフォーマ駆動中の CP はポーズ空間の
    # 補正 (PSD) であり、レスト形状へ焼き込むのは誤り。
    # 焼き込むと補正がレストの一部になり、
    # バインドポーズでも常に効いてしまう。
    if is_pose_driven(node_name):
        return False

    cn = acc.read()

    changed = False
    moved_eps = []      # [(ep_idx, new_pos, old_pos)]
    moved_handles = []  # [pos_idx]
    ep_set = cn.endpoint_indices()

    for i in range(len(cn.positions)):
        try:
            dx = cmds.getAttr("{}.controlPoints[{}].xValue".format(
                node_name, i))
            dy = cmds.getAttr("{}.controlPoints[{}].yValue".format(
                node_name, i))
            dz = cmds.getAttr("{}.controlPoints[{}].zValue".format(
                node_name, i))
        except Exception:
            continue
        if abs(dx) > 1e-6 or abs(dy) > 1e-6 or abs(dz) > 1e-6:
            old = cn.positions[i][:]
            cn.positions[i] = [old[0] + dx, old[1] + dy, old[2] + dz]
            if i in ep_set:
                moved_eps.append((i, cn.positions[i], old))
            else:
                moved_handles.append(i)
                # コンポーネントモードで動かしたハンドルも手動扱いにする
                cn.mark_manual_handle(i)
            changed = True

    if changed:
        # EP が移動: 直接移動されていないハンドルにデルタを伝播
        handle_moved_set = set(moved_handles)
        for ep_idx, new_pos, old_pos in moved_eps:
            delta = [new_pos[k] - old_pos[k] for k in range(3)]
            for sp in cn.splines:
                if sp[0] == ep_idx and sp[1] not in handle_moved_set:
                    cn.positions[sp[1]] = [cn.positions[sp[1]][k] + delta[k]
                                           for k in range(3)]
                if sp[3] == ep_idx and sp[2] not in handle_moved_set:
                    cn.positions[sp[2]] = [cn.positions[sp[2]][k] + delta[k]
                                           for k in range(3)]
        _commit_net_data(node_name, cn)
    return changed


def _nearest_spline_t(cn: RetopoGuideData, world_pt: list) -> Optional[tuple]:
    """
    world_pt に最も近い spline の (sp_idx, t) を返す。
    32 サンプルの粗探索 → Newton-Raphson リファインで高精度な t を得る。
    """
    if not cn.splines:
        return None
    import numpy as _np
    best_sp: Optional[int] = None
    best_t  = 0.5
    best_d2 = 1e30
    N = 32
    for si, sp in enumerate(cn.splines):
        if any(i >= len(cn.positions) for i in sp):
            continue
        p0, p1, p2, p3 = [cn.positions[i] for i in sp]
        for k in range(N + 1):
            t  = k / N
            u  = 1.0 - t
            bx = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
            by = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
            bz = u**3*p0[2] + 3*u**2*t*p1[2] + 3*u*t**2*p2[2] + t**3*p3[2]
            dx = world_pt[0]-bx; dy = world_pt[1]-by; dz = world_pt[2]-bz
            d2 = dx*dx + dy*dy + dz*dz
            if d2 < best_d2:
                best_d2 = d2
                best_sp = si
                best_t  = t
    # Newton-Raphson リファインで正確な t を取得
    if best_sp is not None:
        sp = cn.splines[best_sp]
        p0 = _np.asarray(cn.positions[sp[0]], dtype=float)
        p1 = _np.asarray(cn.positions[sp[1]], dtype=float)
        p2 = _np.asarray(cn.positions[sp[2]], dtype=float)
        p3 = _np.asarray(cn.positions[sp[3]], dtype=float)
        Q  = _np.asarray(world_pt, dtype=float)
        _, best_t, _ = closest_point_on_bezier(p0, p1, p2, p3, Q,
                                               t_hint=best_t)
    return (best_sp, best_t) if best_sp is not None else None


#: カーブをスクリーン空間で掴めるとみなす画面上の距離 (ピクセル)
_SCREEN_SNAP_PX = 12.0

#: EP をスクリーン空間で掴めるとみなす画面上の距離 (ピクセル)
#: EP マーカーは 8〜14px で描かれるので、それより少し広めに取る。
_EP_SNAP_PX = 16.0


def _find_ep_under_screen(cn: "RetopoGuideData", sx: float, sy: float,
                          tol_px: float = _EP_SNAP_PX,
                          mesh_name: str = "") -> Optional[int]:
    """スクリーン座標 (sx, sy) の真下にある EP を返す。

    EP スナップも 3D 距離ではなく画面上の距離で判定する。3D 距離だと
    メッシュが大きい場合にスナップ半径が広がりすぎ、画面上では明らかに
    離れた EP に吸い込まれてしまう (結果として二重スプラインになったり、
    始点に戻ったと判定されて操作がキャンセルされたりする)。
    """
    if not cn.splines:
        return None
    ep_set = cn.endpoint_indices()
    best = None
    best_d2 = tol_px * tol_px
    vis = make_visibility_test(mesh_name) if mesh_name else None
    for ep in ep_set:
        if ep >= len(cn.positions):
            continue
        s = _world_to_screen(cn.positions[ep])
        if s is None:
            continue
        d2 = (s[0] - sx) ** 2 + (s[1] - sy) ** 2
        if d2 < best_d2:
            # 見えていない (メッシュの裏側の) EP は候補にしない。
            # best_d2 は更新しない。更新すると、この後に見つかる
            # 「少し遠いが見えている」候補まで弾かれてしまう。
            if vis is not None and not vis(cn.positions[ep]):
                continue
            best_d2 = d2
            best = ep
    return best


def _screen_to_view_plane(sx: float, sy: float, anchor) -> Optional[list]:
    """スクリーン座標のレイを、*anchor* を通り視線に直交する平面と交差させる。

    ハンドルはメッシュから浮いていてよいので、面に投影するとアーティストの
    意図した接線が作れない。掴んだ時点の奥行きを保ったまま画面と平行に動かす。
    """
    try:
        view = omui.M3dView.active3dView()
        origin = om.MPoint()
        direction = om.MVector()
        view.viewToWorld(int(sx), int(sy), origin, direction)
        # 視線方向 (パースではレイと違うのでカメラの向きを別に取る)
        cam = om.MDagPath()
        view.getCamera(cam)
        cam_fn = om.MFnCamera(cam)
        vdir = cam_fn.viewDirection(om.MSpace.kWorld)
    except Exception:
        return None
    denom = direction.x * vdir.x + direction.y * vdir.y + direction.z * vdir.z
    if abs(denom) < 1e-12:
        return None
    ax, ay, az = anchor
    t = ((ax - origin.x) * vdir.x + (ay - origin.y) * vdir.y
         + (az - origin.z) * vdir.z) / denom
    return [origin.x + direction.x * t, origin.y + direction.y * t,
            origin.z + direction.z * t]


def _find_handle_under_screen(cn: "RetopoGuideData", sx: float, sy: float,
                              tol_px: float = _EP_SNAP_PX) -> Optional[int]:
    """スクリーン座標の真下にあるハンドル CV を返す。

    ハンドルはメッシュから浮いているので、レイキャストした表面位置との
    3D 距離では捉まえられない。EP と同じく画面上の距離で判定する。
    """
    best = None
    best_d2 = tol_px * tol_px
    for sp in cn.splines:
        for hi in (sp[1], sp[2]):
            if hi >= len(cn.positions):
                continue
            s = _world_to_screen(cn.positions[hi])
            if s is None:
                continue
            d2 = (s[0] - sx) ** 2 + (s[1] - sy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = hi
    return best


def _find_spline_under_screen(cn, sx, sy, tol_px=_SCREEN_SNAP_PX,
                              exclude_eps=None, mesh_name=""):
    from .screen_hit import find_spline
    return find_spline(cn, sx, sy, tol_px, exclude_eps, mesh_name)


def _find_spline_under_screen_scalar(cn: "RetopoGuideData", sx: float, sy: float,
                              tol_px: float = _SCREEN_SNAP_PX,
                              exclude_eps: Optional[set] = None,
                              mesh_name: str = ""
                              ) -> Optional[tuple]:
    """スクリーン座標 (sx, sy) の真下にあるスプラインを探す。

    カーブネットはメッシュ表面に張り付くので、少しでも凸な場所では
    カーブがポリゴンに埋もれる。3D 距離で接続先を判定すると、
    レイキャストで得られる点 (メッシュ表面) と埋もれたカーブの間に
    大きな隔たりが出て掴めない。そこで「カメラから見て重なっていれば
    掴める」ことにして、判定をスクリーン空間で行う。

    Parameters
    ----------
    cn : RetopoGuideData
        カーブネット。
    sx, sy : float
        スクリーン座標。
    tol_px : float
        ヒットとみなす画面上の距離 (ピクセル)。
    exclude_eps : set | None
        この EP を端点に持つスプラインは対象外にする。自分自身に
        繋ぎ直すのを防ぐ。

    Returns
    -------
    tuple | None
        ``(sp_idx, t, world_pt)``。見つからなければ None。
    """
    if not cn.splines:
        return None
    exclude_eps = exclude_eps or set()

    N = 24
    best = None
    best_d2 = tol_px * tol_px
    # 画面上で重なっていても、メッシュの裏側にあって見えていない
    # カーブは掴めないようにする。判定は候補が最良を更新するときだけ
    # 行うので、1 フレームあたり数回で済む。
    vis = make_visibility_test(mesh_name) if mesh_name else None

    for si, sp in enumerate(cn.splines):
        if any(i >= len(cn.positions) for i in sp):
            continue
        if sp[0] in exclude_eps or sp[3] in exclude_eps:
            continue
        p0, p1, p2, p3 = [cn.positions[i] for i in sp]

        # カーブをスクリーンへ投影
        scr = []
        for k in range(N + 1):
            t = k / N
            wp = _bezier_point(p0, p1, p2, p3, t)
            s = _world_to_screen(wp)
            scr.append((t, s, wp) if s is not None else (t, None, wp))

        # 隣り合う投影点を結ぶ線分と (sx, sy) の距離を測る
        for k in range(N):
            t0, s0, w0 = scr[k]
            t1, s1, w1 = scr[k + 1]
            if s0 is None or s1 is None:
                continue
            ex = s1[0] - s0[0]
            ey = s1[1] - s0[1]
            L2 = ex * ex + ey * ey
            if L2 < 1e-12:
                u = 0.0
            else:
                u = ((sx - s0[0]) * ex + (sy - s0[1]) * ey) / L2
                u = max(0.0, min(1.0, u))
            cx = s0[0] + ex * u
            cy = s0[1] + ey * u
            d2 = (sx - cx) ** 2 + (sy - cy) ** 2
            if d2 < best_d2:
                t_hit = t0 + (t1 - t0) * u
                # 端点そのものは EP スナップの仕事なので避ける。
                # ここで best_d2 を更新してはいけない。更新すると、
                # この後に見つかる「少し遠いが有効な」候補まで
                # 弾かれてしまい、カーブ端付近で何も掴めなくなる。
                if t_hit < 0.04 or t_hit > 0.96:
                    continue
                wp = _bezier_point(p0, p1, p2, p3, t_hit)
                if vis is not None and not vis(wp):
                    continue
                best_d2 = d2
                best = (si, t_hit, wp)

    return best


def _spline_exists(cn: "RetopoGuideData", ep_a: int, ep_b: int) -> bool:
    """ep_a と ep_b を結ぶスプラインが既に存在するか。"""
    for sp in cn.splines:
        if (sp[0] == ep_a and sp[3] == ep_b) or (sp[0] == ep_b and sp[3] == ep_a):
            return True
    return False


def _screen_dist(world_pt, screen) -> Optional[float]:
    """world_pt の投影位置と screen 座標のピクセル距離。投影不能なら None。"""
    s = _world_to_screen(world_pt)
    if s is None:
        return None
    return math.hypot(s[0] - screen[0], s[1] - screen[1])


def _resolve_drop_target(cn: "RetopoGuideData", sel_ep: Optional[int],
                         screen: tuple, mesh_name: str = "") -> tuple:
    """スクリーン座標 screen での接続先を決める。

    ドラッグ中のハイライト表示と、リリース時の確定処理の両方から
    呼ぶことで「光っているのに繋がらない」という食い違いを防ぐ。

    Returns
    -------
    tuple
        ``(snapped_ep, hit, already_ep)``。
        ``snapped_ep`` は接続先の既存 EP、``hit`` はカーブ上の
        ``(sp_idx, t, world_pt)``。非 None になるのはどちらか一方だけ。
        ``snapped_ep == sel_ep`` の場合は「始点に戻した = キャンセル」。
        ``already_ep`` は「既に sel_ep と繋がっているのでスナップ先から
        外した EP」。両方 None かつ ``already_ep`` が非 None なら、
        新規 EP を作らずキャンセルすべき。
    """
    sx, sy = screen
    excl = {sel_ep} if sel_ep is not None else None
    hit = _find_spline_under_screen(cn, sx, sy, exclude_eps=excl,
                                    mesh_name=mesh_name)
    snapped = _find_ep_under_screen(cn, sx, sy, mesh_name=mesh_name)
    already = None

    # 既に繋がっている EP へのスナップは二重スプラインになるだけで
    # 見た目が変わらない (= ユーザーには「繋がらない」ように見える)。
    # ハイライトしていたカーブ上に交点を作る方へ回す。
    if (snapped is not None and sel_ep is not None and snapped != sel_ep
            and _spline_exists(cn, sel_ep, snapped)):
        already = snapped
        snapped = None

    # 両方が候補になる場合は画面上でカーソルに近い方を採用する
    if snapped is not None and hit is not None:
        d_ep = _screen_dist(cn.positions[snapped], screen)
        d_hv = _screen_dist(hit[2], screen)
        if d_ep is not None and d_hv is not None and d_hv < d_ep:
            snapped = None
        else:
            hit = None

    return snapped, hit, already


def _split_spline_at(cn: "RetopoGuideData", sp_idx: int, t: float,
                     mesh_name: str) -> int:
    """スプライン sp_idx をパラメータ t で分割し、交点 EP を返す。

    分割点はメッシュ表面へ投影する。カーブがメッシュに埋もれている状態で
    掴んだ場合、投影によってカーブネットが表面へ引き戻される。分割後は
    両側のハンドルを張り直して、元の形状からのズレを最小限にする。

    Parameters
    ----------
    cn : RetopoGuideData
        カーブネット。
    sp_idx : int
        分割するスプライン。
    t : float
        分割パラメータ (0..1)。
    mesh_name : str
        投影先メッシュ。空なら投影しない。

    Returns
    -------
    int
        生成された交点 EP のインデックス。
    """
    new_ep, sp_a, sp_b = cn.split_spline(sp_idx, t)
    # 分割でハンドルは作り直されるので、元の手動指定は引き継がない
    cn.clear_manual_handles(cn.splines[sp_a][1:3])
    if sp_b is not None and sp_b < len(cn.splines):
        cn.clear_manual_handles(cn.splines[sp_b][1:3])

    if mesh_name and cmds.objExists(mesh_name):
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
        snap_pt, face_idx, bary = _closest_point_on_mesh(
            mesh_fn, mesh_dag, cn.positions[new_ep])
        cn.positions[new_ep] = snap_pt
        cn.surface_binding[new_ep] = (face_idx, bary)
        for si in (sp_a, sp_b):
            if si is not None and si < len(cn.splines):
                _fit_spline_handles_to_mesh(cn, si, mesh_name)

    cn.classify_endpoints()
    return new_ep


def _find_nearest_spline(cn: "RetopoGuideData", point: list, radius: float) -> int:
    """point に最も近いスプラインのインデックスを返す。見つからない場合は -1。

    32 サンプルの粗探索で候補を絞り、Newton-Raphson で正確な距離を評価する。
    """
    import numpy as _np
    N = 32
    best_d2 = radius * radius
    best_sp = -1
    coarse_t = 0.5
    for si, sp in enumerate(cn.splines):
        if any(i >= len(cn.positions) for i in sp):
            continue
        p0, p1, p2, p3 = [cn.positions[i] for i in sp]
        for k in range(N + 1):
            t = k / N
            bp = _bezier_point(p0, p1, p2, p3, t)
            d2 = sum((bp[j] - point[j]) ** 2 for j in range(3))
            if d2 < best_d2:
                best_d2 = d2
                best_sp = si
                coarse_t = t
    # Newton-Raphson リファインで正確な距離を再評価
    if best_sp >= 0:
        sp = cn.splines[best_sp]
        p0 = _np.asarray(cn.positions[sp[0]], dtype=float)
        p1 = _np.asarray(cn.positions[sp[1]], dtype=float)
        p2 = _np.asarray(cn.positions[sp[2]], dtype=float)
        p3 = _np.asarray(cn.positions[sp[3]], dtype=float)
        Q  = _np.asarray(point, dtype=float)
        _, _, refined_dist = closest_point_on_bezier(
            p0, p1, p2, p3, Q, t_hint=coarse_t)
        if refined_dist > radius:
            best_sp = -1
    return best_sp


def _bezier_point(p0, p1, p2, p3, t):
    """ベジェカーブ上のパラメータ t の点を計算する。"""
    u = 1.0 - t
    return [
        u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0],
        u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1],
        u**3*p0[2] + 3*u**2*t*p1[2] + 3*u*t**2*p2[2] + t**3*p3[2],
    ]


def _bezier_tangent(p0, p1, p2, p3, t):
    """ベジェカーブ上のパラメータ t の 1 次導関数 (接線ベクトル) を計算する。"""
    u = 1.0 - t
    return [
        3*u*u*(p1[k]-p0[k]) + 6*u*t*(p2[k]-p1[k]) + 3*t*t*(p3[k]-p2[k])
        for k in range(3)
    ]


# ---------------------------------------------------------------------------
# Ring-Cut: Plane-Mesh Intersection
# ---------------------------------------------------------------------------

def _compute_ring_by_plane(mesh_fn, mesh_dag, center, tangent,
                           n_ring_eps=8, vtx_cache=None, phase=None, offset=None):
    """スプライン接線を法線とするカット平面でメッシュを切断し、
    閉じたループ上の等間隔ポイントを返す。

    Parameters
    ----------
    mesh_fn : om.MFnMesh (API 1)
    mesh_dag : om.MDagPath
    center : list[float] (3,) — カット平面の通過点
    tangent : list[float] (3,) — カット平面の法線 (スプライン接線)
    n_ring_eps : int — 出力する等間隔ポイント数
    vtx_cache : list[list[float]] or None — 頂点座標キャッシュ (ドラッグ高速化用)

    Returns
    -------
    list[list[float]] — 閉ループ上の等間隔ポイント (len = n_ring_eps)。
                        ループが得られなかった場合は空リスト。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import _v3_sub, _v3_dot, _v3_len, _v3_normalize

    N = _v3_normalize(tangent)
    if phase is None:
        phase = cmds.optionVar(q='aruRetopoRingPhase') if cmds.optionVar(exists='aruRetopoRingPhase') else 0.
    if offset is None:
        offset = cmds.optionVar(q='aruRetopoRingOffset') if cmds.optionVar(exists='aruRetopoRingOffset') else 0.
    center = [center[k]+N[k]*offset for k in range(3)]

    # ---- 頂点座標を取得 (キャッシュがあれば再利用) ----
    if vtx_cache is not None:
        vtx_pos = vtx_cache
    else:
        pts = om.MPointArray()
        mesh_fn.getPoints(pts, om.MSpace.kWorld)
        vtx_pos = [[pts[i].x, pts[i].y, pts[i].z]
                    for i in range(pts.length())]

    # 各頂点の符号付き距離 d = dot(v - center, N)
    d_sign = [_v3_dot(_v3_sub(v, center), N) for v in vtx_pos]
    # A plane through an existing vertex ring otherwise has no strict sign
    # changes. Use a consistent tiny side assignment at those vertices.
    epsilon=max(1e-9,max((abs(d) for d in d_sign),default=1.)*1e-8)
    d_sign=[epsilon if abs(d)<epsilon else d for d in d_sign]

    # ---- MItMeshEdge で全辺を走査し、平面交差する辺を検出 ----
    edge_it = om.MItMeshEdge(mesh_dag)
    # edge_idx → (交差点, 隣接 face リスト)
    crossings = {}  # {edge_idx: (point, [face_ids])}
    face_to_edges = {}  # {face_idx: [edge_idx, ...]}
    while not edge_it.isDone():
        ei = edge_it.index()
        v0i = edge_it.index(0)
        v1i = edge_it.index(1)
        d0 = d_sign[v0i]
        d1 = d_sign[v1i]
        if d0 * d1 < 0:  # 符号が異なる → 平面を跨ぐ
            t_edge = d0 / (d0 - d1)
            pt = [vtx_pos[v0i][k] + (vtx_pos[v1i][k] - vtx_pos[v0i][k]) * t_edge
                  for k in range(3)]
            # 隣接 face を取得
            face_arr = om.MIntArray()
            edge_it.getConnectedFaces(face_arr)
            faces = [face_arr[j] for j in range(face_arr.length())]
            crossings[ei] = (pt, faces)
            for fi in faces:
                face_to_edges.setdefault(fi, []).append(ei)
        edge_it.next()

    if len(crossings) < 3:
        return []

    # ---- face 隣接でマーチングして閉ループに整列 ----
    loops = _march_crossing_loop(crossings, face_to_edges, center)
    if not loops:
        return []

    # ---- arc-length で n_ring_eps 等分サンプリング ----
    from Aru_RetopoTool.hard_surface import corner_samples
    samples=corner_samples(loops,_resample_loop(loops,n_ring_eps,phase))
    if _sym.is_enabled():
        mesh=mesh_dag.fullPathName()
        mc=_sym.mirror_point(center,mesh)
        mn=_sym.mirror_point([center[k]+N[k] for k in range(3)],mesh)
        reflected=[mn[k]-mc[k] for k in range(3)]
        same_plane=(abs(sum((mc[k]-center[k])*N[k] for k in range(3)))<1e-6
                    and abs(sum(reflected[k]*N[k] for k in range(3)))>.9999)
        if same_plane:
            for p in list(samples):
                mp=_sym.mirror_point(p,mesh)
                if not any(sum((q[k]-mp[k])**2 for k in range(3))<1e-12 for q in samples):samples.append(mp)
            samples=corner_samples(loops,samples,order_only=True)
    return samples


def _march_crossing_loop(crossings, face_to_edges, center):
    """交差辺を face 隣接でマーチングし、閉じたループ (点列 list) を返す。
    複数ループがある場合は center に最も近いものを返す。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import _v3_sub, _v3_dot, _v3_len
    visited = set()
    best_loop = None
    best_dist = float('inf')

    for start_edge in crossings:
        if start_edge in visited:
            continue
        loop_pts = []
        loop_edges = []
        current = start_edge
        prev_face = None
        closed = False

        while True:
            if current in visited and current != start_edge:
                break
            if current == start_edge and len(loop_pts) > 2:
                closed = True
                break
            visited.add(current)
            pt, faces = crossings[current]
            loop_pts.append(pt)
            loop_edges.append(current)

            # 次の辺を探す: 現在の辺の隣接 face を経由して次の交差辺へ
            found_next = False
            for fi in faces:
                if fi == prev_face:
                    continue
                # この face 上の他の交差辺を探す
                for next_edge in face_to_edges.get(fi, []):
                    if next_edge == current:
                        continue
                    if next_edge == start_edge and len(loop_pts) > 2:
                        # ループ閉じ
                        prev_face = fi
                        current = next_edge
                        found_next = True
                        break
                    if next_edge not in visited:
                        prev_face = fi
                        current = next_edge
                        found_next = True
                        break
                if found_next:
                    break
            if not found_next:
                break

        if closed and len(loop_pts) >= 3:
            # ループの重心と center の距離で評価
            cx = sum(p[0] for p in loop_pts) / len(loop_pts)
            cy = sum(p[1] for p in loop_pts) / len(loop_pts)
            cz = sum(p[2] for p in loop_pts) / len(loop_pts)
            d = _v3_len(_v3_sub([cx, cy, cz], center))
            if d < best_dist:
                best_dist = d
                best_loop = loop_pts

    return best_loop


def _resample_loop(loop_pts, n_out, phase=0.):
    """閉ループ点列を arc-length 等分で n_out 点にリサンプリングする。"""
    from Aru_RetopoTool.editor.curvenet.curve_net_data import _v3_sub, _v3_len, _v3_lerp
    n = len(loop_pts)
    if n < 3:
        return []

    # 各セグメントの arc-length を計算 (閉ループなので最後→最初も含む)
    seg_lens = []
    for i in range(n):
        j = (i + 1) % n
        seg_lens.append(_v3_len(_v3_sub(loop_pts[j], loop_pts[i])))
    total = sum(seg_lens)
    if total < 1e-12:
        return []

    # 累積 arc-length
    cumul = [0.0]
    for sl in seg_lens:
        cumul.append(cumul[-1] + sl)

    # n_out 等分のパラメータ位置で補間
    result = []
    for k in range(n_out):
        target = total * ((k / n_out + phase / 360.) % 1.)
        # target が属するセグメントを探す
        seg = 0
        for seg in range(n):
            if cumul[seg + 1] >= target - 1e-12:
                break
        local_t = (target - cumul[seg]) / seg_lens[seg] if seg_lens[seg] > 1e-12 else 0.0
        local_t = max(0.0, min(1.0, local_t))
        j = (seg + 1) % n
        result.append(_v3_lerp(loop_pts[seg], loop_pts[j], local_t))

    return result


def _create_ring_curve(cn, mesh_name, ring_points):
    """リングポイント列から閉じたループ RetopoGuide カーブを生成する。

    Parameters
    ----------
    cn : RetopoGuideData
    mesh_name : str
    ring_points : list[list[float]] — 閉ループ上の点列 (始点≠終点)
    """
    if len(ring_points) < 3:
        return

    have_mesh = mesh_name and cmds.objExists(mesh_name)
    mesh_fn = mesh_dag = None
    if have_mesh:
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)

    # 各ポイントを EP として追加
    ep_indices = []
    for pt in ring_points:
        if have_mesh:
            snap_pt, face_idx, bary = _closest_point_on_mesh(
                mesh_fn, mesh_dag, pt)
            ep = cn.add_cv(snap_pt, surface=(face_idx, bary))
        else:
            ep = cn.add_cv(pt)
        ep_indices.append(ep)

    # 隣接 EP 間にスプラインを作成 (ループなので最後→最初も含む)
    snap_r = _snap_radius(mesh_name)
    new_sp_indices = []
    n = len(ep_indices)
    for i in range(n):
        j = (i + 1) % n
        sp_idx = _add_spline_to_cn(cn, mesh_name, ep_indices[i], ep_indices[j])
        new_sp_indices.append(sp_idx)

    from Aru_RetopoTool.symmetry_ops import mirrored_splines
    reflected=mirrored_splines(cn,mesh_name,new_sp_indices,create=True)
    new_sp_indices=sorted(set(new_sp_indices)|set(reflected.values()))

    # 既存スプラインとの交差点を検出・分割
    for sp_idx in new_sp_indices:
        if sp_idx < len(cn.splines):
            _split_splines_at_intersections(cn, sp_idx, mesh_name,
                                            snap_r * 0.5)

    cn.classify_endpoints()


def _sample_spline(cn: "RetopoGuideData", sp_idx: int, n: int = 32):
    """スプラインを折れ線に落とす。``[(t, point), ...]`` を返す。"""
    sp = cn.splines[sp_idx]
    if any(i >= len(cn.positions) for i in sp):
        return []
    p0, p1, p2, p3 = [cn.positions[i] for i in sp]
    return [(k / float(n), _bezier_point(p0, p1, p2, p3, k / float(n)))
            for k in range(n + 1)]


def _polyline_bounds(pts, pad: float = 0.0):
    """``[(t, point), ...]`` の AABB を ``(lo, hi)`` で返す。"""
    lo = [min(p[1][k] for p in pts) - pad for k in range(3)]
    hi = [max(p[1][k] for p in pts) + pad for k in range(3)]
    return lo, hi


def _bounds_overlap(a, b) -> bool:
    return all(a[0][k] <= b[1][k] and b[0][k] <= a[1][k] for k in range(3))


def _segments_cross(a0, a1, b0, b1, normal):
    """接平面へ落として 2 線分が **本当に交差する** か調べる。

    近いだけ (平行に並走している等) は交差ではない。従来はここを
    「距離が許容値以内」だけで判定していたため、密なネットの隙間に
    カーブを通すと、またいでもいない隣のカーブすべてと交点を作って
    しまっていた。

    法線まわりの符号で「相手の線のどちら側にいるか」を見て、
    両方とも符号が入れ替わるときだけ交差とみなす (2D の線分交差判定を
    曲面の接平面で行うのと同じ)。

    Returns
    -------
    tuple | None
        線分内パラメータ ``(s, u)``。交差しなければ None。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import (
        _v3_sub, _v3_dot, _v3_cross)
    da = _v3_sub(a1, a0)
    db = _v3_sub(b1, b0)

    # b の線に対する a0 / a1 の側
    ca0 = _v3_dot(normal, _v3_cross(db, _v3_sub(a0, b0)))
    ca1 = _v3_dot(normal, _v3_cross(db, _v3_sub(a1, b0)))
    if ca0 * ca1 >= 0.0:
        return None
    # a の線に対する b0 / b1 の側
    cb0 = _v3_dot(normal, _v3_cross(da, _v3_sub(b0, a0)))
    cb1 = _v3_dot(normal, _v3_cross(da, _v3_sub(b1, a0)))
    if cb0 * cb1 >= 0.0:
        return None

    den_a = ca0 - ca1
    den_b = cb0 - cb1
    if abs(den_a) < 1e-30 or abs(den_b) < 1e-30:
        return None
    return (ca0 / den_a, cb0 / den_b)


def _same_surface_side(mesh_fn, pa, pb, min_dot: float = -0.5) -> bool:
    """2 点が **同じ面の上** にあるか法線の向きで判定する。

    太ももと尻尾のように別のパーツが密着していると、
    スナップ許容値 (メッシュ AABB の 4%) の方が隙間より大きくなり、
    「近い」だけでは自分のパーツと隣のパーツを区別できない。

    密着した 2 面は必ず **向かい合う** ので、パーツの向きによらず
    法線の内積は -1 に近くなる (実測 -1.0000)。同じ面の上なら
    +1 に近い (実測 +1.0000)。折り重なった薄い板の表と裏も同じ理屈で
    弾ける。

    しきい値を 0 ではなく -0.5 にしているのは、箱の角のような
    ハードエッジをまたぐ本物の交差 (内積 ≒ 0) を落とさないため。

    法線が取れないときは判定できないので True (従来どおり) を返す。
    """
    try:
        na = _get_normal_at_point(mesh_fn, pa)
        nb = _get_normal_at_point(mesh_fn, pb)
    except Exception:
        return True
    if na is None or nb is None:
        return True
    return sum(na[k] * nb[k] for k in range(3)) > min_dot


def _find_curve_crossings(cn: "RetopoGuideData", sp_a: int, sp_b: int,
                          tol: float, mesh_fn=None,
                          samples: int = 32) -> list:
    """スプライン sp_a と sp_b が **実際に交差する** 点を返す。

    弦ではなく実際のベジエ曲線どうしで判定する。曲面上のカーブは
    メッシュに沿って曲がるので、弦で代用すると本当は通っていない
    場所を横切ったことになってしまう。

    Returns
    -------
    list
        ``[(t_a, t_b, point), ...]``。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import (
        _v3_sub, _v3_cross, _v3_len)

    A = _sample_spline(cn, sp_a, samples)
    B = _sample_spline(cn, sp_b, samples)
    if not A or not B:
        return []

    # スプライン単位の早期棄却
    if not _bounds_overlap(_polyline_bounds(A, tol), _polyline_bounds(B)):
        return []

    out = []
    for i in range(len(A) - 1):
        ta0, a0 = A[i]
        ta1, a1 = A[i + 1]
        lo = [min(a0[k], a1[k]) - tol for k in range(3)]
        hi = [max(a0[k], a1[k]) + tol for k in range(3)]
        for j in range(len(B) - 1):
            tb0, b0 = B[j]
            tb1, b1 = B[j + 1]
            # 線分単位の早期棄却 (ここが効くので全体は十分速い)
            if (max(b0[0], b1[0]) < lo[0] or min(b0[0], b1[0]) > hi[0]
                    or max(b0[1], b1[1]) < lo[1] or min(b0[1], b1[1]) > hi[1]
                    or max(b0[2], b1[2]) < lo[2] or min(b0[2], b1[2]) > hi[2]):
                continue

            mid = [(a0[k] + a1[k] + b0[k] + b1[k]) * 0.25 for k in range(3)]
            normal = None
            if mesh_fn is not None:
                try:
                    normal = _get_normal_at_point(mesh_fn, mid)
                except Exception:
                    normal = None
            if normal is None:
                # メッシュが無い場合は 2 本の向きから面を作る。
                # 並走しているとここが縮退するが、その場合は交差でもない。
                normal = _v3_cross(_v3_sub(a1, a0), _v3_sub(b1, b0))
                if _v3_len(normal) < 1e-12:
                    continue

            hit = _segments_cross(a0, a1, b0, b1, normal)
            if hit is None:
                continue
            s, u = hit
            pa = [a0[k] + (a1[k] - a0[k]) * s for k in range(3)]
            pb = [b0[k] + (b1[k] - b0[k]) * u for k in range(3)]
            # 接平面では交差していても、面から浮いて立体交差している
            # (別のパーツを跨いでいる) ことがあるので距離も見る
            d = _v3_len(_v3_sub(pa, pb))
            if d > tol:
                continue
            # 隣り合った別パーツ (太ももと尻尾など) を跨いでいないか。
            # 許容値はメッシュ AABB 基準なので、密着したパーツ同士の
            # 隙間より大きくなりうる。そのままだと尻尾のカーブと
            # 太もものカーブが勝手に繋がってしまう。
            if mesh_fn is not None and not _same_surface_side(mesh_fn, pa, pb):
                continue
            out.append((ta0 + (ta1 - ta0) * s,
                        tb0 + (tb1 - tb0) * u,
                        [(pa[k] + pb[k]) * 0.5 for k in range(3)]))

    if len(out) < 2:
        return out

    # 同じ場所を重複して拾った分をまとめる
    out.sort(key=lambda h: h[0])
    merged = [out[0]]
    for h in out[1:]:
        if abs(h[0] - merged[-1][0]) > 1e-3:
            merged.append(h)
    return merged


def _split_splines_at_intersections(
    cn: "RetopoGuideData",
    new_sp_idx: int,
    mesh_name: str,
    tol: float = 0.05,
) -> None:
    """
    新しく追加された spline (new_sp_idx) と既存スプラインが **実際に
    交差する** 点を検出し、両方を分割して交差点に共有 EP を作成する。

    「近い」だけでは分割しない。密なネットの隙間にカーブを通したとき、
    またいでもいない隣のカーブすべてと交点を作ってしまうのを防ぐため。
    """
    new_sp = cn.splines[new_sp_idx]
    if any(i >= len(cn.positions) for i in new_sp):
        return

    # 新スプラインと端点を共有するスプラインは除外
    new_ep_set = {new_sp[0], new_sp[3]}
    sp_count = len(cn.splines)

    have_mesh = mesh_name and cmds.objExists(mesh_name)
    mesh_fn = mesh_dag = None
    if have_mesh:
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)

    hit_data = []  # [(existing_sp_idx, t_existing, t_new, point)]
    for si in range(sp_count):
        if si == new_sp_idx:
            continue
        existing_sp = cn.splines[si]
        if existing_sp[0] in new_ep_set or existing_sp[3] in new_ep_set:
            continue
        for t_new, t_crv, pt in _find_curve_crossings(
                cn, new_sp_idx, si, tol, mesh_fn):
            # 端点のすぐ脇での分割は、元の EP と重なった無駄な点になる
            if t_new < 0.05 or t_new > 0.95:
                continue
            if t_crv < 0.05 or t_crv > 0.95:
                continue
            hit_data.append((si, t_crv, t_new, pt))

    if not hit_data:
        return

    # 新スプライン上で近すぎる交点はまとめる (団子になるのを防ぐ)
    hit_data.sort(key=lambda x: x[2])
    pruned = [hit_data[0]]
    for h in hit_data[1:]:
        if h[2] - pruned[-1][2] > 0.02:
            pruned.append(h)
    hit_data = pruned

    # 新 spline 上の t が大きい方から分割 (インデックスがずれないように)
    hit_data.sort(key=lambda x: x[2], reverse=True)

    # 既存スプラインの分割を先に行い、交差点 EP を作成
    # (既存スプラインの分割は互いに独立なので順序不問)
    intersection_eps = []  # [(t_new_spline, ep_idx)]
    for si, t_crv, t_new, pt in hit_data:
        # 既存スプラインを分割
        new_ep, _, _ = cn.split_spline(si, t_crv)
        # メッシュ投影
        if have_mesh:
            snap_pt, face_idx, bary = _closest_point_on_mesh(
                mesh_fn, mesh_dag, cn.positions[new_ep])
            cn.positions[new_ep] = snap_pt
            cn.surface_binding[new_ep] = (face_idx, bary)
        intersection_eps.append((t_new, new_ep))

    if not intersection_eps:
        return

    # 新 spline を交差点 EP を経由するように再構成
    # 新 spline の端点
    new_sp = cn.splines[new_sp_idx]
    ep_start = new_sp[0]
    ep_end = new_sp[3]

    # 新 spline を削除。ハンドルは参照が外れるが、_commit_net_data で
    # 孤立 CV として掃除される。
    cn.splines.pop(new_sp_idx)

    # 始点→交差点EP群→終点 の順で spline を生成
    intersection_eps.sort(key=lambda x: x[0])  # t 昇順
    chain_eps = [ep_start] + [ep for _, ep in intersection_eps] + [ep_end]

    normal = None
    if have_mesh:
        mid = [(cn.positions[chain_eps[0]][k] + cn.positions[chain_eps[-1]][k]) * 0.5
               for k in range(3)]
        normal = _get_normal_at_point(mesh_fn, mid)

    for i in range(len(chain_eps) - 1):
        sp_idx = cn.add_spline_two_endpoints(
            chain_eps[i], chain_eps[i + 1], surface_normal=normal)
        _fit_spline_handles_to_mesh(cn, sp_idx, mesh_name)

    cn.classify_endpoints()


def _remove_ep(cn: RetopoGuideData, ep: int, mesh_name: str = "") -> None:
    """
    EP を削除する。チェーン中間点 (次数2) の場合は隣接2スプラインを1本に結合する。
    それ以外は全接続スプラインを削除する。
    """
    # ep に接続するスプラインを収集
    connected = [(i, sp) for i, sp in enumerate(cn.splines)
                 if sp[0] == ep or sp[3] == ep]

    if len(connected) == 2:
        # チェーン中間点: 2本のスプラインを1本に結合
        (i0, sp0), (i1, sp1) = connected
        # sp0 の ep を含まない側の端点と、sp1 の ep を含まない側の端点を繋ぐ
        other0 = sp0[3] if sp0[0] == ep else sp0[0]
        other1 = sp1[3] if sp1[0] == ep else sp1[0]
        # 2本のスプラインを削除 (大きいインデックスから)
        for idx in sorted([i0, i1], reverse=True):
            cn.splines.pop(idx)
        # other0 == other1 の場合は自己ループになるので結合しない
        if other0 != other1:
            normal = None
            if mesh_name and cmds.objExists(mesh_name):
                mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
                mid = [(cn.positions[other0][k] + cn.positions[other1][k]) * 0.5
                       for k in range(3)]
                normal = _get_normal_at_point(mesh_fn, mid)
            sp_idx = cn.add_spline_two_endpoints(other0, other1,
                                                 surface_normal=normal)
            if mesh_name and cmds.objExists(mesh_name):
                mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
                sp = cn.splines[sp_idx]
                for hi in [sp[1], sp[2]]:
                    proj_pt, fi, b = _closest_point_on_mesh(
                        mesh_fn, mesh_dag, cn.positions[hi])
                    cn.positions[hi] = proj_pt
                    cn.surface_binding[hi] = (fi, b)
    else:
        # 次数 != 2: 接続スプラインをすべて削除
        cn.splines = [sp for sp in cn.splines
                      if sp[0] != ep and sp[3] != ep]
    # 単独ポイントの印を持ったまま削除すると残骸掃除の対象外になり、
    # 画面から消えたはずの点が netData に残り続ける。
    cn.unmark_standalone(ep)
    cn.classify_endpoints()


def _attach_ep_to_spline(cn: RetopoGuideData, ep: int, sp_idx: int, t: float,
                         mesh_name: str) -> bool:
    """既存の EP *ep* を、スプライン *sp_idx* の *t* の位置の交点にする。

    スプラインを分割してできた点に *ep* を統合するので、*ep* に繋がって
    いたカーブはそのまま保たれ、分割された 2 本も *ep* に繋がる。
    結果として *ep* は「カーブの交点」になる。

    *ep* を端点に持つスプラインを分割しようとした場合など、意味のない
    操作になるときは何もせず False を返す。
    """
    if sp_idx < 0 or sp_idx >= len(cn.splines):
        return False
    sp = cn.splines[sp_idx]
    if sp[0] == ep or sp[3] == ep:
        return False

    new_ep = _split_spline_at(cn, sp_idx, t, mesh_name)
    # 分割点はカーブの上にあるので、EP をそこへ移してから統合する。
    # そうしないと EP が交点からわずかに浮いたままになる。
    cn.positions[ep] = list(cn.positions[new_ep])
    if new_ep in cn.surface_binding:
        cn.surface_binding[ep] = cn.surface_binding[new_ep]
    _merge_two_eps(cn, ep_keep=ep, ep_remove=new_ep)
    _recompute_handles_for_ep(cn, ep, mesh_name)
    cn.classify_endpoints()
    return True


def _mirror_attach_ep_to_spline(cn: RetopoGuideData, ep: int, mirror_ep: int,
                                mesh_name: str) -> bool:
    """*ep* を交点にしたあと、対称側の *mirror_ep* も交点にする。

    対称側は画面で狙えないので、反転位置の近くを通るカーブを探す。
    """
    if (not _sym.is_enabled() or mirror_ep is None or mirror_ep == ep
            or mirror_ep >= len(cn.positions) or ep >= len(cn.positions)):
        return False
    tol = _mirror_tol(mesh_name)
    mpos = _sym.mirror_point(cn.positions[ep], mesh_name)
    cn.move_cv(mirror_ep, mpos)
    hit = _nearest_spline_t_excluding(cn, mpos, tol * 2.0,
                                      exclude_ep=mirror_ep,
                                      mesh_name=mesh_name)
    if hit is None:
        _recompute_handles_for_ep(cn, mirror_ep, mesh_name)
        return False
    return _attach_ep_to_spline(cn, mirror_ep, hit[0], hit[1], mesh_name)


def _mirror_merge_pair(cn: RetopoGuideData, mesh_name: str,
                       ep_keep: int, ep_remove: int):
    """対称側でマージすべき EP の組 ``(keep, remove)`` を返す。無ければ None。

    **マージを実行する前に呼ぶこと。** マージ後は *ep_remove* が端点では
    なくなるので、対称側の相方を探せなくなる。

    対称側の EP が両方見つかったときだけ返す。片方しか無いときに新しく
    作ると、ユーザーが置いていない点が生えてしまうため。
    """
    if not _sym.is_enabled():
        return None
    tol = _mirror_tol(mesh_name)
    m_keep = _sym.find_mirror_ep(cn, mesh_name, ep_keep, tol)
    m_rem = _sym.find_mirror_ep(cn, mesh_name, ep_remove, tol)
    if m_keep is None or m_rem is None or m_keep == m_rem:
        return None
    # 両方とも対称面の上 = 元のマージで用が足りている
    if m_keep == ep_keep and m_rem == ep_remove:
        return None
    # 互いが相手の対称 = 対称面をまたぐマージ。これも済んでいる
    if m_keep == ep_remove and m_rem == ep_keep:
        return None
    return (m_keep, m_rem)


def _mirror_split_spline(cn: RetopoGuideData, mesh_name: str, ep: int):
    """スプラインを分割して出来た *ep* の対称側にも分割点を作る。

    対称側に既に EP があれば何もしない。近くにカーブが無ければ、
    宙に浮いた点を作らずにあきらめる。
    """
    if (not _sym.is_enabled() or ep is None
            or ep >= len(cn.positions)):
        return None
    tol = _mirror_tol(mesh_name)
    found = _sym.find_mirror_ep(cn, mesh_name, ep, tol)
    if found is not None:
        # 対称面の上なら自分自身が返る。どちらの場合も作る必要はない
        return None

    mpos = _sym.mirror_point(cn.positions[ep], mesh_name)
    face_idx, bary = -1, []
    if mesh_name and cmds.objExists(mesh_name):
        mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
        mpos, face_idx, bary = _closest_point_on_mesh(mesh_fn, mesh_dag, mpos)

    hit = _nearest_spline_t_excluding(cn, mpos, tol * 2.0,
                                      mesh_name=mesh_name)
    if hit is None:
        return None
    sp_idx, t = hit
    m_ep = _split_spline_at(cn, sp_idx, t, mesh_name)
    # 分割点はカーブ上の位置なので、左右が厳密には対応しない。
    # 反転位置そのものへ寄せておかないと、あとで相方を探すときに
    # 許容距離から外れて見つからなくなる。
    cn.move_cv(m_ep, mpos)
    if face_idx >= 0:
        cn.surface_binding[m_ep] = (face_idx, bary)
    _recompute_handles_for_ep(cn, m_ep, mesh_name)
    return m_ep


def _merge_two_eps(cn: RetopoGuideData, ep_keep: int, ep_remove: int) -> None:
    """
    ep_remove を ep_keep に統合する。
    ep_remove を端点として持つすべての spline を ep_keep に書き換える。
    退化スプライン (両端が同じ EP) は除去する。
    """
    new_splines = []
    for sp in cn.splines:
        s = tuple(ep_keep if x == ep_remove else x for x in sp)
        if s[0] == s[3]:   # 両端が同じ EP になった退化スプラインを除去
            continue
        new_splines.append(s)
    cn.splines = new_splines
    # 統合された側は消えるので印を外す。統合先がまだ線なしなら印を引き継ぐ。
    if cn.is_standalone(ep_remove):
        cn.unmark_standalone(ep_remove)
        if not any(ep_keep in (sp[0], sp[3]) for sp in cn.splines):
            cn.mark_standalone(ep_keep)



# ===========================================================================
# RetopoGuideContext
# ===========================================================================

class RetopoGuideContext:
    """RetopoGuide 編集コンテキスト。

    draggerContext のコールバック・選択管理・コンポーネントモード・
    scriptJob を統合するクラス。共有状態は RetopoGuideState インスタンス
    (self._s) を通じてアクセスする。
    """

    def __init__(self, state):
        from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import RetopoGuideState
        self._s: RetopoGuideState = state
        self._undo_open = False
        self._relax_save_callback = None

    def _point_preview_for(self, node):
        preview=getattr(self,'_point_preview',None)
        if preview is not None:return preview
        if not cmds.objExists(node+'.editPreviewPositions') or is_pose_driven(node):return None
        from .point_preview import PointPreview
        preview=PointPreview(node)
        # Preserve first-dab compaction/remapping in scenes with orphan CVs.
        if preview.read().orphan_cv_indices():return None
        self._point_preview=preview
        self._point_save_callback=om.MSceneMessage.addCallback(
            om.MSceneMessage.kBeforeSave,self._before_point_save)
        return preview

    def _finish_point(self, commit, take=False):
        preview=getattr(self,'_point_preview',None)
        self._point_preview=None
        callback=getattr(self,'_point_save_callback',None)
        if callback is not None:om.MMessage.removeCallback(callback)
        self._point_save_callback=None
        if preview is None or preview.closed:return None
        try:
            if take:return preview.take()
            if commit:preview.commit()
            else:preview.cancel()
        finally:
            if not preview.closed:preview.cancel()

    def _before_point_save(self, *args):
        try:self._finish_point(False)
        finally:self._close_undo()

    def _close_undo(self):
        if self._undo_open:
            self._undo_open = False
            cmds.undoInfo(closeChunk=True)
            _rebind.resume()

    def _remove_relax_save_callback(self):
        if self._relax_save_callback is not None:
            om.MMessage.removeCallback(self._relax_save_callback)
            self._relax_save_callback = None

    def _finish_relax(self,commit):
        stroke = _state_get(self._s,'relax_stroke')
        _state_set(self._s,'relax_stroke',None)
        self._remove_relax_save_callback()
        if not stroke:return None
        preview=stroke.get('numeric_preview')
        if preview is not None and not preview.closed:
            try:
                if commit:preview.commit()
                else:preview.cancel()
            finally:
                # Also clears transient positions on a failed commit.
                if not preview.closed:preview.cancel()
        elif preview is None and commit and stroke['moved']:
            from . import curve_net_relax
            curve_net_relax.relax(stroke['node'],{v:1. for v in stroke['affected']},
                                  draft=False,smooth=False)
        return stroke

    def _before_relax_save(self,*args):
        # Maya save callbacks do not reliably record scene edits in the open
        # gesture's Undo chunk. Discard only the in-flight preview; save the
        # last committed state instead of introducing an un-undoable commit.
        try:self._finish_relax(False)
        except Exception:
            om.MGlobal.displayError('[RetopoGuide] relax save error:\n'+traceback.format_exc())
        finally:self._close_undo()

    def _cancel_relax(self):
        try:
            self._finish_relax(False)
            self._finish_point(False)
        finally:self._close_undo()

    def press(self):
        self._cancel_relax()
        cmds.undoInfo(openChunk=True, chunkName="RetopoGuide")
        self._undo_open = True
        # ドラッグ中は netData が連続で書かれるので、リバインドはリリースまで止める
        _rebind.suspend()
        try:
            self._press_impl()
        except Exception:
            om.MGlobal.displayError("[RetopoGuide] press error:\n" + traceback.format_exc())
            self._cancel_relax()

    def _press_impl(self):
        # ボタン番号: 1=LMB, 2=MMB, 3=RMB
        try:
            button = cmds.draggerContext(_DRAGGER_CTX, q=True, button=True) or 1
        except Exception:
            button = 1

        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if not node or not cmds.objExists(node):
            om.MGlobal.displayWarning("[RetopoGuide] press: retopoGuideContext_node not set")
            return

        acc       = RetopoGuideAccessor(node)
        cn        = acc.read()
        mesh_name = acc.mesh_name

        screen_pt = cmds.draggerContext(_DRAGGER_CTX, q=True, anchorPoint=True)
        sx, sy    = int(screen_pt[0]), int(screen_pt[1])
        world_pt  = _raycast_from_screen(sx, sy, mesh_name)

        # 前回のドラッグ結果が残らないようクリアする
        _state_set(self._s, "press_screen", (float(sx), float(sy)))
        _state_set(self._s, "drag_screen", None)
        _state_set(self._s, "hover_spline", None)
        _state_set(self._s, "relax_stroke", None)
        _DRAG_CN_CACHE.clear()
        # modifier ビットマスク: Shift=1, Ctrl=4, Alt=8
        mods = cmds.getModifiers()
        has_shift = bool(mods & 1)
        has_ctrl  = bool(mods & 4)

        # ---- Ctrl+LMB: リングカット (メッシュ外からも可能) ----
        if has_ctrl and not has_shift and button == 1:
            if not mesh_name or not cmds.objExists(mesh_name):
                om.MGlobal.displayWarning("[RetopoGuide] リングカット: メッシュが必要です")
                return

            mesh_fn_rc, mesh_dag_rc = _get_mesh_fn(mesh_name)

            # カメラレイを取得
            try:
                view = omui.M3dView.active3dView()
                cam_origin = om.MPoint()
                cam_dir = om.MVector()
                view.viewToWorld(sx, sy, cam_origin, cam_dir)
                cam_dir_list = [cam_dir.x, cam_dir.y, cam_dir.z]
            except Exception:
                cam_dir_list = [0.0, 0.0, 1.0]
                cam_origin = om.MPoint(0, 0, 0)
                cam_dir = om.MVector(0, 0, 1)

            # 独自のレイ-メッシュ直接交差テスト
            # (_raycast_from_screen はフォールバックで常にポイントを返すため使えない)
            ray_src = om.MFloatPoint(cam_origin.x, cam_origin.y,
                                      cam_origin.z)
            ray_dir_f = om.MFloatVector(cam_dir.x, cam_dir.y, cam_dir.z)
            hit_pt_f = om.MFloatPoint()
            _hit_face_u = om.MScriptUtil()
            _hit_face_u.createFromInt(0)
            ray_hit = mesh_fn_rc.closestIntersection(
                ray_src, ray_dir_f, None, None, False,
                om.MSpace.kWorld, 1e9, False,
                None, hit_pt_f, None, _hit_face_u.asIntPtr(),
                None, None, None, 1e-6)
            on_mesh_pt = ([hit_pt_f.x, hit_pt_f.y, hit_pt_f.z]
                          if ray_hit else None)

            # 頂点キャッシュ (ドラッグ中の再計算を高速化)
            pts_arr = om.MPointArray()
            mesh_fn_rc.getPoints(pts_arr, om.MSpace.kWorld)
            vtx_cache = [[pts_arr[i].x, pts_arr[i].y, pts_arr[i].z]
                          for i in range(pts_arr.length())]

            n_ring_eps = max(3, min(128, int(cmds.optionVar(q='aruRetopoRingCount')))) if cmds.optionVar(exists='aruRetopoRingCount') else 8
            result = _nearest_spline_t(cn, on_mesh_pt) if on_mesh_pt else None
            if result is not None:
                # スプラインあり: 接線方向でカット平面を即座にプレビュー
                sp_idx, t = result
                sp = cn.splines[sp_idx]
                p0, p1, p2, p3 = [cn.positions[i] for i in sp]
                ring_center = _bezier_point(p0, p1, p2, p3, t)
                ring_tangent = _bezier_tangent(p0, p1, p2, p3, t)

                ring_pts = _compute_ring_by_plane(
                    mesh_fn_rc, mesh_dag_rc, ring_center, ring_tangent,
                    n_ring_eps=n_ring_eps, vtx_cache=vtx_cache)
                if not ring_pts:
                    om.MGlobal.displayWarning(
                        "[RetopoGuide] リングカット: カット平面がメッシュと交差しません")
                    return

                self._s.ring_cut = {
                    "mode": "spline",
                    "sp_idx": sp_idx, "t": t,
                    "center": ring_center, "tangent": ring_tangent,
                    "vtx_cache": vtx_cache,
                    "anchor_sx": sx, "anchor_sy": sy, "base_count": n_ring_eps,
                    "n_ring_eps": n_ring_eps,
                }
                self._s.ring_preview = ring_pts
                self._s.ring_line = None
                _dirty_shape_view()
                om.MGlobal.displayInfo(
                    "[RetopoGuide] リングカット(spline): sp={} t={:.3f}  "
                    "上下=位置 左右=分割数".format(sp_idx, t))
            else:
                # スプラインなし: ドラッグ線でカット方向を決定 (Multi-Cut 風)
                self._s.ring_cut = {
                    "mode": "freecut",
                    "start_sx": sx, "start_sy": sy,
                    "vtx_cache": vtx_cache,
                    "n_ring_eps": n_ring_eps,
                    "mesh_name": mesh_name,
                }
                self._s.ring_preview = None
                self._s.ring_line = None
                _dirty_shape_view()
                om.MGlobal.displayInfo(
                    "[RetopoGuide] リングカット: ドラッグでカット線を描画")
            return

        # world_pt が None の場合 (Ctrl+LMB 以外ではメッシュヒットが必要)
        if world_pt is None:
            return

        snap_r  = _snap_radius(mesh_name)
        nearest = cn.find_nearest_cv(world_pt, snap_r)
        ep_set  = cn.endpoint_indices()
        snapped = nearest if (nearest is not None and nearest in ep_set) else None

        # ---- Ctrl+MMB: スプライン上に EP を挿入 ----
        if has_ctrl and not has_shift and button == 2:
            result = _nearest_spline_t(cn, world_pt)
            if result is not None:
                sp_idx, t = result
                # _split_spline_at はメッシュ投影と両側のハンドル張り直しも
                # まとめて面倒を見る
                new_ep = _split_spline_at(cn, sp_idx, t, mesh_name)
                msg = "[RetopoGuide] inserted EP {} at t={:.3f}".format(new_ep, t)
                m_ep = _mirror_split_spline(cn, mesh_name, new_ep)
                if m_ep is not None:
                    msg += " (対称側 EP {})".format(m_ep)
                cn.classify_endpoints()
                self._s.sel_ep = new_ep
                _commit_net_data(node, cn)
                om.MGlobal.displayInfo(msg)
            return

        # ---- 中ボタン: ドラッグ対象 EP / ハンドル を選択 ----
        if button == 2:
            if snapped is None:
                # EP が無ければハンドルを探す (画面上の距離で判定)。
                # 非表示 (showHandles=off) なら掴ませない。
                hcv = None
                try:
                    show_h = (not cmds.objExists(node + ".showHandles")
                              or cmds.getAttr(node + ".showHandles"))
                except Exception:
                    show_h = True
                if show_h:
                    hcv = _find_handle_under_screen(cn, float(sx), float(sy))
                if hcv is not None:
                    _state_set(self._s, "drag_handle", hcv)
                    # ドラッグ中はこの点を通るビュー平面上で動かす
                    _state_set(self._s, "drag_handle_anchor",
                               list(cn.positions[hcv]))
                    # 対称側のハンドルは押した瞬間に一度だけ決める (EP と同じ)
                    _state_set(self._s, "drag_mirror_handle",
                               _find_mirror_handle(cn, mesh_name, hcv))
                    om.MGlobal.displayInfo(
                        "[RetopoGuide] MMB start drag handle={}".format(hcv))
                return
            if snapped is not None:
                self._s.drag_ep = snapped
                # 対称ドラッグの相方と、開始時にいた側を憶えておく。
                # ドラッグ中に位置が動くと相方を見失うので、押した瞬間に
                # 一度だけ決める。
                mirror = None
                side = None
                if _sym.is_enabled():
                    mirror = _sym.find_mirror_ep(cn, mesh_name, snapped,
                                                 _mirror_tol(mesh_name))
                    if mirror == snapped:
                        mirror = None
                    coord = _sym.plane_coord(cn.positions[snapped], mesh_name)
                    if coord is not None:
                        side = 1.0 if coord >= 0.0 else -1.0
                _state_set(self._s, "drag_mirror_ep", mirror)
                _state_set(self._s, "drag_side", side)
                om.MGlobal.displayInfo("[RetopoGuide] MMB start drag EP={}".format(snapped))
            return

        # ---- Ctrl+Shift+RMB: スプライン削除 (draggerContext では RMB は届かないため無効) ----
        if has_ctrl and has_shift and button == 3:
            return

        # ---- Ctrl+Shift+LMB: EP 削除 / スプライン削除 ----
        if has_ctrl and has_shift and button == 1:
            target = snapped if snapped is not None else self._s.sel_ep
            if target is not None:
                # EP が近くにある場合は EP 削除
                from Aru_RetopoTool.symmetry_ops import delete_targets
                targets,_=delete_targets(node,{target})
                for ep in sorted(targets,reverse=True):_remove_ep(cn,ep,mesh_name)
                if self._s.sel_ep == target:
                    self._s.sel_ep = None
                _commit_net_data(node, cn)
                om.MGlobal.displayInfo(
                    "[RetopoGuide] EP {} を削除しました".format(target))
            else:
                # EP がない場所: 最近スプラインを削除
                si = _find_nearest_spline(cn, world_pt, snap_r)
                if si >= 0:
                    sp = cn.splines[si]
                    from Aru_RetopoTool.symmetry_ops import delete_targets
                    _,targets=delete_targets(node,splines={si})
                    for index in sorted(targets,reverse=True):cn.splines.pop(index)
                    cn.classify_endpoints()
                    _commit_net_data(node, cn)
                    om.MGlobal.displayInfo(
                        "[RetopoGuide] spline {}-->{} を削除しました".format(sp[0], sp[3]))
            return

        # ---- Shift+LMB: click merges; dragging relaxes on the surface ----
        if has_shift and not has_ctrl and button == 1:
            _state_set(self._s, "relax_stroke", {
                "node": node, "snapped": snapped, "origin": (sx, sy),
                "last": (sx, sy), "moved": False, "affected": set()})
            return

        # ---- 通常 LMB ----
        if snapped is not None:
            # 既存 EP をクリック
            if self._s.sel_ep is None:
                # 1回目: 選択 + プレビュー開始
                self._s.sel_ep = snapped
                self._s.preview_end = list(cn.positions[snapped])
                om.MGlobal.displayInfo("[RetopoGuide] EP selected: {}".format(snapped))
            elif self._s.sel_ep != snapped:
                # 2回目: プレビュー開始 → リリースで確定
                self._s.preview_end = list(cn.positions[snapped])
                _dirty_shape_view()
                return
            else:
                # 同じ EP を再クリック: 選択解除
                self._s.sel_ep = None
                self._s.preview_end = None
        else:
            if self._s.sel_ep is not None:
                # sel_ep 設定済み + 空き場所: プレビュー開始 → リリースで確定
                pv_pt, _pf, _pb, _pon = _apply_symmetry_constraint(
                    mesh_name, world_pt)
                self._s.preview_end = pv_pt
                _dirty_shape_view()
                return
            else:
                # 空き場所をクリック → 新規 EP を追加 + プレビュー開始
                # 対称面の近くなら面の上へ吸着させる (反対側は作らない)
                snap_pt, face_idx, bary, _on_plane = \
                    _apply_symmetry_constraint(mesh_name, world_pt)
                if face_idx >= 0:
                    new_ep = cn.add_cv(snap_pt, surface=(face_idx, bary))
                else:
                    new_ep = cn.add_cv(snap_pt)
                # まだ線が繋がっていないので、書き込み時の残骸掃除で
                # 消えないよう単独ポイントの印を付ける。
                cn.mark_standalone(new_ep)
                _mirror_new_ep(cn, mesh_name, new_ep)
                om.MGlobal.displayInfo("[RetopoGuide] new EP: {}".format(new_ep))
                self._s.sel_ep = new_ep
                self._s.preview_end = list(snap_pt)
                cn.classify_endpoints()

        _commit_net_data(node, cn)


    def _merge_shift_click(self, node, snapped):
        acc = RetopoGuideAccessor(node)
        cn, mesh_name = acc.read(), acc.mesh_name
        sel = self._s.sel_ep
        if sel is None or snapped is None or sel == snapped:
            om.MGlobal.displayWarning("[RetopoGuide] マージ: 2つの異なる EP が必要です")
            return
        pair = _mirror_merge_pair(cn, mesh_name, snapped, sel)
        _merge_two_eps(cn, ep_keep=snapped, ep_remove=sel)
        _recompute_handles_for_ep(cn, snapped, mesh_name)
        if pair is not None:
            _merge_two_eps(cn, ep_keep=pair[0], ep_remove=pair[1])
            _recompute_handles_for_ep(cn, pair[0], mesh_name)
        cn.classify_endpoints()
        self._s.sel_ep = None
        _commit_net_data(node, cn)
        om.MGlobal.displayInfo("[RetopoGuide] merged EP {} into {}".format(sel, snapped))

    def _relax_drag(self, sx, sy):
        stroke = _state_get(self._s, "relax_stroke")
        if not stroke: return False
        if math.hypot(sx-stroke['origin'][0], sy-stroke['origin'][1]) < _CLICK_SLOP_PX:
            return True
        stroke['moved'] = True
        if math.hypot(sx-stroke['last'][0], sy-stroke['last'][1]) < 3:
            return True
        stroke['last'] = (sx, sy)
        from . import curve_net_relax
        if cmds.objExists(stroke['node']+'.editPreviewPositions'):
            preview=stroke.get('numeric_preview')
            if preview is None:
                from .relax_preview import RelaxPreview
                preview=RelaxPreview(stroke['node'])
                stroke['numeric_preview']=preview
                self._relax_save_callback=om.MSceneMessage.addCallback(
                    om.MSceneMessage.kBeforeSave,self._before_relax_save)
            affected=preview.brush(sx,sy)
        else:
            # A running older plugin can retain the established edit path.
            affected=curve_net_relax.brush_relax(stroke['node'],sx,sy)
        stroke['affected'].update(affected)
        return True

    def drag(self):
        try:
            self._drag_impl()
        except Exception:
            om.MGlobal.displayError("[RetopoGuide] drag error:\n" + traceback.format_exc())
            self._cancel_relax()

    def _drag_impl(self):
        try:
            button = cmds.draggerContext(_DRAGGER_CTX, q=True, button=True) or 1
        except Exception:
            button = 1

        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if not node or not cmds.objExists(node):
            return
        mesh_name = cmds.getAttr("{}.meshName".format(node)) or ""
        screen_pt = cmds.draggerContext(_DRAGGER_CTX, q=True, dragPoint=True)
        sx, sy    = int(screen_pt[0]), int(screen_pt[1])
        if self._relax_drag(sx, sy): return
        world_pt  = _raycast_from_screen(sx, sy, mesh_name)
        if world_pt is None:
            return

        if mesh_name and cmds.objExists(mesh_name):
            mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)
            snap_pt, face_idx, bary = _closest_point_on_mesh(
                mesh_fn, mesh_dag, world_pt)
        else:
            snap_pt, face_idx, bary = world_pt, -1, []

        # ---- リングカット ドラッグ ----
        rc = self._s.ring_cut
        if rc is not None and button == 1:
            mode = rc.get("mode", "spline")

            if mode == "spline":
                # ---- スプラインモード: Y=位置スライド, X=分割数調整 ----
                need_recompute = False
                new_center = rc["center"]
                new_tangent = rc["tangent"]

                # X方向: 分割数調整 (50px で ±1)
                dx = sx - rc["anchor_sx"]
                base_n = rc.get("base_count", 8)
                delta_n = int(dx / 50.0)
                new_n = max(3, min(128, base_n + delta_n))
                cmds.optionVar(iv=('aruRetopoRingCount',new_n))
                if new_n != rc["n_ring_eps"]:
                    rc["n_ring_eps"] = new_n
                    need_recompute = True

                # Y方向: スプラインに沿って位置スライド
                cn  = RetopoGuideAccessor(node).read()
                sp_idx = rc["sp_idx"]
                if sp_idx >= len(cn.splines):
                    self._s.ring_cut = None
                    self._s.ring_preview = None
                    self._s.ring_line = None
                    return
                sp = cn.splines[sp_idx]
                p0, p1, p2, p3 = [cn.positions[i] for i in sp]

                dy = sy - rc["anchor_sy"]
                delta_t = dy / 200.0
                new_t = max(0.05, min(0.95, rc["t"] + delta_t))
                new_center = _bezier_point(p0, p1, p2, p3, new_t)
                new_tangent = _bezier_tangent(p0, p1, p2, p3, new_t)
                if new_center != rc["center"] or new_tangent != rc["tangent"]:
                    need_recompute = True

                if need_recompute:
                    mesh_fn_rc, mesh_dag_rc = _get_mesh_fn(mesh_name)
                    ring_pts = _compute_ring_by_plane(
                        mesh_fn_rc, mesh_dag_rc, new_center, new_tangent,
                        n_ring_eps=rc["n_ring_eps"],
                        vtx_cache=rc.get("vtx_cache"))
                    if ring_pts:
                        self._s.ring_preview = ring_pts
                        rc["center"] = new_center
                        rc["tangent"] = new_tangent
                _dirty_shape_view()
                return

            # ---- freecut モード: ドラッグ線方向でカット平面を計算 ----
            from Aru_RetopoTool.editor.curvenet.curve_net_data import _v3_cross, _v3_normalize, _v3_sub

            sx0, sy0 = rc["start_sx"], rc["start_sy"]
            drag_dx = sx - sx0
            drag_dy = sy - sy0
            drag_len_sq = drag_dx * drag_dx + drag_dy * drag_dy
            if drag_len_sq < 25:  # 5px 未満はまだドラッグが短い
                _dirty_shape_view()
                return

            # カメラレイ: 開始点・終了点・中間点
            try:
                view = omui.M3dView.active3dView()
                cam_o = om.MPoint()
                dir0 = om.MVector()
                dir1 = om.MVector()
                dir_mid = om.MVector()
                view.viewToWorld(sx0, sy0, cam_o, dir0)
                view.viewToWorld(sx, sy, cam_o, dir1)
                mid_sx = int((sx0 + sx) * 0.5)
                mid_sy = int((sy0 + sy) * 0.5)
                view.viewToWorld(mid_sx, mid_sy, cam_o, dir_mid)
            except Exception:
                _dirty_shape_view()
                return

            # ワールド空間のドラッグ方向 (近接面上の 2 点の差分)
            d = 1.0
            p0w = [cam_o.x + dir0.x * d, cam_o.y + dir0.y * d,
                   cam_o.z + dir0.z * d]
            p1w = [cam_o.x + dir1.x * d, cam_o.y + dir1.y * d,
                   cam_o.z + dir1.z * d]
            d_world = _v3_sub(p1w, p0w)
            d_len = (d_world[0]**2 + d_world[1]**2 + d_world[2]**2)**0.5
            if d_len < 1e-12:
                _dirty_shape_view()
                return
            d_world = [d_world[k] / d_len for k in range(3)]

            # カメラ視線方向 (中間点)
            cam_fwd = [dir_mid.x, dir_mid.y, dir_mid.z]
            cf_len = (cam_fwd[0]**2 + cam_fwd[1]**2 + cam_fwd[2]**2)**0.5
            if cf_len < 1e-12:
                _dirty_shape_view()
                return
            cam_fwd = [cam_fwd[k] / cf_len for k in range(3)]

            # カット平面法線 = cross(d_world, cam_forward)
            cut_normal = _v3_cross(d_world, cam_fwd)
            cn_len = (cut_normal[0]**2 + cut_normal[1]**2
                      + cut_normal[2]**2)**0.5
            if cn_len < 1e-12:
                _dirty_shape_view()
                return
            cut_normal = [cut_normal[k] / cn_len for k in range(3)]

            # カット中心: 中間点レイ → メッシュ交差, なければ BBox 中心
            freecut_mesh = rc.get("mesh_name", mesh_name)
            mesh_fn_rc, mesh_dag_rc = _get_mesh_fn(freecut_mesh)
            ray_src = om.MFloatPoint(cam_o.x, cam_o.y, cam_o.z)
            ray_dir_f = om.MFloatVector(dir_mid.x, dir_mid.y, dir_mid.z)
            hit_pt_f = om.MFloatPoint()
            _hit_u = om.MScriptUtil()
            _hit_u.createFromInt(0)
            hit = mesh_fn_rc.closestIntersection(
                ray_src, ray_dir_f, None, None, False,
                om.MSpace.kWorld, 1e9, False,
                None, hit_pt_f, None, _hit_u.asIntPtr(),
                None, None, None, 1e-6)
            if hit:
                cut_center = [hit_pt_f.x, hit_pt_f.y, hit_pt_f.z]
            else:
                bb = cmds.exactWorldBoundingBox(freecut_mesh)
                cut_center = [(bb[0]+bb[3])*0.5, (bb[1]+bb[4])*0.5,
                              (bb[2]+bb[5])*0.5]

            ring_pts = _compute_ring_by_plane(
                mesh_fn_rc, mesh_dag_rc, cut_center, cut_normal,
                n_ring_eps=rc["n_ring_eps"], vtx_cache=rc.get("vtx_cache"))
            if ring_pts:
                self._s.ring_preview = ring_pts
                rc["center"] = cut_center
                rc["tangent"] = cut_normal
            else:
                self._s.ring_preview = None

            # ドラッグ線(ワールド座標)をVP2描画用に保存
            far = 1000.0
            line_s = [cam_o.x + dir0.x * far, cam_o.y + dir0.y * far,
                      cam_o.z + dir0.z * far]
            line_e = [cam_o.x + dir1.x * far, cam_o.y + dir1.y * far,
                      cam_o.z + dir1.z * far]
            self._s.ring_line = (line_s, line_e)
            _dirty_shape_view()
            return

        # LMB プレビューカーブ更新
        if button == 1 and self._s.preview_end is not None:
            # 対称面に近ければプレビューの終点も面へ吸着させる
            # (リリースで作られる EP の位置と一致させるため)
            pv_pt, _pf, _pb, _pon = _apply_symmetry_constraint(
                mesh_name, world_pt)
            self._s.preview_end = pv_pt
            # スクリーン座標を憶えておき、release でカーブ途中への
            # スナップ判定に使う (メッシュに埋もれたカーブも掴めるように)
            _state_set(self._s, "drag_screen", (float(sx), float(sy)))
            try:
                cn_hover = _DRAG_CN_CACHE.get(node)
                if cn_hover is None:
                    cn_hover = RetopoGuideAccessor(node).read()
                    _DRAG_CN_CACHE[node] = cn_hover
                _snapped, _hit, _already = _resolve_drop_target(
                    cn_hover, self._s.sel_ep, (float(sx), float(sy)),
                    mesh_name)
                _state_set(self._s, "hover_spline", _hit)
            except Exception:
                _state_set(self._s, "hover_spline", None)
            _dirty_shape_view()
            return

        drag_handle = getattr(self._s, "drag_handle", None)
        if button == 2 and drag_handle is not None:
            # ハンドルは面に張り付けない。掴んだ時の奥行きを保ったビュー平面上で
            # 動かす (アーティストが接線を直接描くための操作なので自動フィットも掛けない)。
            acc = RetopoGuideAccessor(node)
            cn = acc.read()
            if drag_handle < len(cn.positions):
                anchor = (getattr(self._s, "drag_handle_anchor", None)
                          or cn.positions[drag_handle])
                pt = _screen_to_view_plane(sx, sy, anchor) or world_pt
                cn.move_cv(drag_handle, pt)
                cn.mark_manual_handle(drag_handle)
                mh = _state_get(self._s, "drag_mirror_handle")
                if mh is not None and mh != drag_handle and mh < len(cn.positions):
                    cn.move_cv(mh, _sym.mirror_point(pt, mesh_name))
                    cn.mark_manual_handle(mh)
                _commit_net_data(node, cn)
            return

        if button == 2 and self._s.drag_ep is not None:
            # Keep topology/metadata owned until release; redraw numeric positions.
            acc = RetopoGuideAccessor(node)
            preview = self._point_preview_for(node)
            cn = preview.read() if preview is not None else acc.read()
            ep  = self._s.drag_ep
            # 対称面への吸着 / 面を跨がせない制限
            snap_pt, face_idx, bary, on_plane = _apply_symmetry_constraint(
                mesh_name, world_pt, side=self._s.drag_side)
            old_pt = list(cn.positions[ep])
            cn.move_cv(ep, snap_pt)
            _translate_manual_handles(
                cn, ep, [snap_pt[k] - old_pt[k] for k in range(3)])
            if face_idx >= 0:
                cn.surface_binding[ep] = (face_idx, bary)
            _recompute_handles_for_ep(cn, ep, mesh_name, draft=True)

            # ---- 対称側も一緒に動かす ----
            mirror_ep = self._s.drag_mirror_ep
            if (mirror_ep is not None and mirror_ep != ep
                    and mirror_ep < len(cn.positions)):
                if on_plane:
                    # 対称面まで来たので相方と同じ位置に重ねる。
                    # 実際の統合はリリース時に行う (ドラッグ中に CV を
                    # 消すとインデックスがずれて掴んでいる点を見失うため)
                    m_pt, m_face, m_bary = snap_pt, face_idx, bary
                else:
                    m_pt, m_face, m_bary = _project_on_mesh(
                        mesh_name, _sym.mirror_point(snap_pt, mesh_name))
                cn.move_cv(mirror_ep, m_pt)
                if m_face >= 0:
                    cn.surface_binding[mirror_ep] = (m_face, m_bary)
                _recompute_handles_for_ep(cn, mirror_ep, mesh_name, draft=True)

            _smooth_moved_ep_routes(cn, {ep, mirror_ep}, mesh_name)
            cn.classify_endpoints()
            # マージ候補を記録 (近くの既存 EP)
            snap_r = _snap_radius(mesh_name)
            ep_set = cn.endpoint_indices()
            nearest = cn.find_nearest_cv(snap_pt, snap_r, exclude=ep)
            if mirror_ep is not None and nearest == mirror_ep:
                # 対称面に乗せたときの統合はリリース時に専用処理で行う
                nearest = None
            if nearest is not None and nearest in ep_set and nearest != ep:
                self._s.merge_target = nearest
            else:
                self._s.merge_target = None

            # ---- カーブの上にホバーしているか ----
            # ここで見つかれば、リリース時にそのカーブを分割して
            # 掴んでいる EP を交点にする。判定はスクリーン空間で行う
            # (カーブがメッシュに埋もれていても狙えるように)。
            _state_set(self._s, "drag_screen", (float(sx), float(sy)))
            if self._s.merge_target is None:
                excl = {ep}
                if mirror_ep is not None:
                    excl.add(mirror_ep)
                _state_set(self._s, "hover_spline",
                           _find_spline_under_screen(cn, float(sx), float(sy),
                                                     exclude_eps=excl,
                                                     mesh_name=mesh_name))
            else:
                _state_set(self._s, "hover_spline", None)
            if preview is not None:preview.write(cn)
            else:_commit_net_data(node, cn)


    def release(self):
        try:
            self._release_impl()
        except Exception:
            om.MGlobal.displayError("[RetopoGuide] release error:\n" + traceback.format_exc())
        finally:
            self._close_undo()


    def _release_impl(self):
        stroke = self._finish_relax(True)
        if stroke:
            if not stroke['moved']:
                self._merge_shift_click(stroke['node'], stroke['snapped'])
            return
        point_data = self._finish_point(True, take=True)
        drag_handle = getattr(self._s, "drag_handle", None)
        mirror_handle = _state_get(self._s, "drag_mirror_handle")
        _state_set(self._s, "drag_handle", None)
        _state_set(self._s, "drag_handle_anchor", None)
        _state_set(self._s, "drag_mirror_handle", None)
        if drag_handle is not None:
            # 手で置いたハンドル (とその対称側) は固定し、同じスプラインの
            # もう一方だけ面に載るよう張り直す。
            moved = {drag_handle}
            if mirror_handle is not None:
                moved.add(mirror_handle)
            node = cmds.optionVar(q="retopoGuideContext_node") or ""
            if node and cmds.objExists(node):
                acc = RetopoGuideAccessor(node)
                cn = acc.read()
                for si, sp in enumerate(cn.splines):
                    if sp[1] in moved or sp[2] in moved:
                        if not cn.spline_has_manual_handle(si) or (
                                sp[1] in cn.manual_handles
                                and sp[2] in cn.manual_handles):
                            continue
                        _fit_spline_handles_to_mesh(cn, si, acc.mesh_name)
                _commit_net_data(node, cn)
            return

        drag_ep = self._s.drag_ep
        merge_target = self._s.merge_target
        drag_mirror_ep = self._s.drag_mirror_ep
        self._s.drag_ep = None
        self._s.merge_target = None
        _state_set(self._s, "drag_mirror_ep", None)
        _state_set(self._s, "drag_side", None)

        # ---- MMB ドラッグの後始末 ----
        # ドラッグ中は下書き品質でハンドルを張っているので、
        # ここで最終品質に張り直す。
        if drag_ep is not None:
            drag_screen = getattr(self._s, "drag_screen", None)
            _state_set(self._s, "drag_screen", None)
            _state_set(self._s, "hover_spline", None)
            node = cmds.optionVar(q="retopoGuideContext_node") or ""
            if not (node and cmds.objExists(node)):
                return
            acc = RetopoGuideAccessor(node)
            cn = point_data if point_data is not None else acc.read()
            mesh_name = acc.mesh_name
            refit = []

            if merge_target is not None:
                _merge_two_eps(cn, ep_keep=merge_target, ep_remove=drag_ep)
                refit.append(merge_target)
                om.MGlobal.displayInfo("[RetopoGuide] merged EP {} into {}".format(
                    drag_ep, merge_target))
            elif (drag_mirror_ep is not None and drag_mirror_ep != drag_ep
                    and _sym.is_enabled()
                    and drag_ep < len(cn.positions)
                    and _sym.on_symmetry_plane(cn.positions[drag_ep],
                                               mesh_name,
                                               _mirror_tol(mesh_name))):
                # 対称面まで持ってきたので相方と統合する
                _merge_two_eps(cn, ep_keep=drag_ep, ep_remove=drag_mirror_ep)
                refit.append(drag_ep)
                om.MGlobal.displayInfo(
                    "[RetopoGuide] 対称面に乗ったので EP {} と {} を"
                    "統合しました".format(drag_ep, drag_mirror_ep))
            else:
                # ---- カーブの上で離した → そのカーブを分割して交点にする ----
                attached = False
                if drag_screen is not None and drag_ep < len(cn.positions):
                    excl = {drag_ep}
                    if drag_mirror_ep is not None:
                        excl.add(drag_mirror_ep)
                    hit = _find_spline_under_screen(
                        cn, drag_screen[0], drag_screen[1], exclude_eps=excl,
                        mesh_name=mesh_name)
                    if hit is not None:
                        attached = _attach_ep_to_spline(
                            cn, drag_ep, hit[0], hit[1], mesh_name)
                if attached:
                    refit.append(drag_ep)
                    if drag_mirror_ep is not None and drag_mirror_ep != drag_ep:
                        refit.append(drag_mirror_ep)
                    om.MGlobal.displayInfo(
                        "[RetopoGuide] EP {} をカーブ上の交点にしました".format(
                            drag_ep))
                    if drag_mirror_ep is not None and drag_mirror_ep != drag_ep:
                        _mirror_attach_ep_to_spline(
                            cn, drag_ep, drag_mirror_ep, mesh_name)
                else:
                    refit.append(drag_ep)
                    if (drag_mirror_ep is not None
                            and drag_mirror_ep != drag_ep):
                        refit.append(drag_mirror_ep)

            for e in refit:
                if e is not None and e < len(cn.positions):
                    _recompute_handles_for_ep(cn, e, mesh_name)
            _smooth_moved_ep_routes(cn, refit, mesh_name)
            cn.classify_endpoints()
            _commit_net_data(node, cn)
            return

        # ---- リングカット 確定 ----
        rc = self._s.ring_cut
        ring_preview = self._s.ring_preview
        self._s.ring_cut = None
        self._s.ring_preview = None
        self._s.ring_line = None
        if rc is not None and ring_preview:
            node = cmds.optionVar(q="retopoGuideContext_node") or ""
            if node and cmds.objExists(node):
                acc = RetopoGuideAccessor(node)
                cn = acc.read()
                mesh_name = acc.mesh_name
                _create_ring_curve(cn, mesh_name, ring_preview)
                _commit_net_data(node, cn)
                om.MGlobal.displayInfo(
                    "[RetopoGuide] リングカーブを作成しました ({} EP)".format(
                        len(ring_preview)))
            _dirty_shape_view()
            return

        preview_end = self._s.preview_end
        press_screen = getattr(self._s, "press_screen", None)
        drag_screen = getattr(self._s, "drag_screen", None)
        self._s.preview_end = None
        _state_set(self._s, "press_screen", None)
        _state_set(self._s, "drag_screen", None)
        _state_set(self._s, "hover_spline", None)
        _DRAG_CN_CACHE.clear()

        if preview_end is None or self._s.sel_ep is None:
            return

        # プレビューからスプライン確定
        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if not node or not cmds.objExists(node):
            self._s.sel_ep = None
            _dirty_shape_view()
            return

        acc       = RetopoGuideAccessor(node)
        cn        = acc.read()
        mesh_name = acc.mesh_name

        # 始点位置を取得
        sel_ep = self._s.sel_ep
        if sel_ep < len(cn.positions):
            start_pos = cn.positions[sel_ep]
        else:
            self._s.sel_ep = None
            _dirty_shape_view()
            return

        # 始点と終点の距離が短い場合はスプライン生成せずプレビューのみクリア
        # (クリックだけでドラッグしなかった = 次のクリックを待つ)
        #
        # 判定はスクリーン空間の移動量で行う。3D 距離で判定すると、
        # メッシュが大きくカーブネットのマス目が細かい場合に
        # 「画面上ではしっかりドラッグしたのに snap_r 未満」となって
        # 接続が黙って無視されてしまう。
        snap_r = _snap_radius(mesh_name)
        if press_screen is not None and drag_screen is not None:
            moved_px = math.hypot(drag_screen[0] - press_screen[0],
                                  drag_screen[1] - press_screen[1])
            is_click = moved_px < _CLICK_SLOP_PX
        else:
            dist2 = sum((preview_end[k] - start_pos[k]) ** 2 for k in range(3))
            is_click = dist2 < snap_r * snap_r
        if is_click:
            # ドラッグなし: sel_ep を維持して次のクリックを待つ
            _dirty_shape_view()
            return

        # 画面上でカーブに重なっているか (ドラッグ中のハイライトと同じ判定)
        hit = None
        snapped = None
        already = None
        if drag_screen is not None:
            snapped, hit, already = _resolve_drop_target(
                cn, sel_ep, drag_screen, mesh_name)
        else:
            # ビューが取れない場合のみ 3D 距離にフォールバック
            nearest = cn.find_nearest_cv(preview_end, snap_r)
            ep_set = cn.endpoint_indices()
            snapped = (nearest if (nearest is not None and nearest in ep_set)
                       else None)
            if (snapped is not None and snapped != sel_ep
                    and _spline_exists(cn, sel_ep, snapped)):
                already = snapped
                snapped = None

        if snapped is not None and snapped == sel_ep:
            # 同じ EP: キャンセル
            self._s.sel_ep = None
            _dirty_shape_view()
            return

        if snapped is None and hit is None and already is not None:
            # 既に繋がっている EP の真上で離した。ここで新規 EP を作ると
            # 既存 EP に重なった不要な点ができるのでキャンセルする。
            om.MGlobal.displayWarning(
                "[RetopoGuide] EP {} とは既に接続済みよ。".format(already))
            self._s.sel_ep = None
            _dirty_shape_view()
            return

        if snapped is not None:
            new_sp = _add_spline_to_cn(cn, mesh_name, sel_ep, snapped)
            _split_splines_at_intersections(cn, new_sp, mesh_name, snap_r * 0.5)
            _mirror_spline(cn, mesh_name, sel_ep, snapped, snap_r * 0.5)
            om.MGlobal.displayInfo("[RetopoGuide] spline: {}-->{}".format(
                sel_ep, snapped))
        elif hit is not None:
            # カメラから見てカーブの途中に重なっているのでそこを接続先にする。
            # カーブがポリゴンに埋もれていても掴めるよう、判定は 3D 距離では
            # なくスクリーン空間で行う。
            sp_hit, t_hit, _wp = hit
            new_ep = _split_spline_at(cn, sp_hit, t_hit, mesh_name)
            new_sp = _add_spline_to_cn(cn, mesh_name, sel_ep, new_ep)
            _split_splines_at_intersections(
                cn, new_sp, mesh_name, snap_r * 0.5)
            _mirror_spline(cn, mesh_name, sel_ep, new_ep, snap_r * 0.5)
            om.MGlobal.displayInfo(
                "[RetopoGuide] spline: {}-->{}(カーブ上に交点を作成)".format(
                    sel_ep, new_ep))
        else:
            # 新規 EP を作成してスプライン接続
            # 対称面の近くなら面の上へ吸着させる
            snap_pt, face_idx, bary, _on_plane = \
                _apply_symmetry_constraint(mesh_name, preview_end)
            if face_idx >= 0:
                new_ep = cn.add_cv(snap_pt, surface=(face_idx, bary))
            else:
                new_ep = cn.add_cv(snap_pt)
            new_sp = _add_spline_to_cn(cn, mesh_name, sel_ep, new_ep)
            _split_splines_at_intersections(
                cn, new_sp, mesh_name, snap_r * 0.5)
            _mirror_spline(cn, mesh_name, sel_ep, new_ep, snap_r * 0.5)
            om.MGlobal.displayInfo("[RetopoGuide] spline: {}-->{}(new)".format(
                sel_ep, new_ep))

        self._s.sel_ep = None
        _commit_net_data(node, cn)


    def delete_selected_ep(self) -> None:
        """選択中の EP とそれに繋がる全スプラインを削除する。"""
        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if not node or not cmds.objExists(node):
            return
        ep = self._s.sel_ep
        if ep is None:
            om.MGlobal.displayWarning("[RetopoGuide] 削除: EP が選択されていません")
            return
        acc = RetopoGuideAccessor(node)
        cn = acc.read()
        if not cn.splines and not cn.is_standalone(ep):
            return
        mesh_name = acc.mesh_name
        # 対称化が有効なら反対側も一緒に消す。
        # 消す前に相手を探しておかないと、_remove_ep でスプラインが消えて
        # EP として認識されなくなり見つけられなくなる。
        mirror_ep = None
        if _sym.is_enabled():
            mirror_ep = _sym.find_mirror_ep(cn, mesh_name, ep,
                                            _mirror_tol(mesh_name))
        _remove_ep(cn, ep, mesh_name)
        if mirror_ep is not None and mirror_ep != ep:
            _remove_ep(cn, mirror_ep, mesh_name)
        self._s.sel_ep = None
        self._s.preview_end = None
        _commit_net_data(node, cn)
        om.MGlobal.displayInfo("[RetopoGuide] EP {} を削除しました".format(ep))


    def enter(self) -> None:
        """draggerContext 進入時: controlPoints を焼き込み + 状態リセット。"""
        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if node and cmds.objExists(node):
            _sync_ep_positions_back(node)
        self._s.sel_ep  = None
        self._s.drag_ep = None
        self._s.preview_end = None
        self._s.merge_target = None
        _state_set(self._s, "drag_mirror_ep", None)
        _state_set(self._s, "drag_side", None)
        # ツール中はリバインドを保留 (抜けた時にまとめて 1 回)
        _rebind.tool_entered(node)


    def exit(self) -> None:
        """draggerContext 離脱時: 状態リセット + 保留していたリバインドを実行。"""
        try:
            self._finish_relax(True)
            self._finish_point(True)
        finally:self._close_undo()
        self._s.sel_ep  = None
        self._s.drag_ep = None
        self._s.preview_end = None
        self._s.merge_target = None
        _state_set(self._s, "drag_mirror_ep", None)
        _state_set(self._s, "drag_side", None)
        _rebind.tool_exited()


    # ===========================================================================
    # EP ロケーター同期 / 選択 / 削除ヘルパー

    # -------------------------------------------------------------------
    # Scene callbacks (from curve_net_edit.py D-group)
    # -------------------------------------------------------------------

    def on_selection_changed(self) -> None:
        """Maya の選択変更時にコンポーネント選択を sel_ep に反映する。"""
        if self._s._is_scene_clearing:
            return
        try:
            if cmds.currentCtx() == _DRAGGER_CTX:
                return
        except Exception:
            pass

        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        found_ep = None

        sel = cmds.ls(selection=True) or []
        for s in sel:
            # コンポーネント選択: "shape.cv[0]" / "shape.vtx[0]"
            if ".cv[" in s or ".vtx[" in s:
                try:
                    idx = int(s.split("[")[-1].rstrip("]"))
                    if node and cmds.objExists(node):
                        cn = RetopoGuideAccessor(node).read()
                        ep_set = cn.endpoint_indices()
                        if idx in ep_set:
                            found_ep = idx
                except Exception:
                    pass
                break

            # 後方互換: EP ロケーター選択
            try:
                shapes = cmds.listRelatives(s, shapes=True,
                                            type=kEPNodeName) or []
            except Exception:
                shapes = []
            if shapes:
                try:
                    found_ep = cmds.getAttr("{}.epIndex".format(shapes[0]))
                except Exception:
                    pass
                break

        if found_ep != self._s.sel_ep:
            self._s.sel_ep = found_ep
            _dirty_shape_view()


    def handle_delete(self) -> None:
        """コンポーネント選択または EP ロケーター選択から EP を削除する。"""
        node = cmds.optionVar(q="retopoGuideContext_node") or ""

        # --- コンポーネント選択チェック ---
        sel = cmds.ls(selection=True) or []
        comp_eps = set()
        for s in sel:
            if ".cv[" in s or ".vtx[" in s:
                try:
                    idx = int(s.split("[")[-1].rstrip("]"))
                    comp_eps.add(idx)
                except Exception:
                    pass
        if comp_eps and node and cmds.objExists(node):
            cn = RetopoGuideAccessor(node).read()
            from Aru_RetopoTool.symmetry_ops import delete_targets
            comp_eps,_=delete_targets(node,comp_eps)
            cn.splines = [sp for sp in cn.splines
                          if sp[0] not in comp_eps
                          and sp[3] not in comp_eps]
            self._s.sel_ep = None
            _commit_net_data(node, cn)
            om.MGlobal.displayInfo("[RetopoGuide] EP を削除しました")
            return

        # --- 後方互換: EP ロケーター選択チェック ---
        sel_xf = cmds.ls(selection=True, type="transform") or []
        net_updates: dict = {}
        for s in sel_xf:
            try:
                shapes = cmds.listRelatives(s, shapes=True, type=kEPNodeName) or []
            except Exception:
                shapes = []
            if shapes:
                try:
                    ep_idx = cmds.getAttr("{}.epIndex".format(shapes[0]))
                except Exception:
                    continue
                loc_parent = cmds.listRelatives(s, parent=True) or []
                if loc_parent:
                    grp = loc_parent[0]
                    if grp.endswith(_LOC_GRP_SUFFIX):
                        net_xf = grp[:-len(_LOC_GRP_SUFFIX)]
                        net_shapes = cmds.listRelatives(
                            net_xf, shapes=True, type=kPluginNodeName) or []
                        if net_shapes:
                            net_updates.setdefault(net_shapes[0], set()).add(ep_idx)

        if net_updates:
            for net_node, ep_set_del in net_updates.items():
                cn = RetopoGuideAccessor(net_node).read()
                from Aru_RetopoTool.symmetry_ops import delete_targets
                ep_set_del,_=delete_targets(net_node,ep_set_del)
                cn.splines = [sp for sp in cn.splines
                              if sp[0] not in ep_set_del
                              and sp[3] not in ep_set_del]
                self._s.sel_ep = None
                _commit_net_data(net_node, cn)
            om.MGlobal.displayInfo("[RetopoGuide] EP を削除しました")
            return

        # dragger context 内で sel_ep がある場合はそちらを削除
        ep = self._s.sel_ep
        if ep is not None:
            if node and cmds.objExists(node):
                cn = RetopoGuideAccessor(node).read()
                if cn.splines:
                    cn.splines = [sp for sp in cn.splines
                                  if sp[0] != ep and sp[3] != ep]
                    self._s.sel_ep = None
                    _commit_net_data(node, cn)
                    om.MGlobal.displayInfo(
                        "[RetopoGuide] EP {} を削除しました".format(ep))
                    return


    def on_ep_maybe_moved(self) -> None:
        """Undo/Redo/ToolChanged 後にビューを更新する。"""
        if self._s._is_scene_clearing:
            return
        try:
            _dirty_shape_view()
        except Exception:
            pass


    # ===========================================================================
    # コンポーネントモード / 右クリックメニュー
    # ===========================================================================

    def enter_component_mode(self, mode="all", *_args):
        """retopoGuideNode をコンポーネントモードに切り替える。

        Parameters
        ----------
        mode : str
            "ep" — EP のみ, "handle" — ハンドルのみ, "all" — 全ポイント
        """
        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if not node or not cmds.objExists(node):
            # 選択中のノードから取得
            sel = cmds.ls(selection=True, long=True) or []
            for s in sel:
                shape = _find_shape_node(s)
                if shape:
                    node = shape
                    break
        if not node or not cmds.objExists(node):
            om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
            return

        shape = _find_shape_node(node)
        if not shape:
            return
        parent = (cmds.listRelatives(shape, parent=True, fullPath=True)
                  or [shape])[0]

        self._s._component_mode = mode
        cmds.optionVar(sv=("retopoGuideContext_node", shape))

        # 他のオブジェクトのハイライトを解除 (kSelectMeshVerts 共有のため
        # hilite 状態のメッシュの頂点も矩形選択で拾ってしまう)
        hilited = cmds.ls(hilite=True) or []
        if hilited:
            cmds.hilite(hilited, u=True)

        # コンポーネント選択モードへ切り替え
        cmds.selectMode(component=True)
        cmds.hilite(parent)
        cmds.selectType(allComponents=False)
        cmds.selectType(controlVertex=True)
        # _active_indices を即座に更新させるために VP2 を dirty にする
        _dirty_shape_view()
        om.MGlobal.displayInfo(
            "[RetopoGuide] コンポーネントモード: {}".format(mode))


    def exit_component_mode(self, *_args):
        """オブジェクトモードに戻る。"""
        self._s._component_mode = None
        cmds.hilite(cmds.ls(hilite=True) or [], u=True)
        cmds.selectMode(object=True)
        cmds.select(cl=True)
        _dirty_shape_view()


    def select_nearest_component(self, sx=None, sy=None, mode=None, add=False):
        """スクリーン座標に最も近い EP / ハンドルを .vtx[i] で選択する。

        Parameters
        ----------
        sx, sy : int or None
            スクリーン座標。None の場合はカーソル位置を取得。
        mode : str or None
            "ep" / "handle" / None=現在のモード。
        add : bool
            True の場合は追加選択。
        """
        node = cmds.optionVar(q="retopoGuideContext_node") or ""
        shape = _find_shape_node(node) if node else None
        if not shape or not cmds.objExists(shape):
            return

        if mode is None:
            mode = (self._s._component_mode or "all")

        positions, cn = _get_net_data_positions(shape)
        if not positions:
            return

        ep_set = cn.endpoint_indices()
        handle_set = set()
        for sp in cn.splines:
            handle_set.add(sp[1])
            handle_set.add(sp[2])

        if mode == "ep":
            candidates = sorted(ep_set)
        elif mode == "handle":
            candidates = sorted(handle_set)
        else:
            candidates = list(range(len(positions)))

        if not candidates:
            return

        # スクリーン座標でソートして最近傍を取得
        if sx is None or sy is None:
            # 現在のマウス位置 — draggerContext のクエリで取得試行
            try:
                ap = cmds.draggerContext(_DRAGGER_CTX, q=True, anchorPoint=True)
                sx, sy = int(ap[0]), int(ap[1])
            except Exception:
                return

        best_idx = None
        best_dist = 1e30
        for idx in candidates:
            if idx >= len(positions):
                continue
            scr = _world_to_screen(positions[idx])
            if scr is None:
                continue
            dx = scr[0] - sx
            dy = scr[1] - sy
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best_idx = idx

        if best_idx is not None and best_dist < 900:  # 30px 半径
            comp_str = "{}.vtx[{}]".format(shape, best_idx)
            if add:
                cmds.select(comp_str, add=True)
            else:
                cmds.select(comp_str, r=True)


    # ---------------------------------------------------------------------------

    def start_scriptjob(self) -> None:
        """SelectionChanged / Undo / Redo / ToolChanged scriptJob を開始する。"""
        if self._s._sel_sj is not None:
            return
        _cb_sel = ("import __main__ as _m; "
                   "_m.__retopoGuideCtx__.on_selection_changed()")
        _cb_sync = ("import __main__ as _m; "
                    "_m.__retopoGuideCtx__.on_ep_maybe_moved()")
        jobs = []
        jobs.append(cmds.scriptJob(event=["SelectionChanged", _cb_sel]))
        jobs.append(cmds.scriptJob(event=["Undo", _cb_sync]))
        jobs.append(cmds.scriptJob(event=["Redo", _cb_sync]))
        jobs.append(cmds.scriptJob(event=["ToolChanged", _cb_sync]))
        self._s._sel_sj = jobs


    def stop_scriptjob(self) -> None:
        """scriptJob を停止する。"""
        self._cancel_relax()
        jobs = self._s._sel_sj
        if jobs is not None:
            for sj in (jobs if isinstance(jobs, list) else [jobs]):
                try:
                    cmds.scriptJob(kill=sj, force=True)
                except Exception:
                    pass
            self._s._sel_sj = None
        # nodeDeleted scriptJob もクリーンアップ
        for xf, sj in list(_nd_sj_map.items()):
            try:
                cmds.scriptJob(kill=sj, force=True)
            except Exception:
                pass
        _nd_sj_map.clear()


    def register_node_deleted_sj(self, node_name: str) -> None:
        """retopoGuideNode 削除時のクリーンアップ scriptJob を登録する (後方互換)。"""
        parent_xf = _get_net_transform(node_name)
        if parent_xf in _nd_sj_map:
            return
        grp_name = parent_xf + _LOC_GRP_SUFFIX
        # 旧ロケーターグループが存在する場合のみクリーンアップ
        if not cmds.objExists(grp_name):
            return
        # nodeDeleted コールバック: visibility=False にして孤児リストに追加
        _cb = (
            'import maya.cmds as cmds; '
            'grp = "{grp}"; '
            'cmds.setAttr(grp + ".visibility", False) if cmds.objExists(grp) else None; '
            'import __main__; '
            '__main__.__retopoGuidePlugin__._orphaned_loc_groups.append("{grp}")'
            .format(grp=grp_name)
        )
        try:
            sj = cmds.scriptJob(nodeDeleted=[parent_xf, _cb])
            _nd_sj_map[parent_xf] = sj
        except Exception:
            pass

