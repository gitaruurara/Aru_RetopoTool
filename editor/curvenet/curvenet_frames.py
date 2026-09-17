"""
curvenet_frames.py — スケールドフレーム & 変形勾配 (§3)
================================================================
Implements §3 of:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)

パイプライン
--------
1. カーブネットポリラインのサンプリング  (sample_curves / sample_curves_from_maya)
2. 交差検出                       (detect_intersections)
3. コーナー法線 + 幅             (compute_corner_frames)
4. 平行移動 + ブレンド         (compute_all_frames)
5. 変形勾配                       (compute_deformation_gradients)
6. f_c / x_c の組み立て         (assemble_gradient_constraints /
                                assemble_position_constraints)

コア計算は numpy のみ。Maya ヘルパーはオプションの便利ラッパー。
"""

from __future__ import annotations

import numpy as np
from typing import Optional


# ======================================================================
# ベクトルユーティリティ
# ======================================================================

def _rodrigues(v: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """単位軸 *axis* まわりに *v* を *angle* (ラジアン) 回転する。

    Parameters
    ----------
    v : np.ndarray
        回転するベクトル (3,)。
    axis : np.ndarray
        回転軸 (単位ベクトル, 3,)。
    angle : float
        回転角 (ラジアン)。

    Returns
    -------
    np.ndarray
        回転後のベクトル (3,)。
    """
    c, s = float(np.cos(angle)), float(np.sin(angle))
    return c * v + s * np.cross(axis, v) + (1.0 - c) * np.dot(axis, v) * axis


def _safe_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v * 0.0


def _perp_to(v: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """*ref* を *v* に直交に投影し正規化する。

    Parameters
    ----------
    v : np.ndarray
        基準方向 (単位ベクトル, 3,)。
    ref : np.ndarray
        投影元ベクトル (3,)。

    Returns
    -------
    np.ndarray
        *v* に直交な単位ベクトル (3,)。
    """
    p = ref - np.dot(ref, v) * v
    n = float(np.linalg.norm(p))
    if n < 1e-10:
        for fb in (np.array([0., 1., 0.]), np.array([0., 0., 1.]),
                   np.array([1., 0., 0.])):
            p = fb - np.dot(fb, v) * fb
            if float(np.linalg.norm(p)) > 1e-6:
                break
    return _safe_normalize(p)


# ======================================================================
# 0. カーブチェーン構築 (§3 交点 / アンカー / カーブ)
# ======================================================================

def classify_spline_endpoints(splines: list) -> tuple[dict, dict]:
    """スプライン端点を交点 / ノード / アンカーに分類する (§3)。

    論文 §3「交点、アンカー、カーブ」の定義:

    - **intersection** : 3 本以上のスプラインで共有される端点
    - **anchor**       : 1 本のスプラインのみに接続する端点
    - **node**         : 2 本のスプラインを繋ぐだけのラベル無し端点
      (カーブの途中であり、ここでカーブを切ってはならない)

    Parameters
    ----------
    splines : list[tuple[int, int, int, int]]
        3 次ベジェの制御点インデックスタプル。

    Returns
    -------
    ep2sp : dict[int, list[int]]
        端点インデックス → 接続スプラインインデックスのリスト。
    ep_type : dict[int, str]
        端点インデックス → 'intersection' | 'node' | 'anchor'。
    """
    ep2sp: dict[int, list[int]] = {}
    for si, sp in enumerate(splines):
        for ep in (sp[0], sp[3]):
            ep2sp.setdefault(ep, []).append(si)

    ep_type: dict[int, str] = {}
    for ep, sps in ep2sp.items():
        n = len(sps)
        if n >= 3:
            ep_type[ep] = 'intersection'
        elif n == 2:
            ep_type[ep] = 'node'
        else:
            ep_type[ep] = 'anchor'
    return ep2sp, ep_type


def build_curve_chains(splines: list) -> list[list[int]]:
    """スプラインを *カーブ* (交点/アンカー間のチェーン) にグループ化する (§3)。

    論文 §3: 交点および/またはアンカーを繋ぐ連続したスプラインのシーケンス
    を 1 本のカーブとする。どちらの端点もラベルを持たない残りのスプライン
    は孤立した閉じたカーブとしてグループ化する。

    Parameters
    ----------
    splines : list[tuple[int, int, int, int]]
        3 次ベジェの制御点インデックスタプル。

    Returns
    -------
    list[list[int]]
        カーブごとのスプラインインデックスのチェーン。
        :func:`sample_curves` の *curves* 引数に渡す。
    """
    ep2sp, ep_type = classify_spline_endpoints(splines)
    visited: set[int] = set()
    curves: list[list[int]] = []

    def _walk(start_ep: int, first_sp: int) -> list[int]:
        chain = [first_sp]
        visited.add(first_sp)
        sp = splines[first_sp]
        others = [x for x in (sp[0], sp[3]) if x != start_ep]
        cur_ep = others[0] if others else None
        while cur_ep is not None:
            # 'node' のみチェーンを継続する (交点/アンカーはカーブの端)
            if ep_type.get(cur_ep, 'anchor') != 'node':
                break
            next_sps = [s for s in ep2sp.get(cur_ep, []) if s not in visited]
            if not next_sps:
                break
            ns = next_sps[0]
            chain.append(ns)
            visited.add(ns)
            nsp = splines[ns]
            others = [x for x in (nsp[0], nsp[3]) if x != cur_ep]
            cur_ep = others[0] if others else None
        return chain

    # 交点 / アンカーを起点に走査 (決定的な順序のため sorted)
    for ep in sorted(ep2sp.keys()):
        if ep_type.get(ep) not in ('intersection', 'anchor'):
            continue
        for sp_idx in ep2sp[ep]:
            if sp_idx not in visited:
                curves.append(_walk(ep, sp_idx))

    # 残り: ラベル無し端点のみで繋がった孤立した閉じたカーブ (§3)
    for si in range(len(splines)):
        if si in visited:
            continue
        curves.append(_walk(splines[si][0], si))

    return curves


def _orient_chain(chain: list, splines: list) -> list[tuple]:
    """チェーン内のスプラインを首尾一貫した向きに揃える。

    :func:`build_curve_chains` が返すチェーンは接続順ではあるが、個々の
    スプラインの向き (i0→i3) は揃っていない。揃えないまま連結して
    サンプリングすると接合点でカーブが折り返し、接線・弧長が破綻する。

    Parameters
    ----------
    chain : list[int]
        スプラインインデックスのチェーン。
    splines : list[tuple[int, int, int, int]]
        制御点インデックスタプル。

    Returns
    -------
    list[tuple[int, int, int, int]]
        前のスプラインの終端に始点が繋がるよう必要に応じて反転した
        制御点インデックスタプルのリスト。
    """
    if not chain:
        return []

    first = tuple(splines[chain[0]])
    if len(chain) == 1:
        return [first]

    # 先頭スプラインの向きは 2 番目との共有端点から決める
    second = tuple(splines[chain[1]])
    shared = {first[0], first[3]} & {second[0], second[3]}
    if first[3] in shared:
        cur = first
    elif first[0] in shared:
        cur = (first[3], first[2], first[1], first[0])
    else:
        cur = first

    out = [cur]
    prev_end = cur[3]
    for sp_idx in chain[1:]:
        sp = tuple(splines[sp_idx])
        if sp[0] == prev_end:
            cur = sp
        elif sp[3] == prev_end:
            cur = (sp[3], sp[2], sp[1], sp[0])
        else:
            # 非連結 (データ不整合) — そのまま採用して破綻を局所化する
            cur = sp
        out.append(cur)
        prev_end = cur[3]
    return out


# ======================================================================
# 1. サンプリング
# ======================================================================

def sample_curves(positions_pool: np.ndarray,
                  splines: list,
                  curves: list,
                  n_per_spline: int = 5,
                  avg_edge_length: float = 0.0,
                  rest_positions_pool: Optional[np.ndarray] = None,
                  ) -> list[dict]:
    """RetopoGuideData 形式のカーブネットをポリラインにサンプリングする。

    Parameters
    ----------
    positions_pool : np.ndarray
        全制御点位置 (P, 3)。ベジェ評価に使用。
    splines : list[tuple[int, int, int, int]]
        3次ベジェのインデックスタプル (i0, i1, i2, i3)。
    curves : list[list[int]]
        スプラインインデックスのチェーン
        (交差点/アンカー間、classify_endpoints() 由来)。
    n_per_spline : int
        スプラインセグメントごとの基本サンプル数。
        *avg_edge_length* > 0 の場合はスケール係数として使用される
        (論文 §3: デフォルト 5)。
    avg_edge_length : float
        サーフェスメッシュのレスト平均エッジ長。> 0 の場合、論文 §3 に従い
        スプラインごとのサンプル数を
        ``n_per_spline * (CP ポリライン長 / avg_edge_length)``
        で適応的に決定する。0 以下の場合は固定値 *n_per_spline* を使用。
    rest_positions_pool : np.ndarray, optional
        レストポーズ (ニュートラルポーズ) の制御点位置。
        論文 §3 のサンプル数計算に使用。指定時は *positions_pool* ではなく
        こちらの CP ポリライン長で nk を決定し、ベジェ評価は
        *positions_pool* で行う。
        ポーズ時の CP 長変化による int 丸め不連続を防止する。

    Returns
    -------
    list[dict]
        カーブごとの dict::

            {
                'positions':   (M, 3)  float   ワールド空間サンプル位置
                'tangents':    (M, 3)  float   単位接線ベクトル
                'seg_lengths': (M-1,)  float   各セグメントの弧長
            }
    """
    _adaptive = avg_edge_length > 1e-12
    # nk 計算用の CP プール: rest が指定されていればそちらを使用 (論文 §3)
    _nk_pool = (np.asarray(rest_positions_pool)
                if rest_positions_pool is not None else positions_pool)

    results = []
    for chain in curves:
        # チェーン内のスプライン向きを揃える (接合点での折り返しを防止)
        oriented = _orient_chain(chain, splines)
        pts_all = []
        for si, sp_cp in enumerate(oriented):
            i0, i1, i2, i3 = sp_cp
            p0 = np.asarray(positions_pool[i0])
            p1 = np.asarray(positions_pool[i1])
            p2 = np.asarray(positions_pool[i2])
            p3 = np.asarray(positions_pool[i3])
            if _adaptive:
                # 論文 §3: CP ポリライン長はニュートラルポーズで計算 →
                # nk は rest CP から算出、ベジェ評価は posed CP (p0-p3) で行う
                rp0 = np.asarray(_nk_pool[i0])
                rp1 = np.asarray(_nk_pool[i1])
                rp2 = np.asarray(_nk_pool[i2])
                rp3 = np.asarray(_nk_pool[i3])
                cp_poly_len = (float(np.linalg.norm(rp1 - rp0))
                               + float(np.linalg.norm(rp2 - rp1))
                               + float(np.linalg.norm(rp3 - rp2)))
                nk = max(3, int(n_per_spline * cp_poly_len
                                / avg_edge_length + 0.5))
            else:
                nk = n_per_spline
            for k in range(nk):
                if si > 0 and k == 0:
                    continue  # 接合点での重複をスキップ
                t = k / max(nk - 1, 1)
                mt = 1.0 - t
                pt = (mt ** 3 * p0 + 3 * mt ** 2 * t * p1 +
                      3 * mt * t ** 2 * p2 + t ** 3 * p3)
                pts_all.append(pt)
        raw_pts = np.array(pts_all, dtype=float)
        M_raw = len(raw_pts)
        if M_raw < 2:
            results.append(None)
            continue

        # --- 弧長リサンプリング (§3 Pixar 論文) ---
        # パラメトリックサンプルに沿った累積弧長を計算
        raw_diffs = np.diff(raw_pts, axis=0)
        raw_seg_lens = np.linalg.norm(raw_diffs, axis=1)
        cum_len = np.concatenate([[0.0], np.cumsum(raw_seg_lens)])
        total_len = float(cum_len[-1])
        if total_len < 1e-12:
            results.append(None)
            continue

        # 出力サンプル数: 適応モードでは raw_pts 数をそのまま使用、
        # 固定モードでは n_per_spline * スプライン数
        M = max(len(raw_pts), 3) if _adaptive else max(n_per_spline * len(chain), 3)
        target_s = np.linspace(0.0, total_len, M)
        pts = np.empty((M, 3))
        for j in range(M):
            # target_s[j] を含むセグメントを二分探索
            idx = int(np.searchsorted(cum_len, target_s[j], side='right')) - 1
            idx = max(0, min(idx, M_raw - 2))
            seg_len = float(cum_len[idx + 1] - cum_len[idx])
            if seg_len > 1e-14:
                frac = (target_s[j] - cum_len[idx]) / seg_len
            else:
                frac = 0.0
            frac = max(0.0, min(1.0, frac))
            pts[j] = raw_pts[idx] * (1.0 - frac) + raw_pts[idx + 1] * frac

        diffs = np.diff(pts, axis=0)
        seg_lens = np.linalg.norm(diffs, axis=1)
        # 各サンプルの接線 (中央差分、端点は前方/後方差分)
        tangs = np.empty_like(pts)
        for j in range(M):
            if j == 0:
                t = diffs[0]
            elif j == M - 1:
                t = diffs[-1]
            else:
                t = diffs[j - 1] + diffs[j]
            tn = float(np.linalg.norm(t))
            tangs[j] = t / tn if tn > 1e-12 else np.array([1., 0., 0.])
        results.append({
            'positions':   pts,
            'tangents':    tangs,
            'seg_lengths': seg_lens,
        })
    return results


def sample_curves_from_maya(curve_fns, n_samples: int = 100) -> list[dict | None]:
    """Maya NURBS カーブ (MFnNurbsCurve) をポリラインにサンプリングする。

    Parameters
    ----------
    curve_fns : list
        MFnNurbsCurve オブジェクトのリスト。
    n_samples : int
        カーブあたりのサンプル数。

    Returns
    -------
    list[dict | None]
        :func:`sample_curves` と同じ dict 形式。
    """
    import maya.api.OpenMaya as om
    results = []
    for cfn in curve_fns:
        if cfn is None:
            results.append(None)
            continue
        t0, t1 = cfn.knotDomain
        params = np.linspace(t0, t1, n_samples)
        pts = np.empty((n_samples, 3))
        tangs = np.empty((n_samples, 3))
        for j, p in enumerate(params):
            wp = cfn.getPointAtParam(p, om.MSpace.kWorld)
            pts[j] = (wp.x, wp.y, wp.z)
            tv = cfn.tangent(p, space=om.MSpace.kWorld)
            tv.normalize()
            tangs[j] = (tv.x, tv.y, tv.z)
        diffs = np.diff(pts, axis=0)
        seg_lens = np.linalg.norm(diffs, axis=1)
        results.append({
            'positions':   pts,
            'tangents':    tangs,
            'seg_lengths': seg_lens,
            'params':      params,
        })
    return results


# ======================================================================
# 2. 交差検出
# ======================================================================

def detect_intersections(curve_data_list: list[dict | None],
                         tol: float = 1e-3) -> dict:
    """カーブ端点を近接度でクラスタリングし、交差/アンカーを分類する。

    Parameters
    ----------
    curve_data_list : list[dict | None]
        sample_curves / sample_curves_from_maya の出力。
    tol : float
        端点マッチングの距離閾値。

    Returns
    -------
    dict
        以下のキーを持つ::

            'intersections': list[dict]  {
                'pos':     (3,)
                'members': [(curve_idx, side, outgoing_tangent), ...]
            }
            'ep_type':  { (ci, side): 'intersection' | 'anchor' }
            'ep_isect': { (ci, side): intersection_index | -1 }

    Notes
    -----
    論文 §3 の定義に従い、**3 本以上**のカーブ端点が集まる位置のみを交点
    とする。2 本しか集まらない位置は、孤立した閉じたカーブが自分自身に
    戻ってきた場合 (始点 == 終点) であり、交点ではない。
    ここを 2 本で交点と判定すると、コーナー法線 m_i = t_i × t_{i+1} が
    t_{i+1} ≈ -t_i により恒等的に縮退し、法線がワールド軸へ落ちる。
    """
    K = len(curve_data_list)
    ep_pts, ep_tang = {}, {}
    for ci in range(K):
        cd = curve_data_list[ci]
        if cd is None:
            continue
        ep_pts[(ci, 0)] = cd['positions'][0]
        ep_pts[(ci, 1)] = cd['positions'][-1]
        ep_tang[(ci, 0)] = cd['tangents'][0]
        ep_tang[(ci, 1)] = -cd['tangents'][-1]

    ep_keys = list(ep_pts.keys())
    visited = set()
    groups = []
    for k in ep_keys:
        if k in visited:
            continue
        grp = [k]
        visited.add(k)
        for k2 in ep_keys:
            if k2 in visited:
                continue
            if float(np.linalg.norm(ep_pts[k] - ep_pts[k2])) < tol:
                grp.append(k2)
                visited.add(k2)
        groups.append(grp)

    intersections = []
    ep_type = {}
    ep_isect = {}
    for grp in groups:
        if len(grp) >= 3:
            idx = len(intersections)
            pos = np.mean([ep_pts[k] for k in grp], axis=0)
            members = [(k[0], k[1], ep_tang[k]) for k in grp]
            intersections.append({'pos': pos, 'members': members})
            for k in grp:
                ep_type[k] = 'intersection'
                ep_isect[k] = idx
        else:
            for k in grp:
                ep_type[k] = 'anchor'
                ep_isect[k] = -1

    return {
        'intersections': intersections,
        'ep_type': ep_type,
        'ep_isect': ep_isect,
    }


# ======================================================================
# 3. 交差点でのコーナー法線 & 幅
# ======================================================================

def _rotation_between(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
    """単位ベクトル *v_from* を *v_to* へ最短弧で回転する 3×3 回転行列を計算する。

    ベクトルが (反) 平行の場合は単位行列を返す (Rodrigues の公式)。

    Parameters
    ----------
    v_from : np.ndarray
        回転元の単位ベクトル (3,)。
    v_to : np.ndarray
        回転先の単位ベクトル (3,)。

    Returns
    -------
    np.ndarray
        3×3 回転行列。
    """
    c = float(np.clip(np.dot(v_from, v_to), -1.0, 1.0))
    if c > 1.0 - 1e-12:
        return np.eye(3)
    axis = np.cross(v_from, v_to)
    s = float(np.linalg.norm(axis))
    if s < 1e-12:
        # 180-degree case — pick an arbitrary perpendicular axis
        for fb in (np.array([1., 0., 0.]), np.array([0., 1., 0.]),
                   np.array([0., 0., 1.])):
            axis = np.cross(v_from, fb)
            s = float(np.linalg.norm(axis))
            if s > 1e-6:
                break
    axis = axis / max(s, 1e-12)
    # Rodrigues: R = I + sin(θ) K + (1 - cos(θ)) K²
    # θ = arccos(c) なので sin(θ) と cos(θ) を正しく使う
    sin_theta = float(np.sqrt(1.0 - c * c))  # sin(arccos(c))
    K = np.array([[0, -axis[2], axis[1]],
                  [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + sin_theta * K + (1.0 - c) * (K @ K)


def _tangent_pair_rotation(a_rest: np.ndarray, b_rest: np.ndarray,
                           a_posed: np.ndarray, b_posed: np.ndarray):
    """接線ペア (t_i, t_{i+1}) の rest → posed 剛体回転を返す。

    コーナー法線 m_i = t_i × t_{i+1} は **2 本** の接線から決まる。
    そのため rest 法線を片方の接線 t_i の最小回転だけで輸送すると、
    参照法線が真の posed 法線から最大で曲げ角ぶんずれてしまう。
    実測では円柱を曲げたとき dot(m_posed, 輸送された m_rest) が
    cos(曲げ角) で減衰し、90° でちょうど 0 を跨いで符号判定
    (dot < 0) が反転 → 法線が 180° フリップし変形が破綻していた。

    接線ペアが張る正規直交フレーム同士の回転を使えば、参照法線は
    常に真の posed 法線と一致し、符号判定の余裕が 1.0 に保たれる。

    Returns
    -------
    np.ndarray | None
        3×3 回転行列。接線が平行で縮退する場合は None。
    """
    def _frame(a, b):
        e3 = np.cross(a, b)
        n3 = float(np.linalg.norm(e3))
        n1 = float(np.linalg.norm(a))
        if n3 < 1e-8 or n1 < 1e-12:
            return None
        e1 = a / n1
        e3 = e3 / n3
        return np.column_stack((e1, np.cross(e3, e1), e3))

    P_rest = _frame(a_rest, b_rest)
    P_posed = _frame(a_posed, b_posed)
    if P_rest is None or P_posed is None:
        return None
    return P_posed @ P_rest.T


def compute_corner_frames(intersections: list[dict],
                          curve_data_list: list[dict | None],
                          surface_normal_fn=None,
                          reference_corner_frames: dict | None = None,
                          rest_sorted_orders: list[list[int]] | None = None,
                          rest_tangents_at_isect: list[np.ndarray] | None = None,
                          ) -> tuple[dict, list[list[int]], list[np.ndarray]]:
    """交差点でのセグメントごと・片側ごとの法線と幅を計算する (§3)。

    Parameters
    ----------
    intersections : list[dict]
        detect_intersections()['intersections'] の出力。
    curve_data_list : list[dict | None]
        sample_curves / sample_curves_from_maya の出力。
    surface_normal_fn : callable | None
        (pos_3d) -> normal_3d のコールバック (縮退ケース用)。
    reference_corner_frames : dict | None
        レストポーズのコーナーフレーム (出力と同じ構造)。
        rest_tangents_at_isect と併用時、レスト法線を接線回転で
        ポーズに変換し、外積方向の **符号の曖昧性のみ** を解消する。
        法線・幅の値そのものは常にポーズから再計算される (§3)。
    rest_sorted_orders : list[list[int]] | None
        レストポーズ時の CCW ソート順。
        指定時、ポーズ呼び出しでレストのメンバー順序を再利用し、
        n_plus/n_minus の割り当て一貫性を保つ。
    rest_tangents_at_isect : list[np.ndarray] | None
        レストポーズのソート済み接線ベクトル。
        reference_corner_frames と併用し、レスト法線をポーズ接線
        配置へ回転する。

    Returns
    -------
    result : dict
        (ci, side) -> {
            'n_plus': (3,), 'n_minus': (3,),
            'w_plus': float, 'w_minus': float,
        }
    sorted_orders : list[list[int]]
        各交差点の CCW メンバー順序。
        ポーズ計算時に *rest_sorted_orders* として渡す。
    tangents_at_isect : list[np.ndarray]
        各交差点のソート済み接線 (N_at, 3)。
        *rest_tangents_at_isect* として保存・再利用する。
    """
    result = {}
    sorted_orders = []
    tangents_at_isect = []
    for isect_idx, isect in enumerate(intersections):
        members = isect['members']  # [(ci, side, tang), ...]
        if len(members) < 2:
            sorted_orders.append(list(range(len(members))))
            tangents_at_isect.append(np.empty((0, 3)))
            continue

        # --- タンジェントを curve_data_list (posed) から取得 ----------
        t_arr = np.empty((len(members), 3))
        for mi, m in enumerate(members):
            ci_idx, ep_side = m[0], m[1]
            cd = (curve_data_list[ci_idx]
                  if ci_idx < len(curve_data_list) else None)
            if cd is not None and len(cd['tangents']) > 0:
                if ep_side == 0:
                    t_arr[mi] = cd['tangents'][0]
                else:
                    t_arr[mi] = -cd['tangents'][-1]
            else:
                t_arr[mi] = np.asarray(m[2])
        N_at = len(t_arr)

        # ---- Determine sort order ------------------------------------
        if rest_sorted_orders is not None and isect_idx < len(rest_sorted_orders):
            # レストポーズの CCW 順序を再利用し、n_plus/n_minus
            # の一貫性を保証する
            order = rest_sorted_orders[isect_idx]
        else:
            # 接線外積からサーフェス法線を推定
            surf_n = np.zeros(3)
            for i in range(N_at):
                surf_n += np.cross(t_arr[i], t_arr[(i + 1) % N_at])
            sn_len = float(np.linalg.norm(surf_n))
            if sn_len > 1e-10:
                surf_n /= sn_len
            elif surface_normal_fn is not None:
                surf_n = np.asarray(surface_normal_fn(isect['pos']))
            else:
                surf_n = np.array([0., 1., 0.])

            # surf_n まわりにメンバーを CCW ソート
            def _proj(t):
                p = t - np.dot(t, surf_n) * surf_n
                pn = float(np.linalg.norm(p))
                return p / pn if pn > 1e-12 else p

            proj_ts = [_proj(t_arr[i]) for i in range(N_at)]
            ref_vec = proj_ts[0]

            def _angle(pt):
                c = float(np.clip(np.dot(ref_vec, pt), -1., 1.))
                s = float(np.dot(surf_n, np.cross(ref_vec, pt)))
                return float(np.arctan2(s, c))

            order = sorted(range(N_at), key=lambda i: _angle(proj_ts[i]))

        sorted_orders.append(order)
        sorted_members = [members[i] for i in order]
        sorted_tangs = [t_arr[i] for i in order]

        # 交差点での実セグメント長 l_i (§3)
        sorted_lens: list[float] = []
        for sm in sorted_members:
            ci_idx, ep_side = sm[0], sm[1]
            cd = curve_data_list[ci_idx] if ci_idx < len(curve_data_list) else None
            if cd is not None and len(cd['seg_lengths']) > 0:
                sl = cd['seg_lengths']
                sorted_lens.append(float(sl[0]) if ep_side == 0 else float(sl[-1]))
            else:
                sorted_lens.append(1.0)

        # 接線を単位長に正規化
        for i in range(N_at):
            tlen = float(np.linalg.norm(sorted_tangs[i]))
            if tlen > 1e-12:
                sorted_tangs[i] = sorted_tangs[i] / tlen

        # ソート済み接線をレスト接線追跡用に保存
        tangents_at_isect.append(
            np.array([sorted_tangs[i] for i in range(N_at)]))

        # ---- 外積アプローチ (§3) ----
        # コーナー法線 m_i = (t_i × t_{i+1}) / |t_i × t_{i+1}|
        # 縮退フォールバック用 surf_n を推定 (常に必要)
        surf_n_fb = np.zeros(3)
        for i in range(N_at):
            surf_n_fb += np.cross(sorted_tangs[i],
                                  sorted_tangs[(i + 1) % N_at])
        sn_fb_len = float(np.linalg.norm(surf_n_fb))
        if sn_fb_len > 1e-10:
            surf_n_fb /= sn_fb_len
        elif surface_normal_fn is not None:
            surf_n_fb = np.asarray(surface_normal_fn(isect['pos']))
        else:
            surf_n_fb = np.array([0., 1., 0.])

        # レスト外積を事前計算 (符号一貫性チェック用)
        rest_crosses = None
        if rest_tangents_at_isect is not None and isect_idx < len(rest_tangents_at_isect):
            rt = rest_tangents_at_isect[isect_idx]
            if len(rt) == N_at:
                rest_crosses = [
                    np.cross(rt[i], rt[(i + 1) % N_at])
                    for i in range(N_at)
                ]

        # まずクロスプロダクトで法線を計算
        ms = []
        for i in range(N_at):
            ti = sorted_tangs[i]
            ti1 = sorted_tangs[(i + 1) % N_at]
            ci_vec = np.cross(ti, ti1)
            ci_len = float(np.linalg.norm(ci_vec))
            if ci_len < 1e-10:
                # 平行接線 (Tジャンクション, §3)
                ti_prev = sorted_tangs[(i - 1) % N_at]
                ti2 = sorted_tangs[(i + 2) % N_at]
                mi = np.cross(ti_prev, ti) + np.cross(ti1, ti2)
                mi_len = float(np.linalg.norm(mi))
                ms.append(mi / mi_len if mi_len > 1e-10 else surf_n_fb.copy())
            else:
                # 外積の符号をレストと比較し、反転を防止する。
                if rest_crosses is not None:
                    if float(np.dot(ci_vec, rest_crosses[i])) < 0:
                        ci_vec = -ci_vec
                ms.append(ci_vec / ci_len)

        # ポーズ呼び出し時: rest 法線を最小回転で posed 接線空間へ輸送し、
        # 外積法線の **符号のみ** を揃える (§3)。
        #
        # 注意: ここで ms[i] をレスト法線で完全に置換してはならない。
        # 置換すると法線がポーズ後のネット配置から再計算されず、
        # Eq.(1) の「法線ねじり」項が失われ、変形勾配が接線回転のみに
        # 退化する (= プロファイル変形が出なくなる)。
        # 必要なのは外積 t_i × t_{i+1} が持つ ± の曖昧性の解消だけである。
        if (reference_corner_frames is not None
                and rest_tangents_at_isect is not None
                and isect_idx < len(rest_tangents_at_isect)):
            rt = rest_tangents_at_isect[isect_idx]
            if len(rt) == N_at:
                for i in range(N_at):
                    ci_i, side_i = sorted_members[i][0], sorted_members[i][1]
                    ref_key = (ci_i, side_i)
                    if ref_key not in reference_corner_frames:
                        continue
                    rest_mi = reference_corner_frames[ref_key]['n_plus']
                    # rest → posed の輸送は接線 **ペア** の回転で行う。
                    # 片方の接線だけの最小回転では、曲げ角が大きいとき
                    # 参照法線が真の posed 法線から曲げ角ぶんずれ、90°
                    # 付近で dot が 0 を跨いで法線が反転してしまう。
                    rt_i = rt[i]
                    pt_i = sorted_tangs[i]
                    R_pair = _tangent_pair_rotation(
                        rt_i, rt[(i + 1) % N_at],
                        pt_i, sorted_tangs[(i + 1) % N_at])
                    if R_pair is not None:
                        rotated_mi = R_pair @ rest_mi
                    else:
                        # 縮退 (平行接線 / T ジャンクション) のみ
                        # 単一接線の最小回転にフォールバックする。
                        rot_axis = np.cross(rt_i, pt_i)
                        sin_a = float(np.linalg.norm(rot_axis))
                        cos_a = float(np.clip(np.dot(rt_i, pt_i), -1., 1.))
                        if sin_a > 1e-10:
                            rotated_mi = _rodrigues(
                                rest_mi, rot_axis / sin_a,
                                float(np.arctan2(sin_a, cos_a)))
                        elif cos_a < 0:
                            perp = _perp_to(rt_i, surf_n_fb)
                            rotated_mi = _rodrigues(rest_mi, perp, np.pi)
                        else:
                            rotated_mi = rest_mi.copy()
                    # 符号合わせのみ (向き・大きさは posed の外積を維持)
                    if float(np.dot(ms[i], rotated_mi)) < 0.0:
                        ms[i] = -ms[i]

        # 法線割り当て: n_i^+ = m_i,  n_i^- = m_{i-1}
        # 幅公式 (§3):
        #   w_i^+ = l_i + ||c_i|| * (l_{i+1} - l_i)
        #   w_i^- = l_i + ||c_{i-1}|| * (l_{i-1} - l_i)
        for i in range(N_at):
            ci, side = sorted_members[i][0], sorted_members[i][1]
            n_plus = ms[i]
            n_minus = ms[(i - 1) % N_at]

            li = sorted_lens[i]
            li1 = sorted_lens[(i + 1) % N_at]
            li_prev = sorted_lens[(i - 1) % N_at]

            ci_vec = np.cross(sorted_tangs[i], sorted_tangs[(i + 1) % N_at])
            ci_len = float(np.linalg.norm(ci_vec))
            ci_prev = np.cross(sorted_tangs[(i - 1) % N_at], sorted_tangs[i])
            ci_prev_len = float(np.linalg.norm(ci_prev))

            w_plus = li + ci_len * (li1 - li)
            w_minus = li + ci_prev_len * (li_prev - li)

            # 論文 §3 準拠: 幅はポーズごとに再計算する。
            # 以前はここでレスト幅による上書きを行っていたが、それでは
            # w_posed / w_rest ≡ 1 となり Eq.(1) の非一様スケーリング項が
            # 消滅する (= カーブ側ごとのプロファイル変形が出ない)。
            # 「F の行列式が爆発する」現象はカーブのグループ化ミスに起因
            # する 2 価の縮退交点が原因であり、そちらで解消済み。

            result[(ci, side)] = {
                'n_plus': n_plus,
                'n_minus': n_minus,
                'w_plus': max(w_plus, 1e-6),
                'w_minus': max(w_minus, 1e-6),
            }

    return result, sorted_orders, tangents_at_isect


# ======================================================================
# 4. フルフレーム計算 (平行移動 + トーション + 幅)
# ======================================================================

def _parallel_transport(tangs: np.ndarray,
                        n0: np.ndarray,
                        alphas: np.ndarray | None = None,
                        torsion_target: np.ndarray | None = None,
                        reference_theta: float | None = None,
                        ) -> tuple[np.ndarray, float]:
    """接線場に沿って法線 *n0* を平行移動する。オプションでトーション補正を行う。

    Parameters
    ----------
    tangs : np.ndarray
        単位接線ベクトル (M, 3)。
    n0 : np.ndarray
        初期法線 (3,)。
    alphas : np.ndarray | None
        弧長パラメータ [0, 1] (M,)。トーション補正用。
    torsion_target : np.ndarray | None
        終端のトーションターゲット法線 (3,)。
    reference_theta : float | None
        rest-pose で計算されたトーション補正角。指定された場合、
        atan の ±π/2 分岐点を跨がないよう位相接続する。

    Returns
    -------
    tuple[np.ndarray, float]
        (サンプルごとの法線 (M, 3), トーション補正角 theta)。
        トーション補正が無い場合 theta = 0.0。
    """
    M = tangs.shape[0]
    normals = np.empty((M, 3))
    n_curr = _perp_to(tangs[0], n0)
    normals[0] = n_curr
    for i in range(M - 1):
        t0, t1 = tangs[i], tangs[i + 1]
        axis = np.cross(t0, t1)
        sin_a = float(np.linalg.norm(axis))
        cos_a = float(np.clip(np.dot(t0, t1), -1., 1.))
        if sin_a < 1e-10:
            normals[i + 1] = normals[i]
        else:
            normals[i + 1] = _rodrigues(
                normals[i], axis / sin_a, float(np.arctan2(sin_a, cos_a)))
    # トーション補正 (§3)
    # θ = PT 終端法線と torsion_target 間の角度。
    # reference_theta がある場合は、その位相を中心に角度を unwrap する。
    # これにより ±π のブランチカットでも連続になり、旧実装の
    # |theta_rest| > 0.75π という不連続な切替閾値も不要になる。
    theta = 0.0
    if torsion_target is not None and alphas is not None:
        n_tgt = _perp_to(tangs[-1], torsion_target)
        n_tgt_len = float(np.linalg.norm(n_tgt))
        if n_tgt_len > 1e-10:
            Omega_n1 = normals[-1]
            cross_v = np.cross(n_tgt, tangs[-1])
            if reference_theta is not None:
                # Omega_n1 を reference_theta ぶん「戻して」から残差角を測る。
                # (n_tgt, n_tgt×t, t) は左手系なので、t 回りに +reference_theta
                # 回すことが位相を -reference_theta ずらすことに対応する。
                # 符号を誤ると同一入力でも theta が π ずれ、法線が反転する。
                Omega_shifted = _rodrigues(
                    Omega_n1, tangs[-1], reference_theta)
                y = float(np.dot(Omega_shifted, cross_v))
                x = float(np.dot(Omega_shifted, n_tgt))
                delta = float(np.arctan2(y, x))
                theta = reference_theta + delta
            else:
                y = float(np.dot(Omega_n1, cross_v))
                x = float(np.dot(Omega_n1, n_tgt))
                theta = float(np.arctan2(y, x))
            for i in range(M):
                normals[i] = _rodrigues(normals[i], tangs[i],
                                        float(alphas[i]) * theta)
    return normals, theta


def compute_all_frames(curve_data_list: list[dict | None],
                       isect_info: dict,
                       corner_frames: dict,
                       surface_normal_fn=None,
                       reference_frames: list[dict | None] | None = None,
                       ) -> list[dict | None]:
    """全カーブのサンプルごと・片側ごとのフレームを計算する (§3)。

    Parameters
    ----------
    curve_data_list : list[dict | None]
        sample_curves / sample_curves_from_maya の出力。
    isect_info : dict
        detect_intersections() の出力。
    corner_frames : dict
        compute_corner_frames() の出力。
    surface_normal_fn : callable | None
        (pos_3d) -> (3,) サーフェス法線 (アンカー端点用)。
    reference_frames : list[dict | None] | None
        rest-pose の compute_all_frames 出力。ポーズ計算時に指定すると、
        各カーブのトーション補正角 (theta_plus/theta_minus) を参照して
        arctan2 の分岐点を跨がないよう位相接続 (unwrap) する。

    Returns
    -------
    list[dict | None]
        curve_data_list と並列の dict (None はスキップ)::

            {
                'positions':    (M, 3)
                'tangents':     (M, 3)
                'n_plus':       (M, 3)
                'n_minus':      (M, 3)
                'seg_lengths':  (M-1,)
                'sample_len':   (M,)   サンプルごとの代表長
                'w_plus':       (M,)   左側幅
                'w_minus':      (M,)   右側幅
                'h_plus':       (M,)   左側高さ = sqrt(l*w)
                'h_minus':      (M,)   右側高さ
            }
    """
    ep_type  = isect_info['ep_type']
    ep_isect = isect_info['ep_isect']
    K = len(curve_data_list)

    def _fallback_normal(tang):
        return _perp_to(tang, np.array([0., 1., 0.]))

    def _surface_normal(pos, tang):
        if surface_normal_fn is not None:
            try:
                n = np.asarray(surface_normal_fn(pos))
                n = _perp_to(tang, n)
                if float(np.linalg.norm(n)) > 1e-10:
                    return n
            except Exception:
                pass
        return _fallback_normal(tang)

    results = []
    for ci in range(K):
        cd = curve_data_list[ci]
        if cd is None:
            results.append(None)
            continue

        pts = cd['positions']
        tangs = cd['tangents']
        seg_lens = cd['seg_lengths']
        M = len(pts)

        # 弧長パラメータ
        sl = np.concatenate([[0.0], np.cumsum(seg_lens)])
        total = float(sl[-1])
        alphas = sl / total if total > 1e-10 else np.zeros(M)

        # サンプルごとの代表長 (隣接セグメントの平均)
        sample_len = np.empty(M)
        sample_len[0] = seg_lens[0] if len(seg_lens) > 0 else 1e-3
        sample_len[-1] = seg_lens[-1] if len(seg_lens) > 0 else 1e-3
        for j in range(1, M - 1):
            sample_len[j] = 0.5 * (seg_lens[j - 1] + seg_lens[j])

        # 交差点またはサーフェスから開始法線を決定
        key0 = (ci, 0)
        key1 = (ci, 1)
        has_isect0 = key0 in corner_frames
        has_isect1 = key1 in corner_frames

        # 開始法線
        if has_isect0:
            n0_plus = corner_frames[key0]['n_plus'].copy()
            n0_minus = corner_frames[key0]['n_minus'].copy()
        else:
            n0 = _surface_normal(pts[0], tangs[0])
            n0_plus = n0_minus = n0

        # 孤立カーブ (始端が交点でない) の開始法線 (§3 末尾):
        # 「静止タンジェントからの最小回転を使い」— レスト法線をレスト接線
        # → ポーズ接線の最小回転で輸送したものをそのまま採用する。
        #
        # 従来はサーフェス法線フォールバックの値を残し符号チェックのみ
        # 行っていたが、その場合 rest と posed で法線が独立に決まるため
        # (例: 常に perp(t, worldY))、接線の回転と無関係な捩れが F に
        # 混入する。最小回転を採用することで rest/posed が整合する。
        if (not has_isect0
                and reference_frames is not None
                and ci < len(reference_frames)
                and reference_frames[ci] is not None):
            ref = reference_frames[ci]
            ref_n0p = ref['n_plus'][0]
            ref_n0m = ref['n_minus'][0]
            ref_t0 = ref['tangents'][0]
            rot_axis = np.cross(ref_t0, tangs[0])
            sin_a = float(np.linalg.norm(rot_axis))
            cos_a = float(np.clip(np.dot(ref_t0, tangs[0]), -1., 1.))
            if sin_a > 1e-10:
                rot_n0p = _rodrigues(ref_n0p, rot_axis / sin_a,
                                     float(np.arctan2(sin_a, cos_a)))
                rot_n0m = _rodrigues(ref_n0m, rot_axis / sin_a,
                                     float(np.arctan2(sin_a, cos_a)))
            elif cos_a < 0:
                perp = _perp_to(ref_t0, np.array([0., 1., 0.]))
                rot_n0p = _rodrigues(ref_n0p, perp, np.pi)
                rot_n0m = _rodrigues(ref_n0m, perp, np.pi)
            else:
                rot_n0p = ref_n0p
                rot_n0m = ref_n0m
            # 最小回転した rest 法線をそのまま開始法線に採用する (§3)
            n0_plus = _perp_to(tangs[0], rot_n0p)
            n0_minus = _perp_to(tangs[0], rot_n0m)

        # トーションターゲット (カーブ終端)
        tgt_plus = tgt_minus = None
        if has_isect1:
            tgt_plus = corner_frames[key1]['n_plus'].copy()
            tgt_minus = corner_frames[key1]['n_minus'].copy()

        # arctan2 + reference_theta π-unwrap:
        # rest theta を参照し、n_k 符号フリップ (±π オフセット) を除去。
        # arctan2 は x=0 (θ=±π/2) を連続的に通過するため、89° 曲げでも安全。
        ref_theta_plus = None
        ref_theta_minus = None
        if (reference_frames is not None and ci < len(reference_frames)
                and reference_frames[ci] is not None):
            ref = reference_frames[ci]
            ref_theta_plus = ref.get('theta_plus')
            ref_theta_minus = ref.get('theta_minus')

        n_plus, theta_plus = _parallel_transport(
            tangs, n0_plus, alphas, tgt_plus, ref_theta_plus)
        n_minus, theta_minus = _parallel_transport(
            tangs, n0_minus, alphas, tgt_minus, ref_theta_minus)

        # 幅計算 (§3)
        w_plus = np.full(M, sample_len[0])
        w_minus = np.full(M, sample_len[0])
        if has_isect0:
            cf0 = corner_frames[key0]
            w_plus[0] = max(cf0['w_plus'], 1e-6)
            w_minus[0] = max(cf0['w_minus'], 1e-6)

        if has_isect1:
            cf1 = corner_frames[key1]
            w_plus[-1] = max(cf1['w_plus'], 1e-6)
            w_minus[-1] = max(cf1['w_minus'], 1e-6)

        if has_isect0 and has_isect1:
            # 弧長で補間
            for j in range(1, M - 1):
                a = float(alphas[j])
                w_plus[j] = (1.0 - a) * w_plus[0] + a * w_plus[-1]
                w_minus[j] = (1.0 - a) * w_minus[0] + a * w_minus[-1]
        elif has_isect0:
            # 交差点側から一様
            w_plus[:] = w_plus[0]
            w_minus[:] = w_minus[0]
        elif has_isect1:
            w_plus[:] = w_plus[-1]
            w_minus[:] = w_minus[-1]
        else:
            # 孤立カーブ — 幅 = サンプル長 (一様スケーリング)
            w_plus[:] = sample_len
            w_minus[:] = sample_len

        # 高さ = 幾何平均 sqrt(l * w)
        h_plus = np.sqrt(np.maximum(sample_len * w_plus, 1e-12))
        h_minus = np.sqrt(np.maximum(sample_len * w_minus, 1e-12))

        results.append({
            'positions':   pts,
            'tangents':    tangs,
            'n_plus':      n_plus,
            'n_minus':     n_minus,
            'seg_lengths': seg_lens,
            'sample_len':  sample_len,
            'w_plus':      w_plus,
            'w_minus':     w_minus,
            'h_plus':      h_plus,
            'h_minus':     h_minus,
            'theta_plus':  theta_plus,
            'theta_minus': theta_minus,
        })
    return results


# ======================================================================
# 5. 変形勾配   F = (B S)(B̆ S̆)^{-1}
# ======================================================================

def _scaled_frame(tang, normal, length, width, height):
    """スケールドフレーム B*S = [t*l, b*w, n*h] (3×3 列メジャー) を構築する。

    Parameters
    ----------
    tang : np.ndarray
        単位接線 (3,)。
    normal : np.ndarray
        単位法線 (3,)。
    length : float
        接線方向のスケール。
    width : float
        従法線方向のスケール。
    height : float
        法線方向のスケール。
    Returns
    -------
    np.ndarray
        3×3 スケールドフレーム行列。
    """
    binorm = np.cross(normal, tang)
    bn = float(np.linalg.norm(binorm))
    if bn > 1e-12:
        binorm /= bn
    return np.column_stack([
        tang * length,
        binorm * width,
        normal * height,
    ])


def compute_deformation_gradients(rest_frames: list[dict | None],
                                  posed_frames: list[dict | None],
                                  **kwargs,
                                  ) -> list[dict | None]:
    """全カーブのサンプルごと・片側ごとの F を計算する (§3 Eq 1)。

    論文準拠: SVD クランプなし、比クランプなし。

    Parameters
    ----------
    rest_frames : list[dict | None]
        レストポーズフレーム。
    posed_frames : list[dict | None]
        ポーズフレーム。

    Returns
    -------
    list[dict | None]
        フレームリストと並列の dict::

            {
                'F_plus':  (M, 3, 3)
                'F_minus': (M, 3, 3)
            }
    """
    K = len(rest_frames)
    results = []
    for ci in range(K):
        rf = rest_frames[ci]
        pf = posed_frames[ci]
        if rf is None or pf is None:
            results.append(None)
            continue
        M = len(rf['positions'])
        F_plus = np.empty((M, 3, 3))
        F_minus = np.empty((M, 3, 3))
        for j in range(M):
            for side, n_key, w_key, h_key, F_out in [
                ('+', 'n_plus', 'w_plus', 'h_plus', F_plus),
                ('-', 'n_minus', 'w_minus', 'h_minus', F_minus),
            ]:
                l_rest = rf['sample_len'][j]
                w_rest = rf[w_key][j]
                h_rest = rf[h_key][j]

                l_posed = pf['sample_len'][j]
                w_posed = pf[w_key][j]
                h_posed = pf[h_key][j]

                BS_rest = _scaled_frame(
                    rf['tangents'][j], rf[n_key][j], l_rest, w_rest, h_rest)
                BS_posed = _scaled_frame(
                    pf['tangents'][j], pf[n_key][j],
                    l_posed, w_posed, h_posed)
                det = float(np.linalg.det(BS_rest))
                if abs(det) > 1e-12:
                    diff = float(np.linalg.norm(BS_posed - BS_rest))
                    scale = max(float(np.linalg.norm(BS_rest)), 1e-12)
                    if diff / scale < 1e-10:
                        F_out[j] = np.eye(3)
                    else:
                        F_out[j] = BS_posed @ np.linalg.inv(BS_rest)
                else:
                    F_out[j] = np.eye(3)
        results.append({'F_plus': F_plus, 'F_minus': F_minus})
    return results


# ======================================================================
# 6. ポアソンソルバー用制約組み立て
# ======================================================================

def assemble_gradient_constraints(
    deformation_grads: list[dict | None],
    curve_data_list: list[dict | None],
    isect_info: dict,
) -> dict:
    """サンプルごとの変形勾配から制約行列 f_c を構築する。

    論文 §4.3 の「内部サンプル = 隣接セグメントの平均」は、フレームを
    セグメント単位ではなくサンプル単位で計算することで満たしている
    (compute_all_frames の tangents は中央差分 = 前後セグメントの平均、
    sample_len は隣接セグメント長の平均)。したがってここでは各サンプルの
    F_plus / F_minus をそのまま 1 本ずつ列として並べればよい。

    論文 §4.3 の「端点サンプルは入射セグメントごとにコピーを作る」は、
    交差点で溶接された各カーブが自分の (curve_idx, sample_idx, side) を
    持ったまま別々の列として出てくることで満たしている。どの列を
    どのコーナーに割り当てるかは poisson_solve._resolve_corner_constraint
    がハーフエッジのセグメント注釈から決める。

    Parameters
    ----------
    deformation_grads : list[dict | None]
        compute_deformation_gradients() の出力。
    curve_data_list : list[dict | None]
        サンプルデータ。
    isect_info : dict
        detect_intersections() の出力。

    Returns
    -------
    dict
        以下のキーを持つ::

            'positions':  (N_c, 3)    サンプルワールド位置
            'F':          (N_c, 3, 3) 制約ごとの変形勾配
            'curve_idx':  (N_c,) int  カーブインデックス
            'sample_idx': (N_c,) int  カーブ内サンプルインデックス
            'side':       (N_c,) int  0=plus, 1=minus
    """
    pos_list, F_list = [], []
    ci_list, si_list, side_list = [], [], []

    for ci, dg in enumerate(deformation_grads):
        if dg is None:
            continue
        cd = curve_data_list[ci]
        if cd is None:
            continue
        M = len(cd['positions'])
        for j in range(M):
            for s_idx, F_key in enumerate(['F_plus', 'F_minus']):
                pos_list.append(cd['positions'][j])
                F_list.append(dg[F_key][j])
                ci_list.append(ci)
                si_list.append(j)
                side_list.append(s_idx)

    return {
        'positions':  np.array(pos_list),
        'F':          np.array(F_list),
        'curve_idx':  np.array(ci_list, dtype=int),
        'sample_idx': np.array(si_list, dtype=int),
        'side':       np.array(side_list, dtype=int),
    }


def assemble_position_constraints(
    posed_frames: list[dict | None],
    rest_frames: list[dict | None],
    rest_projected: list[np.ndarray | None],
    gradient_constraints: dict,
) -> np.ndarray:
    """調整済みサンプル位置を計算: p_i = q_i - F_i*(q̃_i - p̃_i)。

    Parameters
    ----------
    posed_frames : list[dict | None]
        ポーズフレームデータ (positions = q_i)。
    rest_frames : list[dict | None]
        レストフレームデータ (positions = q̃_i)。
    rest_projected : list[np.ndarray | None]
        カーブごとの (M, 3) メッシュ投影位置 (p̃_i)。
        None のカーブでは投影オフセットはゼロ。
    gradient_constraints : dict
        assemble_gradient_constraints() の出力。

    Returns
    -------
    np.ndarray
        調整済み制約位置 x_c (N_c, 3)。
    """
    gc = gradient_constraints
    N_c = len(gc['positions'])
    x_c = np.empty((N_c, 3))
    for k in range(N_c):
        ci = gc['curve_idx'][k]
        si = gc['sample_idx'][k]
        F_k = gc['F'][k]
        q_posed = posed_frames[ci]['positions'][si]
        q_rest = rest_frames[ci]['positions'][si]
        if rest_projected is not None and rest_projected[ci] is not None:
            p_rest = rest_projected[ci][si]
        else:
            p_rest = q_rest
        x_c[k] = q_posed - F_k @ (q_rest - p_rest)
    return x_c


# ======================================================================
# 便利関数: フルパイプライン
# ======================================================================

def build_rest_and_posed(rest_curve_data: list[dict | None],
                         posed_curve_data: list[dict | None],
                         surface_normal_fn=None,
                         tol: float = 1e-3,
                         **kwargs,
                         ):
    """§3 のフルパイプラインをレストとポーズのカーブデータで実行する。

    Parameters
    ----------
    rest_curve_data : list[dict | None]
        レストポーズのサンプリング済みカーブデータ。
    posed_curve_data : list[dict | None]
        ポーズのサンプリング済みカーブデータ。
    surface_normal_fn : callable | None
        (pos_3d) -> (3,) サーフェス法線。
    tol : float
        交差検出の距離閾値。

    Returns
    -------
    tuple
        (rest_frames, posed_frames, deformation_grads, isect_info)。
    """
    isect_info = detect_intersections(rest_curve_data, tol=tol)
    corner_fr, rest_sorted_orders, rest_tangs_at_isect = compute_corner_frames(
        isect_info['intersections'],
        rest_curve_data,
        surface_normal_fn)

    rest_frames = compute_all_frames(rest_curve_data, isect_info,
                                     corner_fr, surface_normal_fn)

    # ポーズ: レストの交差トポロジーを再利用し、ポーズ位置で計算
    posed_isect = detect_intersections(posed_curve_data, tol=tol)
    posed_corner, _, _ = compute_corner_frames(
        posed_isect['intersections'],
        posed_curve_data,
        surface_normal_fn,
        reference_corner_frames=corner_fr,
        rest_sorted_orders=rest_sorted_orders,
        rest_tangents_at_isect=rest_tangs_at_isect)
    posed_frames = compute_all_frames(posed_curve_data, posed_isect,
                                      posed_corner, surface_normal_fn,
                                      reference_frames=rest_frames)

    dg = compute_deformation_gradients(rest_frames, posed_frames)
    return rest_frames, posed_frames, dg, isect_info
