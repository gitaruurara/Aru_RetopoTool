"""
poisson_solve.py  —  Full cut-mesh Laplacian & two-stage Poisson solve (§4)
============================================================================
Implements §4 of:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)

Includes:
  §4.1  Cut-mesh construction (polygon subdivision, half-edge data structure)
  §4.2  Polygon Laplacian (de Goes et al. 2020, Eq.7–10), V/C matrices
  §4.3  Two-stage mesh optimisation (Eq.4 → Eq.5)

All core math is numpy + scipy.  No Maya dependency.
"""

from __future__ import annotations

import json
import heapq
import math
from dataclasses import dataclass, field
from typing import Optional

from Aru_RetopoTool.editor.logger import get_logger

_log = get_logger("PoissonSolve")

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import KDTree


# ======================================================================
# ハーフエッジデータ構造 (§4.1)
# ======================================================================

# カット頂点タイプ (ビットマスク)
CVTYPE_MESH    = 0   # 元メッシュ頂点
CVTYPE_SAMPLE  = 1   # カーブネットサンプル (メッシュ上に投影済み)
CVTYPE_EDGE_X  = 2   # カーブネットセグメント × メッシュエッジ交差点

# §4.1: カーブネットサンプルが「メッシュ頂点の上」「メッシュエッジの上」に
# 乗っているかを判定する許容誤差。論文はサーフェス境界ボックス対角線長の
# 0.001% と明記しているのでその値を既定にする。
# メッシュ頂点は float32 を経由するため対角線比で ~1e-7 の量子化ノイズが
# 乗るが、この許容誤差はその 100 倍あるので取りこぼさない。
CUT_TOL_FACTOR = 1e-5

# ----------------------------------------------------------------------
# 幾何判定の許容誤差とヒューリスティック定数
# ----------------------------------------------------------------------
# ここに集めた値はいずれも **分岐条件** に使われる。値が変わるとカットメッシュ
# のトポロジー自体が変わりうるため、C++ へ移植する際は同じ値・同じ比較演算子・
# 同じ演算順序を保つこと (double 固定。float に落とすと分岐が変わる)。
# 相対値 (bbox 対角比) のものはモデルスケールに依存しないので、
# 絶対値へ置き換えないこと。

# _ray_edge_intersect: レイ長の下限と、エッジパラメータの許容はみ出し量。
# 端点ちょうどを通るセグメントを取りこぼさないよう ±1% の余裕を持たせる。
RAY_T_MIN = 1e-6
RAY_S_MARGIN = 0.01

# _merge_degenerate_cuts: 同一視するカット点の距離 (リング bbox 対角比)。
MERGE_CUT_TOL_FACTOR = 1e-4

# _resolve_cut_crossings: カット同士の交差とみなすパラメータ範囲の内側マージン。
CROSS_PARAM_EPS = 1e-6
# 交差解決の最大反復回数。
CROSS_MAX_ITER = 8

# _build_cv_warp_matrix (§5): 重心座標のフォールバック判定距離 (bbox 対角比)
# と、その絶対下限。
WARP_BARY_TOL_FACTOR = 1e-6
WARP_BARY_TOL_MIN = 1e-9
# ワープがプロジェクションポーズを再現できているかの検収閾値 (bbox 対角比)。
# 超えた場合はプロジェクション対レストを無効化して従来動作へ落とす。
WARP_ACCEPT_TOL_FACTOR = 1e-4

# _trace_segment_across_faces: 測地線トレースの最大ステップ数と、
# 終点から離れすぎた (展開が破綻した) と判定する弦長倍率。
# §3 の適応サンプリングにより 1 セグメント長 ~ 平均エッジ長なので、
# 通常は数ステップで到達する。
TRACE_MAX_STEPS = 100
TRACE_DIVERGE_CHORD_FACTOR = 2.0

# _factorize_solver: カーブネット拘束を持たない連結成分の対角に足す量
# (行列の対角最大値に対する比)。ラプラシアン項に対して十分小さく、かつ
# 倍精度の丸めに埋もれない大きさ。ここが効くのはゼロ空間だけなので、
# 拘束のある領域の解には影響しない。
SINGULAR_SHIFT_FACTOR = 1e-8


@dataclass
class CutVertex:
    """カットメッシュ上の頂点。"""
    idx: int                     # カットメッシュ頂点プール内のグローバルインデックス
    pos: np.ndarray              # (3,) 3D 座標
    vtype: int = CVTYPE_MESH     # ビットマスク
    mesh_vidx: int = -1          # 元メッシュ頂点インデックス (MESH の場合)
    curve_idx: int = -1          # カーブネットカーブインデックス (SAMPLE の場合)
    sample_idx: int = -1         # カーブ内サンプルインデックス (SAMPLE の場合)
    # §4.2: EDGE_X (カーブ × メッシュエッジ交差点) がセグメント
    # [sample_idx, sample_idx + 1] 上のどこに乗るかを表すパラメータ。
    # この頂点は未知数ではなく、両端サンプルの線形補間による拘束となる。
    seg_t: float = -1.0
    he_ring: list = field(default_factory=list)


@dataclass
class HalfEdge:
    """カットメッシュ上の有向ハーフエッジ。"""
    idx: int
    origin: int                   # CutVertex インデックス (始点)
    twin: int = -1
    next: int = -1
    prev: int = -1
    face: int = -1
    seg_ann: tuple | None = None


@dataclass
class CutFace:
    """カットメッシュ上のポリゴン (クラックを含む場合あり)。"""
    idx: int
    he_start: int
    parent_face: int = -1


# ======================================================================
# §4.1  カットメッシュ構築
# ======================================================================

def _project_sample(pos, verts, face, tol_vtx, tol_edge):
    """*pos* をポリゴン *face* に投影する。

    Parameters
    ----------
    pos : np.ndarray
        投影する 3D 座標 (3,)。
    verts : np.ndarray
        メッシュ頂点配列 (N, 3)。
    face : array-like
        ポリゴンの頂点インデックス列。
    tol_vtx : float
        頂点近傍判定の許容距離。
    tol_edge : float
        エッジ近傍判定の許容距離。

    Returns
    -------
    tuple
        (投影点, ヒット種別, 情報)。ヒット種別は ``'vertex'`` / ``'edge'`` / ``'face'``。
    """
    n_f = len(face)
    pts_f = verts[face]

    # 頂点近傍チェック
    for li in range(n_f):
        if float(np.linalg.norm(pos - pts_f[li])) < tol_vtx:
            return pts_f[li].copy(), 'vertex', face[li]

    # エッジチェック
    for li in range(n_f):
        a, b = pts_f[li], pts_f[(li + 1) % n_f]
        ab = b - a
        ab_len2 = float(np.dot(ab, ab))
        if ab_len2 < 1e-20:
            continue
        t = float(np.dot(pos - a, ab)) / ab_len2
        t = max(0.0, min(1.0, t))
        proj = a + t * ab
        if float(np.linalg.norm(pos - proj)) < tol_edge and 0.0 < t < 1.0:
            return proj.copy(), 'edge', (li, t)

    # 面内部 (§4.1): ポリゴンを三角形に分割し、各三角形への最近傍点を探索。
    # 非平面ポリゴン (クォッドメッシュ等) でも正確な投影を保証する。
    if n_f >= 3:
        best_proj = None
        best_dist = float('inf')
        for ti in range(1, n_f - 1):
            a, b, c = pts_f[0], pts_f[ti], pts_f[ti + 1]
            tri_n = np.cross(b - a, c - a)
            tri_n_len = float(np.linalg.norm(tri_n))
            if tri_n_len < 1e-14:
                continue
            tri_n = tri_n / tri_n_len
            proj = pos - np.dot(pos - a, tri_n) * tri_n
            v0, v1, v2 = b - a, c - a, proj - a
            d00 = float(np.dot(v0, v0))
            d01 = float(np.dot(v0, v1))
            d11 = float(np.dot(v1, v1))
            d20 = float(np.dot(v2, v0))
            d21 = float(np.dot(v2, v1))
            denom = d00 * d11 - d01 * d01
            if abs(denom) < 1e-14:
                continue
            bv = (d11 * d20 - d01 * d21) / denom
            bw = (d00 * d21 - d01 * d20) / denom
            bu = 1.0 - bv - bw
            bu = max(0.0, bu); bv = max(0.0, bv); bw = max(0.0, bw)
            s = bu + bv + bw
            if s < 1e-14:
                continue
            bu /= s; bv /= s; bw /= s
            clamped = bu * a + bv * b + bw * c
            d = float(np.linalg.norm(pos - clamped))
            if d < best_dist:
                best_dist = d
                best_proj = clamped
        if best_proj is not None:
            return best_proj.copy(), 'face', None
    return pos.copy(), 'face', None


def _edge_key(va, vb):
    """正規化された (min, max) エッジキーを返す。

    Parameters
    ----------
    va, vb : int
        エッジの両端頂点インデックス。
    """
    return (va, vb) if va < vb else (vb, va)


def _point_triangle_distance(pos, a, b, c):
    """重心座標投影による *pos* から三角形 (a, b, c) への距離。

    最内ループなのでスカラー演算で実装している (numpy の 3 要素配列演算は
    呼び出しオーバーヘッドが大きい)。演算順序は numpy 版と一致させてあり、
    結果はビット単位で同じになる。C++ へもそのまま移植できる。

    Parameters
    ----------
    pos : np.ndarray
        クエリ点 (3,)。
    a, b, c : np.ndarray
        三角形の頂点座標 (各 (3,))。

    Returns
    -------
    float
        投影距離。退化三角形の場合は ``inf``。
    """
    ax = a[0]; ay = a[1]; az = a[2]
    bx = b[0]; by = b[1]; bz = b[2]
    cx = c[0]; cy = c[1]; cz = c[2]
    v0x = bx - ax; v0y = by - ay; v0z = bz - az
    v1x = cx - ax; v1y = cy - ay; v1z = cz - az
    v2x = pos[0] - ax; v2y = pos[1] - ay; v2z = pos[2] - az

    d00 = v0x * v0x + v0y * v0y + v0z * v0z
    d01 = v0x * v1x + v0y * v1y + v0z * v1z
    d11 = v1x * v1x + v1y * v1y + v1z * v1z
    d20 = v2x * v0x + v2y * v0y + v2z * v0z
    d21 = v2x * v1x + v2y * v1y + v2z * v1z
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-14:
        return float('inf')
    bv = (d11 * d20 - d01 * d21) / denom
    bw = (d00 * d21 - d01 * d20) / denom
    bu = 1.0 - bv - bw
    # NaN の扱いを numpy 版 (max(0., x)) と揃えるため max をそのまま使う
    bu, bv, bw = max(0., bu), max(0., bv), max(0., bw)
    s = bu + bv + bw
    if s < 1e-12:
        return float('inf')
    bu /= s; bv /= s; bw /= s
    # numpy は (bu*a + bv*b) + bw*c の順に加算するので同じ順序で畳む
    dx = pos[0] - (bu * ax + bv * bx + bw * cx)
    dy = pos[1] - (bu * ay + bv * by + bw * cy)
    dz = pos[2] - (bu * az + bv * bz + bw * cz)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _ray_edge_intersect(p0, direction, ea, eb, face_normal=None):
    """レイ (p0 + t*direction) とエッジ (ea → eb) の交差判定 (§4.1)。

    *face_normal* が指定された場合、フェイスのタンジェント平面に投影し
    正確な 2D 交差を計算する (Polthier & Schmies 1998)。

    Parameters
    ----------
    p0 : np.ndarray
        レイの原点 (3,)。
    direction : np.ndarray
        レイの方向ベクトル (3,)。
    ea, eb : np.ndarray
        エッジの両端座標 (各 (3,))。
    face_normal : np.ndarray | None
        フェイス法線 (3,)。指定時に 2D 投影で正確な交差を計算する。

    Returns
    -------
    tuple[float, float] | None
        (t_ray, s_edge)。交差しない場合は None。
        s_edge は [0.01, 0.99] にクランプされる。
    """
    if face_normal is not None:
        # §4.1: タンジェント平面上での正確な 2D 交差 (Cramer の公式)
        t_ax, b_ax = _make_tangent_frame(face_normal)
        p0_2d = np.array([float(np.dot(p0, t_ax)),
                          float(np.dot(p0, b_ax))])
        d_2d = np.array([float(np.dot(direction, t_ax)),
                         float(np.dot(direction, b_ax))])
        ea_2d = np.array([float(np.dot(ea, t_ax)),
                          float(np.dot(ea, b_ax))])
        eb_2d = np.array([float(np.dot(eb, t_ax)),
                          float(np.dot(eb, b_ax))])
        seg = eb_2d - ea_2d
        # det([d_2d | -seg])
        det = -d_2d[0] * seg[1] + seg[0] * d_2d[1]
        if abs(det) < 1e-14:
            return None
        rhs = ea_2d - p0_2d
        t_ray = float((-rhs[0] * seg[1] + rhs[1] * seg[0]) / det)
        s_edge = float((d_2d[0] * rhs[1] - d_2d[1] * rhs[0]) / det)
    else:
        # フォールバック: 3D 最小二乗
        A = np.column_stack([direction, -(eb - ea)])
        try:
            result, _, _, _ = np.linalg.lstsq(A, ea - p0, rcond=None)
            t_ray, s_edge = float(result[0]), float(result[1])
        except Exception:
            return None
    if t_ray < RAY_T_MIN or s_edge < -RAY_S_MARGIN or s_edge > 1.0 + RAY_S_MARGIN:
        return None
    return t_ray, max(0.01, min(0.99, s_edge))


def _nearest_edge_on_face(pos, pts_f, n_f):
    """ポリゴンの最近接エッジを探す。

    Parameters
    ----------
    pos : np.ndarray
        クエリ点 (3,)。
    pts_f : np.ndarray
        ポリゴン頂点座標配列 (n_f, 3)。
    n_f : int
        ポリゴンの頂点数。

    Returns
    -------
    tuple[int, float]
        (best_li, best_t) — エッジローカルインデックスとパラメトリック位置。
    """
    best_dist, best_li, best_t = float('inf'), 0, 0.5
    for li in range(n_f):
        ea, eb = pts_f[li], pts_f[(li + 1) % n_f]
        ab = eb - ea
        ab2 = float(np.dot(ab, ab))
        if ab2 < 1e-20:
            continue
        t_val = max(0.05, min(0.95, float(np.dot(pos - ea, ab)) / ab2))
        d = float(np.linalg.norm(pos - (ea + t_val * ab)))
        if d < best_dist:
            best_dist, best_li, best_t = d, li, t_val
    return best_li, best_t


def _face_centroid_radii(verts, faces):
    """面重心と、重心から面頂点までの最大距離 (外接半径) を返す。

    :func:`_find_closest_face` の枝刈りに使う。面上の任意の点は面頂点の
    凸結合なので、点 q から面までの距離には ``|q - 重心| - 半径`` という
    下界が成り立つ。この下界で候補を切っても最近接面は変わらない。

    Parameters
    ----------
    verts : np.ndarray
        メッシュ頂点 (N, 3)。
    faces : list[list[int]]
        フェイス頂点インデックス。

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (重心 (F, 3), 外接半径 (F,))。
    """
    if not len(faces):
        return np.zeros((0, 3)), np.zeros(0)
    cent = np.array([verts[f].mean(axis=0) for f in faces])
    radii = np.array([
        float(np.linalg.norm(verts[f] - cent[fi], axis=1).max())
        for fi, f in enumerate(faces)
    ])
    return cent, radii


# 最近接面探索で一度に取得する候補数。下界による打ち切りが効かない場合だけ
# 倍々に広げる。全面走査と同じ結果を返しつつ距離計算の回数を大幅に減らす。
_CLOSEST_FACE_BATCH = 64


def _find_closest_face(pos, verts, faces, face_tree, k=None, face_radii=None):
    """*pos* に最も近い面インデックスを返す。

    Parameters
    ----------
    pos : np.ndarray
        クエリ点 (3,)。
    verts : np.ndarray
        メッシュ頂点配列 (N, 3)。
    faces : list[list[int]]
        フェイス頂点インデックスのリスト。
    face_tree : scipy.spatial.KDTree
        面重心の KDTree。
    k : int | None
        候補として取得する最近傍面数。None は厳密な最近接面を返す。
        面重心の固定 k 近傍だけでは細長いポリゴンを取りこぼすため、
        正確性が必要なバインド処理では None を使う。
    face_radii : np.ndarray | None
        面ごとの外接半径 (:func:`_face_centroid_radii`)。*k* が None の
        ときに下界による枝刈りへ使う。**結果は全面走査と一致する**
        (走査順も重心距離の昇順で同じなので同着の解決も変わらない)。
        None の場合は従来どおり全面を走査する。

    Returns
    -------
    int
        最近接面インデックス。
    """
    n_faces = len(faces)
    if n_faces == 0:
        return 0

    def _scan(cand, best_fi, best_d):
        for fi in cand:
            fi = int(fi)
            face = faces[fi]
            pts_f = verts[face]
            n_f = len(face)
            if n_f < 3:
                continue
            for ti in range(1, n_f - 1):
                d_val = _point_triangle_distance(
                    pos, pts_f[0], pts_f[ti], pts_f[ti + 1])
                if d_val < best_d:
                    best_d = d_val
                    best_fi = fi
        return best_fi, best_d

    if k is not None or face_radii is None or not len(face_radii):
        # 従来経路: 固定 k 近傍、または半径が無いので全面を走査する
        candidate_count = n_faces if k is None else min(k, n_faces)
        _, idxs = face_tree.query(pos, k=candidate_count)
        idxs = np.atleast_1d(idxs)
        return _scan(idxs, int(idxs[0]), float('inf'))[0]

    # 重心距離の昇順に候補を広げ、下界 (重心距離 - 最大半径) が現在の最良
    # 距離を上回った時点で打ち切る。それ以降の面は最良を更新し得ない。
    r_max = float(np.max(face_radii))
    slack = 1e-9 * max(r_max, 1.0)      # 下界の丸め誤差ぶんだけ余裕を持たせる
    first_fi, best_fi, best_d, scanned = None, -1, float('inf'), 0
    kk = min(_CLOSEST_FACE_BATCH, n_faces)
    while True:
        dists, idxs = face_tree.query(pos, k=kk)
        idxs = np.atleast_1d(idxs)
        dists = np.atleast_1d(dists)
        if first_fi is None:
            first_fi = int(idxs[0])
        best_fi, best_d = _scan(idxs[scanned:], best_fi, best_d)
        scanned = kk
        if kk >= n_faces:
            break
        if float(dists[-1]) - r_max > best_d + slack:
            break
        kk = min(kk * 2, n_faces)
    return best_fi if best_fi >= 0 else first_fi


# ------------------------------------------------------------------
# _build_cutmesh サブルーチン
# ------------------------------------------------------------------

def _project_samples_onto_mesh(cv_list, curve_samples, rest_verts, faces,
                                face_tree, tol_vtx, tol_edge,
                                face_radii=None):
    """カーブネットサンプルをメッシュに投影し、カット頂点を生成する。

    *cv_list* を直接変更する (新規 CutVertex を追加)。

    Parameters
    ----------
    cv_list : list[CutVertex]
        カット頂点プール (新規頂点が末尾に追加される)。
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ (``'positions'`` キーを含む)。
    rest_verts : np.ndarray
        レストメッシュ頂点 (N, 3)。
    faces : list[list[int]]
        フェイス頂点インデックス。
    face_tree : scipy.spatial.KDTree
        面重心の KDTree。
    tol_vtx : float
        頂点近傍許容距離。
    tol_edge : float
        エッジ近傍許容距離。
    face_radii : np.ndarray | None
        面の外接半径 (:func:`_face_centroid_radii`)。最近接面探索の
        枝刈りに使う。結果は指定の有無で変わらない。

    Returns
    -------
    sample_to_cv : dict[tuple[int, int], int]
        (curve_idx, sample_idx) → CutVertex インデックス。
    face_samples : dict[int, list]
        面内部に落ちたサンプルの CutVertex idx リスト。
    edge_subdivisions : dict[tuple[int, int], list]
        エッジキー → [(cv_idx, t_param), ...] 分割情報。

    Notes
    -----
    複数のスプラインが共有するアンカー (論文 §3 の *intersection*) は、
    カーブごとに独立に投影すると別々の面へ落ちて異なるカット頂点になり、
    分岐点でカットが途切れてしまう。途切れるとカーブが閉ループを成さず、
    ``VᵀL_hV`` がブロック対角に分離しないため、カーブの反対側まで変形が
    漏れる。そこで各カーブの端点サンプルは投影前の座標で照合し、同じ
    アンカーなら同一のカット頂点を共有させる。
    """
    next_cv = len(cv_list)
    sample_to_cv: dict[tuple[int, int], int] = {}
    face_samples: dict[int, list] = {fi: [] for fi in range(len(faces))}
    edge_subdivisions: dict[tuple[int, int], list] = {}
    # 分岐点の溶接用: (投影前サンプル座標, cut vertex idx)
    anchor_cvs: list = []

    for ci, cd in enumerate(curve_samples):
        if cd is None:
            continue
        n_s = len(cd['positions'])
        for si in range(n_s):
            qpos = np.asarray(cd['positions'][si], dtype=float)
            is_anchor = (si == 0 or si == n_s - 1)

            if is_anchor:
                shared = None
                for apos, acv in anchor_cvs:
                    if np.linalg.norm(apos - qpos) <= tol_vtx:
                        shared = acv
                        break
                if shared is not None:
                    sample_to_cv[(ci, si)] = shared
                    continue

            fi = _find_closest_face(qpos, rest_verts, faces, face_tree,
                                    face_radii=face_radii)
            face = faces[fi]
            proj, htype, info = _project_sample(
                qpos, rest_verts, face, tol_vtx, tol_edge)

            if htype == 'vertex':
                mesh_vi = info
                sample_to_cv[(ci, si)] = mesh_vi
                cv_list[mesh_vi].vtype |= CVTYPE_SAMPLE
                cv_list[mesh_vi].curve_idx = ci
                cv_list[mesh_vi].sample_idx = si
            elif htype == 'edge':
                li, t = info
                va, vb = face[li], face[(li + 1) % len(face)]
                cv = CutVertex(idx=next_cv, pos=proj,
                               vtype=CVTYPE_SAMPLE | CVTYPE_EDGE_X,
                               curve_idx=ci, sample_idx=si)
                cv_list.append(cv)
                sample_to_cv[(ci, si)] = next_cv
                t_actual = t if va < vb else (1.0 - t)
                edge_subdivisions.setdefault(
                    _edge_key(va, vb), []).append((next_cv, t_actual))
                next_cv += 1
            else:
                cv = CutVertex(idx=next_cv, pos=proj,
                               vtype=CVTYPE_SAMPLE,
                               curve_idx=ci, sample_idx=si)
                cv_list.append(cv)
                sample_to_cv[(ci, si)] = next_cv
                face_samples[fi].append(next_cv)
                next_cv += 1

            if is_anchor:
                anchor_cvs.append((qpos, sample_to_cv[(ci, si)]))

    return sample_to_cv, face_samples, edge_subdivisions


def _snap_interior_to_edges(face_samples, faces, rest_verts, cv_list,
                             edge_subdivisions):
    """面内部サンプルを最近接エッジにスナップする。

    各内部サンプルに対してエッジ上にアンカー CutVertex を生成する。

    Parameters
    ----------
    face_samples : dict[int, list]
        面インデックス → 内部サンプル cv_idx リスト。
    faces : list[list[int]]
        元メッシュのフェイスリスト。
    rest_verts : np.ndarray
        レスト頂点 (N, 3)。
    cv_list : list[CutVertex]
        カット頂点プール (新規アンカーが追加される)。
    edge_subdivisions : dict[tuple[int, int], list]
        エッジ分割情報 (新規分割が追加される)。

    Returns
    -------
    list[tuple[int, int, int]]
        interior_links: (face_idx, anchor_cv_idx, sample_cv_idx) のリスト。
    """
    next_cv = len(cv_list)
    interior_links: list[tuple[int, int, int]] = []
    for fi, fs_list in face_samples.items():
        if not fs_list:
            continue
        face = faces[fi]
        n_f = len(face)
        pts_f = rest_verts[face]
        for cv_idx in fs_list:
            best_li, best_t = _nearest_edge_on_face(
                cv_list[cv_idx].pos, pts_f, n_f)
            va = face[best_li]
            vb = face[(best_li + 1) % n_f]
            anchor_pos = rest_verts[va] * (1.0 - best_t) + rest_verts[vb] * best_t
            anchor_cv = CutVertex(idx=next_cv, pos=anchor_pos,
                                  vtype=CVTYPE_EDGE_X)
            cv_list.append(anchor_cv)
            t_actual = best_t if va < vb else (1.0 - best_t)
            edge_subdivisions.setdefault(
                _edge_key(va, vb), []).append((next_cv, t_actual))
            interior_links.append((fi, next_cv, cv_idx))
            next_cv += 1
    return interior_links


def _expand_face_rings(faces, edge_subdivisions):
    """エッジを分割し、元のフェイスリングを拡張する。

    Parameters
    ----------
    faces : list[list[int]]
        元メッシュのフェイスリスト。
    edge_subdivisions : dict[tuple[int, int], list]
        エッジキー → [(cv_idx, t_param), ...] 分割情報。

    Returns
    -------
    new_faces : list[list[int]]
        拡張後のフェイスリング。
    face_parent : list[int]
        各新フェイスの元フェイスインデックス。
    edge_new_verts : dict[tuple[int, int], list[int]]
        エッジキー → 挿入された新規頂点 idx リスト。
    """
    edge_new_verts: dict[tuple[int, int], list[int]] = {}
    for ekey, subs in edge_subdivisions.items():
        subs.sort(key=lambda x: x[1])
        edge_new_verts[ekey] = [s[0] for s in subs]

    def _expand_edge(va, vb):
        ekey = _edge_key(va, vb)
        if ekey not in edge_new_verts:
            return [va, vb]
        mids = edge_new_verts[ekey]
        if va > vb:
            return [va] + list(reversed(mids)) + [vb]
        return [va] + mids + [vb]

    new_faces: list[list[int]] = []
    face_parent: list[int] = []
    for fi, face in enumerate(faces):
        ring = []
        for li in range(len(face)):
            expanded = _expand_edge(face[li], face[(li + 1) % len(face)])
            ring.extend(expanded[:-1])
        new_faces.append(ring)
        face_parent.append(fi)
    return new_faces, face_parent, edge_new_verts


def _build_edge_adjacency(new_faces):
    """拡張フェイスリングからエッジ → フェイスの隣接マップを構築する。

    Parameters
    ----------
    new_faces : list[list[int]]
        拡張後のフェイスリング。

    Returns
    -------
    dict[tuple[int, int], list[int]]
        エッジキー → 隣接フェイスインデックスリスト。
    """
    edge_to_face: dict[tuple[int, int], list[int]] = {}
    for nfi, nface in enumerate(new_faces):
        nfn = len(nface)
        for li in range(nfn):
            ek = _edge_key(nface[li], nface[(li + 1) % nfn])
            edge_to_face.setdefault(ek, []).append(nfi)
    return edge_to_face


def _trace_all_cuts(curve_samples, sample_to_cv, face_samples,
                    cv_list, new_faces, edge_to_face, edge_new_verts):
    """カーブネットセグメントをカットエッジとしてトレースする (§4.1)。

    論文 §4.1: フェイスサンプルは孤立カット頂点として保持し、
    カーブネットセグメントによって直接接続する。

    Parameters
    ----------
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ。
    sample_to_cv : dict[tuple[int, int], int]
        (curve_idx, sample_idx) → CutVertex idx。
    face_samples : dict[int, list]
        面インデックス → 内部サンプル cv_idx リスト。
    cv_list : list[CutVertex]
        カット頂点プール。
    new_faces : list[list[int]]
        拡張後のフェイスリング (インプレース変更あり)。
    edge_to_face : dict[tuple[int, int], list[int]]
        エッジ → 隣接フェイスマップ。
    edge_new_verts : dict[tuple[int, int], list[int]]
        エッジ上に挿入された頂点マップ。

    Returns
    -------
    face_cut_edges : dict[int, list[tuple[int, int]]]
        フェイス → カットエッジ (cv_a, cv_b) リスト。
    segment_edges : dict[tuple[int, int], tuple[int, int]]
        (cv_a, cv_b) → (curve_idx, sample_start_idx)。
        ハーフエッジ注釈 (§4.1) に使用する。
    """
    face_cut_edges: dict[int, list[tuple[int, int]]] = {}
    segment_edges: dict[tuple[int, int], tuple[int, int]] = {}

    # §4.1: フェイスサンプルの逆引きマップ (cv_idx → face_idx)
    cv_to_face: dict[int, int] = {}
    for fi, fs_list in face_samples.items():
        for cv_idx in fs_list:
            cv_to_face[cv_idx] = fi

    for ci, cd in enumerate(curve_samples):
        if cd is None:
            continue
        M = len(cd['positions'])
        for si in range(M - 1):
            cv_a = sample_to_cv.get((ci, si))
            cv_b = sample_to_cv.get((ci, si + 1))
            if cv_a is None or cv_b is None:
                continue
            # 共有フェイスを探す (リング内 + face_samples)
            faces_a = {nfi for nfi, nf in enumerate(new_faces)
                       if cv_a in nf}
            faces_b = {nfi for nfi, nf in enumerate(new_faces)
                       if cv_b in nf}
            if cv_a in cv_to_face:
                faces_a.add(cv_to_face[cv_a])
            if cv_b in cv_to_face:
                faces_b.add(cv_to_face[cv_b])
            shared = faces_a & faces_b
            if shared:
                for nfi in shared:
                    face_cut_edges.setdefault(nfi, []).append(
                        (cv_a, cv_b))
                    segment_edges[(cv_a, cv_b)] = (ci, si)
            else:
                _trace_segment_across_faces(
                    cv_a, cv_b, cv_list, new_faces, edge_to_face,
                    face_cut_edges, edge_new_verts,
                    segment_edges, ci, si,
                    cv_to_face=cv_to_face)
    return face_cut_edges, segment_edges


def _remove_islands(face_cut_edges, face_samples, cv_list,
                    sample_to_cv, new_faces, segment_edges):
    """§4.1: フェイス内部のカーブネットアイランドを検出・削除する。

    同一メッシュフェイス内のフェイスサンプルのみからなる接続成分を
    検出し、関連する全要素を削除する。これらはサーフェスメッシュの
    解像度より細かいディテールレベルを表すためである。
    """
    from collections import deque

    # フェイスサンプル集合
    face_sample_set: set[int] = set()
    for fi, fs_list in face_samples.items():
        face_sample_set.update(fs_list)
    if not face_sample_set:
        return

    # リング (境界) に含まれる頂点集合
    boundary_set: set[int] = set()
    for nf in new_faces:
        boundary_set.update(nf)

    # 境界に含まれない純粋なフェイスサンプル
    pure_face_samples = face_sample_set - boundary_set
    if not pure_face_samples:
        return

    # カットエッジからグラフを構築
    adj: dict[int, set[int]] = {}
    for fi, cuts in face_cut_edges.items():
        for (a, b) in cuts:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)

    # BFS で接続成分を検出
    visited: set[int] = set()
    islands_to_remove: list[set[int]] = []
    for start in pure_face_samples:
        if start in visited:
            continue
        component: set[int] = set()
        queue = deque([start])
        is_island = True
        while queue:
            v = queue.popleft()
            if v in component:
                continue
            component.add(v)
            visited.add(v)
            if v not in pure_face_samples:
                is_island = False
            for nb in adj.get(v, set()):
                if nb not in component:
                    queue.append(nb)
        if is_island and component:
            islands_to_remove.append(component)

    if not islands_to_remove:
        return

    _log.info("Removing %d curve-net islands (§4.1)", len(islands_to_remove))
    for island in islands_to_remove:
        # face_cut_edges から削除
        for fi in list(face_cut_edges.keys()):
            face_cut_edges[fi] = [
                (a, b) for (a, b) in face_cut_edges[fi]
                if a not in island and b not in island
            ]
            if not face_cut_edges[fi]:
                del face_cut_edges[fi]
        # segment_edges から削除
        for key in list(segment_edges.keys()):
            if key[0] in island or key[1] in island:
                del segment_edges[key]
        # sample_to_cv から削除
        for key in list(sample_to_cv.keys()):
            if sample_to_cv[key] in island:
                del sample_to_cv[key]


def _merge_degenerate_cuts(ring, cuts, cv_list,
                           tol_factor=MERGE_CUT_TOL_FACTOR):
    """縮退した (長さ 0 の) カットエッジの端点を統合する (§4.1)。

    トレース結果が既存のカット頂点と重なると長さ 0 のカットエッジが
    でき、タンジェント空間の角度ソートが定義できなくなってループ走査が
    破綻する。破綻した面はカーブの両側を短絡させるため、重なった端点は
    1 つに統合しておく。

    Parameters
    ----------
    ring : list[int]
        フェイス境界リング。
    cuts : list[tuple[int, int]]
        カットエッジ。
    cv_list : list[CutVertex]
        カット頂点プール。
    tol_factor : float
        フェイス対角長に対する統合許容距離の比。

    Returns
    -------
    tuple[list[int], list[tuple[int, int]]]
        統合後の (ring, cuts)。
    """
    if not cuts:
        return list(ring), list(cuts)

    pts = np.array([cv_list[v].pos for v in ring])
    eps = max(float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
              * tol_factor, 1e-9)
    ring_set = set(ring)
    remap: dict[int, int] = {}

    def _root(v):
        while v in remap:
            v = remap[v]
        return v

    changed = True
    while changed:
        changed = False
        for a, b in cuts:
            ra, rb = _root(a), _root(b)
            if ra == rb:
                continue
            if np.linalg.norm(cv_list[ra].pos - cv_list[rb].pos) > eps:
                continue
            # 境界リング上の頂点を優先して残す
            if rb in ring_set and ra not in ring_set:
                remap[ra] = rb
            else:
                remap[rb] = ra
            changed = True

    if not remap:
        return list(ring), list(cuts)

    new_ring: list[int] = []
    for v in ring:
        r = _root(v)
        if not new_ring or new_ring[-1] != r:
            new_ring.append(r)
    if len(new_ring) > 1 and new_ring[0] == new_ring[-1]:
        new_ring.pop()

    new_cuts: list[tuple[int, int]] = []
    seen: set = set()
    for a, b in cuts:
        ra, rb = _root(a), _root(b)
        if ra == rb:
            continue
        key = _edge_key(ra, rb)
        if key in seen:
            continue
        seen.add(key)
        new_cuts.append((ra, rb))

    if len(new_ring) < 3:
        return list(ring), list(cuts)
    return new_ring, new_cuts


def _resolve_cut_crossings(ring, cuts, cv_list, segment_edges=None,
                           max_iter=CROSS_MAX_ITER):
    """フェイス内で交差するカットエッジに交点頂点を挿入する (§4.1)。

    カットネットワークは平面グラフでなければならず、交差点には頂点が
    無いと ``_split_face_tangent_space`` のループ走査がサブポリゴンを
    分離できない。分離できない面はカーブの両側を短絡させてしまうため、
    測地線トレースの結果が面内で交差した場合は交点にカット頂点を挿入
    する。

    Parameters
    ----------
    ring : list[int]
        フェイス境界リング。
    cuts : list[tuple[int, int]]
        カットエッジ。
    cv_list : list[CutVertex]
        カット頂点プール (交点が追加される)。
    segment_edges : dict[tuple[int, int], tuple[int, int]] | None
        (cv_a, cv_b) → (curve_idx, sample_start_idx)。分割したエッジの
        注釈を引き継ぐために更新される。
    max_iter : int
        解決する交差の最大数。

    Returns
    -------
    list[tuple[int, int]]
        交差を解消したカットエッジ。
    """
    if len(cuts) < 2:
        return list(cuts)

    ring_pts = np.array([cv_list[v].pos for v in ring])
    t_ax, b_ax = _make_tangent_frame(
        _compute_face_normal_from_positions(ring_pts))
    origin = ring_pts.mean(axis=0)

    def _uv(idx):
        d = cv_list[idx].pos - origin
        return np.array([float(np.dot(d, t_ax)), float(np.dot(d, b_ax))])

    cuts = list(cuts)
    for _ in range(max_iter):
        hit = None
        for i in range(len(cuts)):
            for j in range(i + 1, len(cuts)):
                a, b = cuts[i]
                c, d = cuts[j]
                if len({a, b, c, d}) < 4:
                    continue
                pa, pb, pc, pd = _uv(a), _uv(b), _uv(c), _uv(d)
                r, s = pb - pa, pd - pc
                den = r[0] * s[1] - r[1] * s[0]
                if abs(den) < 1e-12:
                    continue
                q = pc - pa
                t = (q[0] * s[1] - q[1] * s[0]) / den
                u = (q[0] * r[1] - q[1] * r[0]) / den
                if not (CROSS_PARAM_EPS < t < 1.0 - CROSS_PARAM_EPS
                        and CROSS_PARAM_EPS < u < 1.0 - CROSS_PARAM_EPS):
                    continue
                hit = (i, j, t, u)
                break
            if hit is not None:
                break
        if hit is None:
            break

        i, j, t, u = hit
        a, b = cuts[i]
        c, d = cuts[j]
        pos = 0.5 * ((1.0 - t) * cv_list[a].pos + t * cv_list[b].pos
                     + (1.0 - u) * cv_list[c].pos + u * cv_list[d].pos)
        # 交点をカーブ上の補間拘束にするため、いずれかの端点の
        # (curve_idx, sample_idx, seg_t) を引き継ぐ。
        order = [b, a, d, c] if t > 0.5 else [a, b, c, d]
        src = None
        for k in order:
            if cv_list[k].curve_idx >= 0:
                src = cv_list[k]
                break
        if src is None:
            break

        x_idx = len(cv_list)
        cv_list.append(CutVertex(
            idx=x_idx, pos=pos, vtype=CVTYPE_EDGE_X,
            curve_idx=src.curve_idx, sample_idx=src.sample_idx,
            seg_t=src.seg_t if src.seg_t >= 0.0 else 0.0))

        if segment_edges is not None:
            for (p, q_) in ((a, b), (c, d)):
                ann = segment_edges.get((p, q_))
                rev = False
                if ann is None:
                    ann = segment_edges.get((q_, p))
                    rev = True
                if ann is None:
                    continue
                if rev:
                    segment_edges[(x_idx, p)] = ann
                    segment_edges[(q_, x_idx)] = ann
                else:
                    segment_edges[(p, x_idx)] = ann
                    segment_edges[(x_idx, q_)] = ann

        cuts = [e for k, e in enumerate(cuts) if k not in (i, j)]
        cuts += [(a, x_idx), (x_idx, b), (c, x_idx), (x_idx, d)]

    return cuts


def _split_and_finalize(new_faces, face_parent, face_cut_edges, cv_list,
                        rest_verts, faces, face_samples=None,
                        segment_edges=None):
    """カット線に沿って面を分割し、ハーフエッジを構築し、レスト変換を計算する。

    §4.1 のタンジェント空間投影 + CCW ソートアルゴリズムによって
    カットフェイスのサブポリゴンを特定する。

    Parameters
    ----------
    new_faces : list[list[int]]
        拡張後のフェイスリング。
    face_parent : list[int]
        各フェイスの元メッシュ面インデックス。
    face_cut_edges : dict[int, list[tuple[int, int]]]
        フェイス → カットエッジペア。
    cv_list : list[CutVertex]
        カット頂点プール。
    rest_verts : np.ndarray
        レストメッシュ頂点 (N, 3)。
    faces : list[list[int]]
        元メッシュのフェイスリスト。

    Returns
    -------
    tuple
        (final_faces, final_face_loops, final_parent, he_list, rest_Xf_list)。
    """
    # §4.1 — 各カット頂点のタンジェント空間法線を計算
    tangent_normals = _compute_vertex_tangent_normals(
        cv_list, new_faces, face_parent, rest_verts, faces,
        face_samples=face_samples)

    final_faces: list[list[int]] = []
    final_parent: list[int] = []
    final_face_loops: list[list[int]] = []

    for nfi, nface in enumerate(new_faces):
        cuts = face_cut_edges.get(nfi, [])
        if not cuts:
            final_faces.append(nface)
            final_parent.append(face_parent[nfi])
            final_face_loops.append(nface[:])
        else:
            nface, cuts = _merge_degenerate_cuts(nface, cuts, cv_list)
            cuts = _resolve_cut_crossings(nface, cuts, cv_list,
                                          segment_edges=segment_edges)
            face_cut_edges[nfi] = cuts
            for spl in _split_face_tangent_space(
                    nface, cuts, cv_list, tangent_normals):
                final_faces.append(spl)
                final_parent.append(face_parent[nfi])
                final_face_loops.append(spl[:])

    he_list, _ = _build_halfedge_structure(
        final_face_loops, cv_list, face_cut_edges,
        segment_edges=segment_edges)

    rest_Xf_list = [np.array([cv_list[v].pos for v in fl])
                    for fl in final_face_loops]

    return final_faces, final_face_loops, final_parent, he_list, rest_Xf_list


# ------------------------------------------------------------------

def _closest_bary_tri(x, a, b, c):
    """三角形 (a,b,c) 上で *x* に最も近い点の重心座標を返す。

    Ericson "Real-Time Collision Detection" の領域判定。重みは常に
    非負で和が 1 になるため、外挿による暴走が起きない。
    """
    ab = b - a
    ac = c - a
    ap = x - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return 1.0, 0.0, 0.0

    bp = x - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return 0.0, 1.0, 0.0

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        den = d1 - d3
        v = d1 / den if abs(den) > 1e-20 else 0.0
        return 1.0 - v, v, 0.0

    cp = x - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return 0.0, 0.0, 1.0

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        den = d2 - d6
        w = d2 / den if abs(den) > 1e-20 else 0.0
        return 1.0 - w, 0.0, w

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        den = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / den if abs(den) > 1e-20 else 0.0
        return 0.0, 1.0 - w, w

    den = va + vb + vc
    if abs(den) < 1e-20:
        return 1.0, 0.0, 0.0
    v = vb / den
    w = vc / den
    return 1.0 - v - w, v, w


def _face_barycentric(x, pts):
    """多角形 *pts* 上で *x* に最も近い点を表す重み (和 1、非負) を返す。

    三角形ファンに分割し、各三角形上の最近点を求めて最良のものを採る。
    エッジ交差点は自然に 2 頂点の線形補間になり、頂点上の点は単位ベクトルに
    なるので、平均値座標より数値的に安定で厳密。

    Returns
    -------
    tuple
        ``(重み (n,), 最近点までの距離)``。
    """
    n = len(pts)
    if n < 3:
        w = np.zeros(n)
        if n:
            w[0] = 1.0
        return w, float(np.linalg.norm(pts[0] - x)) if n else 0.0

    best_w = None
    best_d = None
    for k in range(1, n - 1):
        a, b, c = pts[0], pts[k], pts[k + 1]
        l0, l1, l2 = _closest_bary_tri(x, a, b, c)
        p = l0 * a + l1 * b + l2 * c
        d = float(np.linalg.norm(p - x))
        if best_d is None or d < best_d:
            w = np.zeros(n)
            w[0] += l0
            w[k] += l1
            w[k + 1] += l2
            best_w, best_d = w, d
            if d < 1e-12:
                break

    if best_w is None:
        w = np.zeros(n)
        w[0] = 1.0
        return w, float(np.linalg.norm(pts[0] - x))
    return best_w, best_d


def _build_cv_warp_matrix(cv_list, faces, face_loops, face_parent, verts):
    """カット頂点を元メッシュ頂点の線形結合として表す行列を作る。

    論文 §5「プロジェクション対レスト」より::

        カーブネットとカットメッシュはプロジェクションポーズで作成されるので、
        カッティングルーティンによって以前にキャッシュされたカーブネット
        サンプルのサーフェスメッシュの最近傍点への結合を再利用することで、
        レストサーフェスの形状に両者をワープする。

    ここで作る行列 ``W`` (n_cv, N) がその「結合」にあたる。
    カット頂点がサーフェスから僅かに浮いている場合に備え、残差を
    オフセット ``o`` として持つ::

        cv_pos = W @ verts + o

    こうしておくとプロジェクションポーズの再現が構成上つねに厳密になる。

    Returns
    -------
    tuple
        ``(W (n_cv, N) の疎行列, オフセット (n_cv, 3))``。
    """
    n_cv = len(cv_list)
    N = len(verts)

    # カット頂点 -> 親となる元メッシュフェイスの候補 (複数ありうる)
    cv_faces: dict = {}
    for fi, loop in enumerate(face_loops):
        pf = face_parent[fi] if fi < len(face_parent) else -1
        if pf < 0 or pf >= len(faces):
            continue
        for cvi in loop:
            s = cv_faces.get(cvi)
            if s is None:
                cv_faces[cvi] = {pf}
            else:
                s.add(pf)

    fcent = (np.array([verts[f].mean(axis=0) for f in faces])
             if faces else np.zeros((0, 3)))
    ftree = KDTree(fcent) if len(fcent) else None
    diag = float(np.linalg.norm(verts.max(axis=0) - verts.min(axis=0))) \
        if N else 1.0
    tol = max(diag * WARP_BARY_TOL_FACTOR, WARP_BARY_TOL_MIN)

    rows, cols, vals = [], [], []
    offset = np.zeros((n_cv, 3))
    n_bary = 0
    n_offset = 0
    max_off = 0.0
    for cvi, cv in enumerate(cv_list):
        mv = int(cv.mesh_vidx)
        if 0 <= mv < N:
            rows.append(cvi); cols.append(mv); vals.append(1.0)
            continue

        pos = np.asarray(cv.pos, dtype=float)

        def _search(cands, best=None):
            for pf in sorted(cands):
                ring = faces[pf]
                pts = verts[ring]
                w, d = _face_barycentric(pos, pts)
                if best is None or d < best[0]:
                    best = (d, ring, w)
                    if d < tol:
                        break
            return best

        # まず親フェイス情報を使う。足りなければ近傍フェイスも試す。
        best = _search(cv_faces.get(cvi, ()))
        if (best is None or best[0] > tol) and ftree is not None:
            k = min(24, len(fcent))
            _d, ii = ftree.query(pos, k=k)
            best = _search({int(j) for j in np.atleast_1d(ii)}, best)

        if best is None:
            # フェイスが 1 つも無い異常ケース。原点へ飛ばさないよう
            # 位置そのものをオフセットとして持つ。
            offset[cvi] = pos
            n_offset += 1
            continue

        d, ring, w = best
        for k, vi in enumerate(ring):
            if abs(w[k]) > 1e-14:
                rows.append(cvi); cols.append(int(vi)); vals.append(float(w[k]))
        if d > tol:
            offset[cvi] = pos - w @ verts[ring]
            n_offset += 1
            max_off = max(max_off, d)
        n_bary += 1

    W = sp.coo_matrix((vals, (rows, cols)), shape=(n_cv, N)).tocsr()
    _log.info("  warp matrix: %d vertex-bound, %d barycentric",
              n_cv - n_bary, n_bary)
    if n_offset:
        _log.info("  warp matrix: %d cut vertices carry an offset "
                  "(max %.3e = %.4f%% of bbox)",
                  n_offset, max_off, 100.0 * max_off / max(diag, 1e-12))
    return W, offset

def _build_cutmesh(rest_verts, faces, curve_samples, tol_factor=CUT_TOL_FACTOR):

    """カットメッシュを構築する (§4.1)。

    Parameters
    ----------
    rest_verts : np.ndarray
        レストメッシュ頂点 (N, 3)。
    faces : list[list[int]]
        フェイス頂点インデックス。
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ。
    tol_factor : float
        許容距離をバウンディングボックス対角線に対する比率で指定。
        既定は論文 §4.1 の 0.001% (``CUT_TOL_FACTOR``)。

    Returns
    -------
    tuple
        (cv_list, final_faces, face_loops, face_parent,
         he_list, sample_to_cv, rest_Xf_list)。
    """
    N = len(rest_verts)
    bbox = rest_verts.max(axis=0) - rest_verts.min(axis=0)
    diag = float(np.linalg.norm(bbox))
    # §4.1 は頂点判定とエッジ判定に同じ許容誤差を使う。エッジ側だけ緩めると
    # カーブから最大 2 倍離れた位置までカットがエッジに吸い寄せられ、
    # 実際のカーブ形状からずれた場所で切れてしまう。
    tol_vtx = diag * tol_factor
    tol_edge = diag * tol_factor

    cv_list: list[CutVertex] = [
        CutVertex(idx=vi, pos=rest_verts[vi].copy(),
                  vtype=CVTYPE_MESH, mesh_vidx=vi)
        for vi in range(N)
    ]
    face_centroids, face_radii = _face_centroid_radii(rest_verts, faces)
    face_tree = KDTree(face_centroids)

    sample_to_cv, face_samples, edge_subdivisions = \
        _project_samples_onto_mesh(
            cv_list, curve_samples, rest_verts, faces,
            face_tree, tol_vtx, tol_edge, face_radii=face_radii)

    # §4.1: フェイスサンプルは孤立カット頂点として保持 (スナップしない)

    new_faces, face_parent, edge_new_verts = _expand_face_rings(
        faces, edge_subdivisions)

    edge_to_face = _build_edge_adjacency(new_faces)

    face_cut_edges, segment_edges = _trace_all_cuts(
        curve_samples, sample_to_cv, face_samples,
        cv_list, new_faces, edge_to_face, edge_new_verts)

    # §4.1: メッシュ解像度より細かいカーブネットアイランドを検出・削除
    _remove_islands(face_cut_edges, face_samples, cv_list,
                    sample_to_cv, new_faces, segment_edges)

    (final_faces, final_face_loops, final_parent,
     he_list, rest_Xf_list) = _split_and_finalize(
        new_faces, face_parent, face_cut_edges, cv_list,
        rest_verts, faces, face_samples=face_samples,
        segment_edges=segment_edges)

    return (cv_list, final_faces, final_face_loops, final_parent,
            he_list, sample_to_cv, rest_Xf_list)


def _unfold_direction_across_edge(direction, edge_vec, normal_from, normal_to):
    """展開により方向ベクトルを隣接面の平面へ引き継ぐ (Polthier & Schmies 1998)。

    共有エッジを軸に隣接フェイスを展開し、最直線測地線の方向を計算する。
    方向のエッジ沿い成分は保存し、面内垂直成分を次フェイスの平面へ回転する。

    Parameters
    ----------
    direction : np.ndarray
        現在フェイスにおける方向ベクトル (3,)。
    edge_vec : np.ndarray
        共有エッジのベクトル (3,)。
    normal_from : np.ndarray
        出発フェイスの単位法線 (3,)。
    normal_to : np.ndarray
        到着フェイスの単位法線 (3,)。

    Returns
    -------
    np.ndarray
        到着フェイス平面における展開済み方向ベクトル (3,)。
    """
    e_len = float(np.linalg.norm(edge_vec))
    if e_len < 1e-12:
        return direction.copy()
    e = edge_vec / e_len

    # エッジ沿い成分は不変
    d_along = np.dot(direction, e) * e
    d_perp = direction - d_along

    # 各フェイスにおけるエッジ垂直方向 (面内)
    p1 = np.cross(e, normal_from)
    p1_len = float(np.linalg.norm(p1))
    p2 = np.cross(e, normal_to)
    p2_len = float(np.linalg.norm(p2))

    if p1_len < 1e-12 or p2_len < 1e-12:
        return direction.copy()
    p1 /= p1_len
    p2 /= p2_len

    coeff = float(np.dot(d_perp, p1))
    return d_along + coeff * p2


def _select_trace_face(current_cv, target_pos, direction, cv_list, faces,
                       visited_faces, cv_to_face):
    """トレースの次フェイスを進行方向に基づいて選ぶ (§4.1)。

    ``current_cv`` を含む未訪問フェイスが複数ある場合 (始点がメッシュ頂点の
    ときなど)、単純に最初の 1 つを選ぶと進行方向と無関係なフェイスへ入って
    しまい、以降の展開が明後日の方向へ逸走する。ここでは各候補フェイスの
    頂点まわりのくさび (wedge) に進行方向が入るかを調べ、最も収まりの良い
    フェイスを選ぶ。

    Parameters
    ----------
    current_cv : int
        現在のカット頂点。
    target_pos : np.ndarray
        セグメント終点の座標 (3,)。
    direction : np.ndarray | None
        展開済み進行方向。None の場合は ``target_pos`` への向きを使う。
    cv_list : list[CutVertex]
        カット頂点プール。
    faces : list[list[int]]
        フェイスリング。
    visited_faces : set[int]
        訪問済みフェイス。
    cv_to_face : dict[int, int]
        フェイス内部サンプル cv_idx → 面インデックス。

    Returns
    -------
    int
        選択したフェイスインデックス。候補なしの場合は -1。
    """
    cands = [fi for fi, f in enumerate(faces)
             if fi not in visited_faces
             and (current_cv in f or cv_to_face.get(current_cv) == fi)]
    if not cands:
        return -1
    if len(cands) == 1:
        return cands[0]

    p0 = cv_list[current_cv].pos
    best_fi, best_score = cands[0], -np.inf
    for fi in cands:
        f = faces[fi]
        if current_cv not in f:
            # 面内部サンプル: くさび判定はできないので中立スコア
            score = 0.0
        else:
            pts = np.array([cv_list[v].pos for v in f])
            normal = _compute_face_normal_from_positions(pts)
            d = direction if direction is not None else (target_pos - p0)
            d = d - np.dot(d, normal) * normal
            d_len = float(np.linalg.norm(d))
            if d_len < 1e-12:
                continue
            d = d / d_len
            li = f.index(current_cv)
            n_f = len(f)
            e_next = cv_list[f[(li + 1) % n_f]].pos - p0
            e_prev = cv_list[f[li - 1]].pos - p0
            e_next = e_next - np.dot(e_next, normal) * normal
            e_prev = e_prev - np.dot(e_prev, normal) * normal
            ln, lp = np.linalg.norm(e_next), np.linalg.norm(e_prev)
            if ln < 1e-12 or lp < 1e-12:
                continue
            e_next = e_next / ln
            e_prev = e_prev / lp
            # くさび [e_next, e_prev] に d が入るなら両方の符号付き面積が正
            c1 = float(np.dot(np.cross(e_next, d), normal))
            c2 = float(np.dot(np.cross(d, e_prev), normal))
            score = min(c1, c2)
        if score > best_score:
            best_score = score
            best_fi = fi
    return best_fi


def _rollback_trace(n_cv0, cv_list, faces, edge_to_face, edge_new_verts,
                    face_cut_edges, segment_edges):
    """失敗したトレースが作った要素をすべて取り消す (§4.1)。

    ``n_cv0`` はトレース開始時点の ``len(cv_list)``。このトレースが生成した
    カット頂点はすべて ``n_cv0`` 以上のインデックスを持つため、それらを参照
    する要素を機械的に取り除けば完全に巻き戻せる。中途半端なカット線を残すと
    レスト形状を再現できない拘束が生まれ、ソルブ全体が破綻する。
    """
    if len(cv_list) <= n_cv0:
        return
    for fi, ring in enumerate(faces):
        if any(v >= n_cv0 for v in ring):
            faces[fi] = [v for v in ring if v < n_cv0]
    for key in list(edge_to_face.keys()):
        if key[0] >= n_cv0 or key[1] >= n_cv0:
            del edge_to_face[key]
    for key in list(edge_new_verts.keys()):
        if key[0] >= n_cv0 or key[1] >= n_cv0:
            del edge_new_verts[key]
        else:
            kept = [v for v in edge_new_verts[key] if v < n_cv0]
            if kept:
                edge_new_verts[key] = kept
            else:
                del edge_new_verts[key]
    for fi in list(face_cut_edges.keys()):
        kept = [(a, b) for (a, b) in face_cut_edges[fi]
                if a < n_cv0 and b < n_cv0]
        if kept:
            face_cut_edges[fi] = kept
        else:
            del face_cut_edges[fi]
    for key in list(segment_edges.keys()):
        if key[0] >= n_cv0 or key[1] >= n_cv0:
            del segment_edges[key]
    del cv_list[n_cv0:]


def _fallback_exit_edge(current_cv, pos_b, face, cv_list, edge_to_face,
                        cur_face, visited_faces):
    """レイが出口エッジを捉えられなかったときの代替出口を返す (§4.1)。

    開始点がフェイス境界上または境界外にある場合、面内のどのエッジとも
    交差しないことがある。その場合は終点に最も近いエッジを出口として選び、
    トレースを前進させる。

    Parameters
    ----------
    current_cv : int
        現在のカット頂点インデックス。
    pos_b : np.ndarray
        トレース終点位置 (3,)。
    face : list[int]
        現フェイスの頂点リング。
    cv_list : list[CutVertex]
        カット頂点プール。
    edge_to_face : dict[tuple[int, int], list[int]]
        エッジ → 隣接フェイスマップ。
    cur_face : int
        現フェイスインデックス。
    visited_faces : set[int]
        訪問済みフェイス集合。

    Returns
    -------
    tuple[int, int, float]
        (エッジ始点, エッジ終点, エッジ上パラメータ)。見つからない場合は
        (-1, -1, 0.5)。
    """
    best = (-1, -1, 0.5)
    best_d = float('inf')
    n = len(face)
    for li in range(n):
        va, vb = face[li], face[(li + 1) % n]
        if va == current_cv or vb == current_cv:
            continue
        ekey = _edge_key(va, vb)
        adj = [fi for fi in edge_to_face.get(ekey, []) if fi != cur_face]
        if adj and all(fi in visited_faces for fi in adj):
            continue
        pa = cv_list[va].pos
        evec = cv_list[vb].pos - pa
        ee = float(np.dot(evec, evec))
        if ee < 1e-24:
            continue
        t = float(np.dot(pos_b - pa, evec) / ee)
        t = min(0.95, max(0.05, t))
        d = float(np.linalg.norm(pa + t * evec - pos_b))
        if d < best_d:
            best_d = d
            best = (va, vb, t)
    return best


def _cv_candidate_faces(cv_idx, faces, cv_to_face):
    """*cv_idx* が属するフェイスインデックスの集合を返す (§4.1)。

    Parameters
    ----------
    cv_idx : int
        カット頂点インデックス。
    faces : list[list[int]]
        フェイスリング。
    cv_to_face : dict[int, int]
        フェイス内部サンプル cv_idx → 面インデックス。

    Returns
    -------
    set[int]
        属するフェイスインデックスの集合。
    """
    out = set(fi for fi, f in enumerate(faces) if cv_idx in f)
    fi = cv_to_face.get(cv_idx)
    if fi is not None:
        out.add(fi)
    return out


def _point_segment_distance(q, a, b):
    """点 *q* と線分 *a*-*b* の距離を返す。

    Parameters
    ----------
    q, a, b : np.ndarray
        点および線分端点 (3,)。

    Returns
    -------
    float
        距離。
    """
    ab = b - a
    ee = float(np.dot(ab, ab))
    if ee < 1e-24:
        return float(np.linalg.norm(q - a))
    t = min(1.0, max(0.0, float(np.dot(q - a, ab) / ee)))
    return float(np.linalg.norm(a + t * ab - q))


def _segment_segment_distance(p1, p2, q1, q2):
    """2 つの線分間の最短距離を返す。

    Parameters
    ----------
    p1, p2 : np.ndarray
        線分 1 の端点 (3,)。
    q1, q2 : np.ndarray
        線分 2 の端点 (3,)。

    Returns
    -------
    float
        距離。
    """
    return min(_point_segment_distance(p1, q1, q2),
               _point_segment_distance(p2, q1, q2),
               _point_segment_distance(q1, p1, p2),
               _point_segment_distance(q2, p1, p2))


def _find_face_path(faces_a, faces_b, pos_a, pos_b, cv_list, faces,
                    edge_to_face, max_hops=4):
    """*faces_a* から *faces_b* への双対グラフ経路を探す (§4.1)。

    セグメントから離れた場所を通らないよう、通過する共有エッジ (portal) と
    線分 a-b の距離をコストとした最良優先探索を行う。隣接するフェイス同士が
    複数のエッジを共有する場合もあるため、portal はコストが最小のものを
    選ぶ。

    Parameters
    ----------
    faces_a, faces_b : set[int]
        始点側・終点側のフェイス集合。
    pos_a, pos_b : np.ndarray
        セグメント端点座標 (3,)。
    cv_list : list[CutVertex]
        カット頂点プール。
    faces : list[list[int]]
        フェイスリング。
    edge_to_face : dict[tuple[int, int], list[int]]
        エッジ → 隣接フェイスマップ。
    max_hops : int
        探索する最大ホップ数。

    Returns
    -------
    tuple[list[int], list[tuple[int, int]]] | None
        (フェイス列, 通過する共有エッジ列)。見つからない場合は None。
    """
    heap = [(0.0, fi, (fi,), ()) for fi in sorted(faces_a)]
    heapq.heapify(heap)
    best_cost = {fi: 0.0 for fi in faces_a}
    while heap:
        cost, fi, path, ekeys = heapq.heappop(heap)
        if fi in faces_b and len(path) > 1:
            return list(path), list(ekeys)
        if len(path) > max_hops:
            continue
        ring = faces[fi]
        n = len(ring)
        for li in range(n):
            ekey = _edge_key(ring[li], ring[(li + 1) % n])
            d = _segment_segment_distance(
                cv_list[ekey[0]].pos, cv_list[ekey[1]].pos, pos_a, pos_b)
            for fj in edge_to_face.get(ekey, []):
                if fj == fi or fj in path:
                    continue
                c = cost + d
                if c < best_cost.get(fj, float('inf')) - 1e-12:
                    best_cost[fj] = c
                    heapq.heappush(
                        heap, (c, fj, path + (fj,), ekeys + (ekey,)))
    return None


def _bridge_face_path(cv_a, cv_b, cv_list, faces, edge_to_face,
                      face_cut_edges, edge_new_verts, segment_edges,
                      ci, si, cv_to_face):
    """測地線トレース失敗時にフェイス列を辿ってカットを直結する (§4.1)。

    測地線トレースは非平面な四角形や大きなフェイスの上で展開が破綻し、
    メッシュ解像度より短いセグメントを追えないことがある。取りこぼすと
    カーブネットのループが閉じず、変形がメッシュ全体へ漏れてしまう。
    ここでは双対グラフ上の短い経路を求め、通過する各共有エッジ上に交差点を
    作ってカットをつなぐ。

    Parameters
    ----------
    cv_a, cv_b : int
        セグメント始点・終点のカット頂点インデックス。
    cv_list : list[CutVertex]
        カット頂点プール (新規交差頂点が追加される)。
    faces : list[list[int]]
        フェイスリング (インプレース変更あり)。
    edge_to_face : dict[tuple[int, int], list[int]]
        エッジ → 隣接フェイスマップ。
    face_cut_edges : dict[int, list[tuple[int, int]]]
        収集先: フェイス → カットエッジペア。
    edge_new_verts : dict[tuple[int, int], list[int]]
        エッジ上の新規頂点マップ。
    segment_edges : dict[tuple[int, int], tuple[int, int]]
        収集先: (cv_u, cv_v) → (curve_idx, sample_start_idx)。
    ci, si : int
        カーブインデックスとセグメント開始サンプルインデックス。
    cv_to_face : dict[int, int]
        フェイス内部サンプル cv_idx → 面インデックス。

    Returns
    -------
    bool
        橋渡しに成功したかどうか。
    """
    faces_a = _cv_candidate_faces(cv_a, faces, cv_to_face)
    faces_b = _cv_candidate_faces(cv_b, faces, cv_to_face)
    if not faces_a or not faces_b or (faces_a & faces_b):
        return False

    pos_a = cv_list[cv_a].pos
    pos_b = cv_list[cv_b].pos
    found = _find_face_path(faces_a, faces_b, pos_a, pos_b, cv_list, faces,
                            edge_to_face)
    if found is None:
        return False
    path, ekeys = found
    if len(ekeys) > 4:
        # 遠回りの経路で橋渡しすると、カットがセグメントから大きく外れた
        # 場所を通ってしまう。
        return False
    chord = pos_b - pos_a
    chord_len2 = float(np.dot(chord, chord))
    chord_len = math.sqrt(chord_len2)
    plan = []
    for ekey in ekeys:
        va, vb = ekey
        if cv_a in (va, vb) or cv_b in (va, vb):
            return False
        pa = cv_list[va].pos
        evec = cv_list[vb].pos - pa
        ee = float(np.dot(evec, evec))
        if ee < 1e-24:
            return False
        # 共有エッジ上で線分 a-b に最も近い点 (2 直線間の最近接パラメータ)
        t = 0.5
        if chord_len2 > 1e-24:
            r = pa - pos_a
            b_ = float(np.dot(evec, chord))
            d_ = float(np.dot(evec, r))
            e_ = float(np.dot(chord, r))
            denom = ee * chord_len2 - b_ * b_
            if abs(denom) > 1e-18:
                t = (b_ * e_ - chord_len2 * d_) / denom
        if not np.isfinite(t):
            t = 0.5
        t = min(0.95, max(0.05, t))
        q = pa + t * evec
        seg_t = 0.0
        if chord_len2 > 1e-24:
            seg_t = min(1.0, max(0.0,
                                 float(np.dot(q - pos_a, chord) / chord_len2)))
        # §4.2 の残差オフセットにより交差点が弦から外れてもレスト形状は
        # 再現されるが、セグメント長に対して極端に遠い点は変形を歪めるため
        # 見送る。
        if float(np.linalg.norm(q - (pos_a + seg_t * chord))) \
                > TRACE_DIVERGE_CHORD_FACTOR * chord_len:
            return False
        plan.append((ekey, va, vb, q, seg_t))

    new_ids = []
    for ekey, va, vb, q, seg_t in plan:
        new_cv = CutVertex(idx=len(cv_list), pos=q, vtype=CVTYPE_EDGE_X,
                           curve_idx=ci, sample_idx=si, seg_t=seg_t)
        cv_list.append(new_cv)
        new_idx = new_cv.idx
        new_ids.append(new_idx)
        edge_new_verts.setdefault(ekey, []).append(new_idx)
        for fi2 in edge_to_face.get(ekey, []):
            _insert_vertex_into_face_edge(faces[fi2], ekey, new_idx)
            edge_to_face.setdefault(_edge_key(va, new_idx), []).append(fi2)
            edge_to_face.setdefault(_edge_key(new_idx, vb), []).append(fi2)

    chain = [cv_a] + new_ids + [cv_b]
    for k, fi in enumerate(path):
        u, v = chain[k], chain[k + 1]
        if u == v:
            continue
        face_cut_edges.setdefault(fi, []).append((u, v))
        segment_edges[(u, v)] = (ci, si)
    return True


def _trace_segment_across_faces(cv_a, cv_b, cv_list, faces, edge_to_face,
                                face_cut_edges, edge_new_verts,
                                segment_edges, ci, si,
                                cv_to_face=None):
    """カーブネットセグメントを cv_a から cv_b まで面を跨いでトレースする (§4.1)。

    Polthier & Schmies [1998] の最直線測地線トレースを採用し、
    フェイス境界を越えるたびに隣接フェイスへ展開して方向を引き継ぐ。
    §4.1: フェイス内部サンプル (cv_to_face) にも対応する。

    Parameters
    ----------
    cv_a, cv_b : int
        トレースの始点・終点 CutVertex インデックス。
    cv_list : list[CutVertex]
        カット頂点プール (新規交差頂点が追加される)。
    faces : list[list[int]]
        拡張後フェイスリング (インプレース変更あり)。
    edge_to_face : dict[tuple[int, int], list[int]]
        エッジ → 隣接フェイスマップ。
    face_cut_edges : dict[int, list[tuple[int, int]]]
        収集先: フェイス → カットエッジペア。
    edge_new_verts : dict[tuple[int, int], list[int]]
        エッジ上の新規頂点マップ。
    segment_edges : dict[tuple[int, int], tuple[int, int]]
        収集先: (cv_a, cv_b) → (curve_idx, sample_start_idx)。
    ci : int
        カーブインデックス。
    si : int
        セグメント開始サンプルインデックス。
    cv_to_face : dict[int, int] | None
        フェイス内部サンプル cv_idx → 面インデックスのマップ。
    """
    if cv_to_face is None:
        cv_to_face = {}
    pos_b = cv_list[cv_b].pos
    chord_len = float(np.linalg.norm(pos_b - cv_list[cv_a].pos))
    n_cv0 = len(cv_list)
    current_cv = cv_a
    visited_faces = set()
    direction = None       # 面上方向ベクトル (展開で更新)
    prev_normal = None     # 直前フェイスの法線
    reached = False
    best_dist = float('inf')
    reason = "step limit"

    for _ in range(TRACE_MAX_STEPS):
        cur_face = _select_trace_face(current_cv, pos_b, direction, cv_list,
                                      faces, visited_faces, cv_to_face)
        if cur_face < 0:
            reason = "no unvisited face"
            break
        visited_faces.add(cur_face)
        face = faces[cur_face]

        # 現フェイスの法線を計算
        face_pts = np.array([cv_list[v].pos for v in face])
        face_normal = _compute_face_normal_from_positions(face_pts)

        # §4.1: cv_b がリング内またはフェイス内部サンプルの場合
        if cv_b in face or cv_to_face.get(cv_b) == cur_face:
            face_cut_edges.setdefault(cur_face, []).append(
                (current_cv, cv_b))
            segment_edges[(current_cv, cv_b)] = (ci, si)
            reached = True
            break

        p0 = cv_list[current_cv].pos

        if direction is None:
            # 初回: ターゲット方向をフェイス平面に射影
            raw = pos_b - p0
            direction = raw - np.dot(raw, face_normal) * face_normal
            d_len = float(np.linalg.norm(direction))
            if d_len < 1e-12:
                # 射影がゼロ → フォールバック (3D 方向)
                direction = raw.copy()
        elif prev_normal is not None:
            # 展開済み direction をさらに現フェイスに射影して数値誤差を除去
            direction = (direction
                         - np.dot(direction, face_normal) * face_normal)

        if float(np.linalg.norm(direction)) < 1e-12:
            reason = "degenerate direction"
            break

        # レイ–エッジ交差で最適な出口エッジを探索
        best_t_ray = float('inf')
        best_t_edge = 0.5
        best_va, best_vb = -1, -1
        for li in range(len(face)):
            va, vb = face[li], face[(li + 1) % len(face)]
            if va == current_cv or vb == current_cv:
                continue
            hit = _ray_edge_intersect(
                p0, direction, cv_list[va].pos, cv_list[vb].pos,
                face_normal)
            if hit is not None and hit[0] < best_t_ray:
                best_t_ray = hit[0]
                best_t_edge = hit[1]
                best_va, best_vb = va, vb

        if best_va < 0:
            # 開始点がフェイス境界上/外にある (前段のカットで生まれた頂点や
            # 投影誤差) と、レイがどのエッジとも交差せず進めなくなる。
            # 終点に最も近いエッジを出口として選び直して前進させる。
            best_va, best_vb, best_t_edge = _fallback_exit_edge(
                current_cv, pos_b, face, cv_list, edge_to_face,
                cur_face, visited_faces)
        if best_va < 0:
            reason = "no exit edge"
            break

        # 隣接フェイスの法線を取得 (頂点挿入前に行う)
        ekey = _edge_key(best_va, best_vb)
        adj_face_idx = -1
        for fi2 in edge_to_face.get(ekey, []):
            if fi2 != cur_face:
                adj_face_idx = fi2
                break

        adj_normal = None
        if adj_face_idx >= 0:
            adj_pts = np.array([cv_list[v].pos for v in faces[adj_face_idx]])
            adj_normal = _compute_face_normal_from_positions(adj_pts)

        # 出口エッジ上に新しいカット頂点を生成
        new_pos = ((1.0 - best_t_edge) * cv_list[best_va].pos
                   + best_t_edge * cv_list[best_vb].pos)

        # 逸走検知: 終点までの距離がこれまでの最短からセグメント長を大きく
        # 超えて悪化したら、展開が破綻して別方向へ進んでいる。トレースを
        # 打ち切り、生成物はまとめて巻き戻す。
        dist = float(np.linalg.norm(new_pos - pos_b))
        if dist > best_dist + TRACE_DIVERGE_CHORD_FACTOR * chord_len:
            reason = "diverging (%.3f > %.3f)" % (dist, best_dist)
            break
        best_dist = min(best_dist, dist)

        # §4.2: この頂点はカーブセグメント [si, si+1] の上に乗るため
        # 未知数ではなく両端サンプルの線形補間による拘束として扱う。
        # 弦への射影でセグメント内パラメータ t を求める。
        chord = pos_b - cv_list[cv_a].pos
        chord_len2 = float(np.dot(chord, chord))
        if chord_len2 > 1e-24:
            seg_t = float(np.dot(new_pos - cv_list[cv_a].pos, chord)
                          / chord_len2)
            seg_t = min(1.0, max(0.0, seg_t))
        else:
            seg_t = 0.0
        new_cv = CutVertex(idx=len(cv_list), pos=new_pos,
                           vtype=CVTYPE_EDGE_X,
                           curve_idx=ci, sample_idx=si, seg_t=seg_t)
        cv_list.append(new_cv)
        new_idx = new_cv.idx

        # 隣接構造を更新
        edge_new_verts.setdefault(ekey, []).append(new_idx)
        for fi2 in edge_to_face.get(ekey, []):
            _insert_vertex_into_face_edge(
                faces[fi2], ekey, new_idx)
            edge_to_face.setdefault(
                _edge_key(best_va, new_idx), []).append(fi2)
            edge_to_face.setdefault(
                _edge_key(new_idx, best_vb), []).append(fi2)

        face_cut_edges.setdefault(cur_face, []).append(
            (current_cv, new_idx))
        segment_edges[(current_cv, new_idx)] = (ci, si)

        # 展開: 方向ベクトルを隣接フェイスの平面へ回転 (Polthier & Schmies)
        if adj_normal is not None:
            edge_vec = cv_list[best_vb].pos - cv_list[best_va].pos
            direction = _unfold_direction_across_edge(
                direction, edge_vec, face_normal, adj_normal)

        prev_normal = face_normal
        current_cv = new_idx

    if not reached:
        # 途中で力尽きたトレースを残すと、到達できなかったサンプルを参照する
        # 中途半端なカット頂点が拘束行列に紛れ込み、レスト形状を再現できなく
        # なる (メッシュ全体が破綻する)。生成物をすべて巻き戻す。
        _rollback_trace(n_cv0, cv_list, faces, edge_to_face, edge_new_verts,
                        face_cut_edges, segment_edges)
        # 両端のフェイスが隣接しているだけの短いセグメントなら、共有エッジを
        # 1 点横切るカットで直接つなげる。これを取りこぼすとカーブネットの
        # ループが閉じず、変形がメッシュ全体へ漏れる。
        if _bridge_face_path(cv_a, cv_b, cv_list, faces, edge_to_face,
                             face_cut_edges, edge_new_verts,
                             segment_edges, ci, si, cv_to_face):
            return
        _log.warning(
            "  curve %d segment %d: geodesic trace failed - %s",
            ci, si, reason)


def _insert_vertex_into_face_edge(face_ring, ekey, new_idx):
    """*face_ring* の *ekey* エッジ端点間に *new_idx* を挿入する。

    Parameters
    ----------
    face_ring : list[int]
        フェイスの頂点インデックスリスト (インプレース変更)。
    ekey : tuple[int, int]
        挿入先エッジの正規化キー。
    new_idx : int
        挿入する CutVertex インデックス。
    """
    for li in range(len(face_ring)):
        va2, vb2 = face_ring[li], face_ring[(li + 1) % len(face_ring)]
        if _edge_key(va2, vb2) == ekey:
            face_ring.insert(li + 1, new_idx)
            return


def _make_tangent_frame(normal):
    """法線ベクトルから正規直交タンジェント/バイノーマル軸を返す (§4.1)。

    Parameters
    ----------
    normal : np.ndarray
        タンジェント空間の法線ベクトル (3,)。

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (tangent, binormal) 正規直交ベクトル対 (各 (3,))。
    """
    n = np.asarray(normal, dtype=float)
    nrm = float(np.linalg.norm(n))
    if nrm < 1e-12:
        return np.array([1., 0., 0.]), np.array([0., 1., 0.])
    n = n / nrm
    abs_n = np.abs(n)
    if abs_n[0] <= abs_n[1] and abs_n[0] <= abs_n[2]:
        ref = np.array([1., 0., 0.])
    elif abs_n[1] <= abs_n[2]:
        ref = np.array([0., 1., 0.])
    else:
        ref = np.array([0., 0., 1.])
    t = ref - np.dot(ref, n) * n
    t_nrm = float(np.linalg.norm(t))
    if t_nrm < 1e-12:
        return np.array([1., 0., 0.]), np.array([0., 1., 0.])
    t /= t_nrm
    b = np.cross(n, t)
    return t, b


def _compute_face_normal_from_positions(pts):
    """頂点座標からポリゴン法線を Newell 法で計算する。

    Parameters
    ----------
    pts : np.ndarray
        頂点座標配列 (n, 3)。

    Returns
    -------
    np.ndarray
        単位法線ベクトル (3,)。退化ポリゴンの場合は [0, 0, 1]。
    """
    if len(pts) < 3:
        return np.array([0., 0., 1.])
    normal = np.zeros(3)
    m = len(pts)
    for i in range(m):
        vc = pts[i]
        vn = pts[(i + 1) % m]
        normal[0] += (vc[1] - vn[1]) * (vc[2] + vn[2])
        normal[1] += (vc[2] - vn[2]) * (vc[0] + vn[0])
        normal[2] += (vc[0] - vn[0]) * (vc[1] + vn[1])
    nrm = float(np.linalg.norm(normal))
    if nrm < 1e-12:
        e1 = pts[1] - pts[0]
        e2 = pts[2] - pts[0]
        normal = np.cross(e1, e2)
        nrm = float(np.linalg.norm(normal))
    return normal / nrm if nrm > 1e-12 else np.array([0., 0., 1.])


def _compute_vertex_tangent_normals(cv_list, new_faces, face_parent,
                                    rest_verts, faces, face_samples=None):
    """§4.1: カット頂点タイプに応じたタンジェント空間法線を計算する。

    - フェイス内部頂点 (SAMPLE): 基底ポリゴン法線に直交する平面
    - エッジ内部頂点 (EDGE_X): メッシュエッジを共有する2フェイスを
      共通平面に展開し、展開平面の法線 (二面角の二等分面法線) を使用。
      展開平面法線 = normalize(n₁ + n₂)。
    - メッシュ頂点: 1-ring インシデントフェイスを平坦化。
      頂点における各フェイスの内角 α_i で重み付けした法線の加重平均
      normalize(Σ α_i · n_i) を使用。指数写像による角度保存平坦化
      のタンジェント平面法線と等価。

    Parameters
    ----------
    cv_list : list[CutVertex]
        カット頂点プール。
    new_faces : list[list[int]]
        拡張後フェイスリング。
    face_parent : list[int]
        各拡張フェイスの元メッシュ面インデックス。
    rest_verts : np.ndarray
        レストメッシュ頂点 (N, 3)。
    faces : list[list[int]]
        元メッシュのフェイスリスト。

    Returns
    -------
    dict[int, np.ndarray]
        頂点 idx → タンジェント空間法線 (3,)。
    """
    orig_normals: dict[int, np.ndarray] = {}
    for fi, face in enumerate(faces):
        pts = rest_verts[face]
        orig_normals[fi] = _compute_face_normal_from_positions(pts)

    vtx_to_orig: dict[int, set] = {}
    for nfi, nface in enumerate(new_faces):
        ofi = face_parent[nfi]
        for v in nface:
            vtx_to_orig.setdefault(v, set()).add(ofi)

    # §4.1: フェイスサンプル (リングに含まれない孤立頂点) を追加
    if face_samples:
        for fi, fs_list in face_samples.items():
            for cv_idx in fs_list:
                vtx_to_orig.setdefault(cv_idx, set()).add(fi)

    tangent_normals: dict[int, np.ndarray] = {}
    for cv in cv_list:
        orig_faces = vtx_to_orig.get(cv.idx)
        if not orig_faces:
            tangent_normals[cv.idx] = np.array([0., 0., 1.])
            continue

        if cv.vtype & CVTYPE_EDGE_X:
            # §4.1 エッジ内部: 共有エッジで2フェイスを共通平面に展開。
            # normalize(n₁ + n₂) は二面角の対称展開法線と数学的に等価。
            # 縮退ケース (n₁ ≈ -n₂, 二面角 ≈ 180°) は共有エッジ軸から構築。
            ofi_list = sorted(orig_faces)
            normals_pair = [orig_normals[f] for f in ofi_list
                            if f in orig_normals]
            if len(normals_pair) >= 2:
                n_unfold = normals_pair[0] + normals_pair[1]
                nrm = float(np.linalg.norm(n_unfold))
                if nrm > 1e-12:
                    tangent_normals[cv.idx] = n_unfold / nrm
                else:
                    # 縮退: 共有エッジ軸を特定し展開法線を構築
                    shared_verts = (set(faces[ofi_list[0]])
                                    & set(faces[ofi_list[1]]))
                    if len(shared_verts) >= 2:
                        sv = sorted(shared_verts)
                        e_dir = rest_verts[sv[1]] - rest_verts[sv[0]]
                        e_len = float(np.linalg.norm(e_dir))
                        if e_len > 1e-12:
                            e_hat = e_dir / e_len
                            # n₁ のエッジ垂直成分 = 展開平面の法線
                            n_perp = (normals_pair[0]
                                      - np.dot(normals_pair[0], e_hat)
                                      * e_hat)
                            n_perp_len = float(np.linalg.norm(n_perp))
                            tangent_normals[cv.idx] = (
                                n_perp / n_perp_len
                                if n_perp_len > 1e-12
                                else normals_pair[0].copy())
                        else:
                            tangent_normals[cv.idx] = normals_pair[0].copy()
                    else:
                        tangent_normals[cv.idx] = normals_pair[0].copy()
            elif normals_pair:
                tangent_normals[cv.idx] = normals_pair[0].copy()
            else:
                tangent_normals[cv.idx] = np.array([0., 0., 1.])

        elif cv.vtype & CVTYPE_SAMPLE:
            # フェイス内部: 基底ポリゴン法線
            ofi = next(iter(orig_faces))
            tangent_normals[cv.idx] = orig_normals.get(
                ofi, np.array([0., 0., 1.]))

        else:
            # §4.1 メッシュ頂点: 1-ring インシデントフェイスを平坦化。
            # 頂点での各フェイス内角 α_i で法線 n_i を重み付けした加重平均を
            # 計算する。これは指数写像 (exponential map) のタンジェント平面
            # 法線と等価であり、角度保存の平坦化を行う。
            mesh_vi = cv.mesh_vidx
            if mesh_vi >= 0:
                weighted_sum = np.zeros(3)
                for fi in orig_faces:
                    if fi not in orig_normals:
                        continue
                    face = faces[fi]
                    try:
                        idx_in_face = face.index(mesh_vi)
                    except ValueError:
                        continue
                    nf = len(face)
                    v_prev = face[(idx_in_face - 1) % nf]
                    v_next = face[(idx_in_face + 1) % nf]
                    d1 = rest_verts[v_prev] - rest_verts[mesh_vi]
                    d2 = rest_verts[v_next] - rest_verts[mesh_vi]
                    d1n = float(np.linalg.norm(d1))
                    d2n = float(np.linalg.norm(d2))
                    if d1n > 1e-12 and d2n > 1e-12:
                        cos_a = float(np.dot(d1, d2)) / (d1n * d2n)
                        alpha = math.acos(max(-1.0, min(1.0, cos_a)))
                    else:
                        alpha = 0.0
                    weighted_sum += alpha * orig_normals[fi]
                nrm = float(np.linalg.norm(weighted_sum))
                if nrm > 1e-12:
                    tangent_normals[cv.idx] = weighted_sum / nrm
                else:
                    tangent_normals[cv.idx] = np.array([0., 0., 1.])
            else:
                tangent_normals[cv.idx] = np.array([0., 0., 1.])

    return tangent_normals


def _split_face_tangent_space(ring, cuts, cv_list, tangent_normals):
    """§4.1: タンジェント空間でCCWソート+ループ走査によりポリゴンを分割する。

    各カット頂点のタンジェント空間にハーフエッジを投影して反時計回りに
    ソートし、``next(h) = ccw_prev(twin(h))`` 規則でループを走査する
    ことで、カットフェイスのサブポリゴンを抽出する。

    Parameters
    ----------
    ring : list[int]
        ポリゴンの頂点インデックスリスト (境界リング)。
    cuts : list[tuple[int, int]]
        カットエッジ (cv_a, cv_b) のリスト。
    cv_list : list[CutVertex]
        カット頂点プール。
    tangent_normals : dict[int, np.ndarray]
        各頂点のタンジェント空間法線。

    Returns
    -------
    list[list[int]]
        分割後のサブポリゴン (頂点数 ≥ 3 のみ)。
    """
    if not cuts:
        return [ring]

    n = len(ring)

    # 境界有向エッジ集合 (フォワード方向)
    boundary_directed: set[tuple[int, int]] = set()
    for li in range(n):
        boundary_directed.add((ring[li], ring[(li + 1) % n]))

    # カットエッジのフィルタ: 境界重複除外 + 重複排除
    seen_ekeys: set[tuple[int, int]] = set()
    effective_cuts: list[tuple[int, int]] = []
    for a, b in cuts:
        ek = _edge_key(a, b)
        if ek in seen_ekeys:
            continue
        if (a, b) in boundary_directed or (b, a) in boundary_directed:
            continue
        seen_ekeys.add(ek)
        effective_cuts.append((a, b))

    if not effective_cuts:
        return [ring]

    # ---- ハーフエッジ構築 ----
    he_data: list[tuple[int, int]] = []      # (origin, dest)
    he_twin: dict[int, int] = {}
    boundary_rev: set[int] = set()           # 境界逆方向 HE
    hi = 0

    for li in range(n):
        u, v = ring[li], ring[(li + 1) % n]
        fwd, rev = hi, hi + 1
        he_data.append((u, v))
        he_data.append((v, u))
        he_twin[fwd] = rev
        he_twin[rev] = fwd
        boundary_rev.add(rev)
        hi += 2

    for a, b in effective_cuts:
        ab, ba = hi, hi + 1
        he_data.append((a, b))
        he_data.append((b, a))
        he_twin[ab] = ba
        he_twin[ba] = ab
        hi += 2

    # ---- 頂点ごと出射 HE を CCW ソート ----
    vtx_out: dict[int, list[int]] = {}
    for idx, (u, _) in enumerate(he_data):
        vtx_out.setdefault(u, []).append(idx)

    ring_pts = np.array([cv_list[v].pos for v in ring])
    fallback_normal = _compute_face_normal_from_positions(ring_pts)

    for v, out_hes in vtx_out.items():
        if len(out_hes) <= 1:
            continue
        tn = tangent_normals.get(v, fallback_normal)
        # 面内での CCW 定義を揃える。頂点法線がフェイス法線と逆を向いて
        # いると、その頂点だけ角度順が反転してループ走査が破綻する。
        if float(np.dot(tn, fallback_normal)) < 0.0:
            tn = -tn
        t_ax, b_ax = _make_tangent_frame(tn)
        v_pos = cv_list[v].pos

        def _angle(h, _vp=v_pos, _ta=t_ax, _ba=b_ax):
            d = cv_list[he_data[h][1]].pos - _vp
            return math.atan2(float(np.dot(d, _ba)),
                              float(np.dot(d, _ta)))

        out_hes.sort(key=_angle)

    # ---- ccw_prev: CCW 循環リストの前方向マップ ----
    ccw_prev: dict[int, int] = {}
    for _v, out_hes in vtx_out.items():
        ne = len(out_hes)
        for i in range(ne):
            ccw_prev[out_hes[i]] = out_hes[(i - 1) % ne]

    # ---- next(h) = ccw_prev( twin(h) ) ----
    he_next: dict[int, int] = {}
    for idx in range(len(he_data)):
        he_next[idx] = ccw_prev[he_twin[idx]]

    # ---- ループ走査でフェイスを抽出 ----
    visited: set[int] = set()
    loops: list[list[int]] = []
    for start in range(len(he_data)):
        if start in visited:
            continue
        loop: list[int] = []
        cur = start
        for _ in range(len(he_data) + 1):
            if cur in visited:
                break
            visited.add(cur)
            loop.append(cur)
            cur = he_next[cur]
        if loop:
            loops.append(loop)

    # ---- 外部ループを除外し頂点リストを抽出 ----
    result: list[list[int]] = []
    for loop in loops:
        if all(h in boundary_rev for h in loop):
            continue
        verts = [he_data[h][0] for h in loop]
        if len(verts) >= 3:
            result.append(verts)

    return result if result else [ring]


def _build_halfedge_structure(face_loops, cv_list, face_cut_edges,
                              segment_edges=None):
    """フェイスループからハーフエッジリストを構築する。

    §4.1: ハーフエッジを向き付きカーブネットセグメントで注釈する。
    seg_ann = (curve_idx, sample_start_idx, is_forward) を設定し、
    カーブの左(+)/右(-)側のトポロジカルな判定に使用する。

    Parameters
    ----------
    face_loops : list[list[int]]
        各フェイスの頂点インデックスリスト。
    cv_list : list[CutVertex]
        カット頂点プール。
    face_cut_edges : dict[int, list[tuple[int, int]]]
        カットエッジ情報 (参照のみ)。
    segment_edges : dict[tuple[int, int], tuple[int, int]] | None
        (cv_a, cv_b) → (curve_idx, sample_start_idx)。

    Returns
    -------
    he_list : list[HalfEdge]
        ハーフエッジリスト。
    cv_to_he : dict[int, list[int]]
        頂点 idx → 起点とするハーフエッジ idx リスト。
    """
    if segment_edges is None:
        segment_edges = {}

    he_list: list[HalfEdge] = []
    edge_he_map: dict[tuple[int, int], int] = {}
    he_idx = 0

    for fi, floop in enumerate(face_loops):
        n_f = len(floop)
        first_he = he_idx
        for li in range(n_f):
            origin = floop[li]
            dest = floop[(li + 1) % n_f]
            he = HalfEdge(idx=he_idx, origin=origin, face=fi)
            # §4.1: 向き付きセグメント注釈
            fwd_key = (origin, dest)
            rev_key = (dest, origin)
            if fwd_key in segment_edges:
                ci_s, si_s = segment_edges[fwd_key]
                he.seg_ann = (ci_s, si_s, True)   # forward
            elif rev_key in segment_edges:
                ci_s, si_s = segment_edges[rev_key]
                he.seg_ann = (ci_s, si_s, False)  # reverse
            he_list.append(he)
            edge_he_map[fwd_key] = he_idx
            he_idx += 1
        for li in range(n_f):
            he_list[first_he + li].next = first_he + (li + 1) % n_f
            he_list[first_he + li].prev = first_he + (li - 1) % n_f

    for (origin, dest), hi in edge_he_map.items():
        twin_key = (dest, origin)
        if twin_key in edge_he_map:
            he_list[hi].twin = edge_he_map[twin_key]

    cv_to_he: dict[int, list[int]] = {}
    for he in he_list:
        cv_to_he.setdefault(he.origin, []).append(he.idx)
    return he_list, cv_to_he


# ======================================================================
# §4.2  ポリゴンラプラシアン (de Goes et al. 2020)
# ======================================================================

def _skew_matrix(v):
    """3×3 歪対称行列 [v]× を返す。

    Parameters
    ----------
    v : np.ndarray
        3D ベクトル (3,)。

    Returns
    -------
    np.ndarray
        (3, 3) 歪対称行列。``[v]× u = v × u`` となる。
    """
    return np.array([
        [0, -v[2], v[1]],
        [v[2], 0, -v[0]],
        [-v[1], v[0], 0],
    ], dtype=float)


# 面の形状品質 (面積 / 周長^2) の下限。カーブがメッシュのエッジループ上に
# ほぼ重なると、カット時に面積がほぼ 0 の sliver 面が生まれる。G_f は
# 1/area で発散するため L_f が桁違いに大きくなり、V^T L V が極端な悪条件と
# なって解が破綻する。品質は寸法に依存しない無次元量なので、これを下限として
# 面積をクランプすることでメッシュ規模によらず L_f の大きさを抑えられる。
# 正常なカット面の品質は 1e-3 を大きく上回るため通常の面には影響しない。
_FACE_QUALITY_EPS = 1e-3
# これ未満の品質 (面積 / 周長^2) は退化面として扱う (浮動小数ノイズより十分大きい)。
_DEGENERATE_QUALITY_EPS = 1e-9


def _polygon_laplacian_face(Xf, lam=1.0, quality_eps=_FACE_QUALITY_EPS):
    """面ごとのポリゴンラプラシアン L_f (Eq.10, de Goes et al. 2020)。

    Parameters
    ----------
    Xf : np.ndarray
        面頂点座標 (n_f, 3)。
    lam : float
        射影残差項 Q_f の重み係数 (論文 Eq.10)。
    quality_eps : float
        sliver 面とみなす形状品質 (面積 / 周長^2) の下限。これを下回る面は
        ``G_f`` の分母に ``quality_eps * 周長^2`` を用いて L_f の発散を防ぐ。

    Returns
    -------
    L_f : np.ndarray
        面ラプラシアン (n_f, n_f)。
    G_f : np.ndarray
        勾配演算子 (3, n_f)。
    area : float
        面積。
    normal : np.ndarray
        面法線 (3,)。
    """
    n_f = len(Xf)
    if n_f < 3:
        return (np.zeros((n_f, n_f)), np.zeros((3, n_f)),
                0.0, np.zeros(3))

    # D_f (n_f × n_f): 差分演算子
    D_f = np.zeros((n_f, n_f))
    for i in range(n_f):
        j = (i + 1) % n_f
        D_f[i, j] = 1.0
        D_f[i, i] = -1.0

    E_f = D_f @ Xf  # (n_f, 3) エッジベクトル

    # A_f (n_f × n_f): 平均演算子
    A_f = np.zeros((n_f, n_f))
    for i in range(n_f):
        j = (i + 1) % n_f
        A_f[i, i] = 0.5
        A_f[i, j] = 0.5

    # 付録A: [a_f] = E_f^T A_f X_f は歪対称行列 (§4.2, de Goes et al. 2020)
    # [a_f]u = a_f × u が成立する 3×3 歪対称行列より直接読み取る。
    # §4.2 クラック付きポリゴンでは非平面になり得るため
    # 反対称部分 (M[i,j] - M[j,i])/2 を抽出して数値安全性を確保する。
    a_mat = E_f.T @ A_f @ Xf
    a_vec = np.array([
        a_mat[2, 1] - a_mat[1, 2],
        a_mat[0, 2] - a_mat[2, 0],
        a_mat[1, 0] - a_mat[0, 1],
    ]) * 0.5
    area = float(np.linalg.norm(a_vec))
    perimeter = float(np.sum(np.linalg.norm(E_f, axis=1)))
    # 退化面 (行って戻るクラックなど、面積が周長^2 に対して実質ゼロ):
    # 法線が浮動小数ノイズの向きになり L_f が意味を持たないので、
    # 勾配項を落として差分ラプラシアン D^T D だけ残す (決定的・移植互換)。
    if area < 1e-14 or area < _DEGENERATE_QUALITY_EPS * perimeter * perimeter:
        return (lam * (D_f.T @ D_f), np.zeros((3, n_f)),
                0.0, np.zeros(3))
    normal = a_vec / area

    # sliver 面対策: 品質が下限を割る面は G_f の分母を持ち上げて
    # L_f のスケールを健全な面と同程度に抑える。面を落とすのではなく
    # クランプすることでカットメッシュの連結性は保たれる。
    area_eff = area
    if perimeter > 1e-30:
        area_min = quality_eps * perimeter * perimeter
        if area_eff < area_min:
            area_eff = area_min

    # 勾配演算子 G_f (Eq.7)
    G_f = (-1.0 / area_eff) * (_skew_matrix(normal) @ E_f.T @ A_f)  # (3, n_f)

    # 射影演算子 Q_f (Eq.8)
    Q_f = D_f - E_f @ G_f  # (n_f, n_f)

    # ラプラシアン L_f (Eq.10)
    L_f = area_eff * (G_f.T @ G_f) + lam * (Q_f.T @ Q_f)
    return L_f, G_f, area_eff, normal


def _assemble_cutmesh_laplacian(face_loops, cv_list, n_h, he_list, lam=1.0):
    """グローバルカットメッシュラプラシアン L_h (n_h × n_h) を組み立てる。

    Parameters
    ----------
    face_loops : list[list[int]]
        各フェイスの頂点インデックス。
    cv_list : list[CutVertex]
        カット頂点プール。
    n_h : int
        ハーフエッジ総数。
    he_list : list[HalfEdge]
        ハーフエッジリスト (参照のみ)。
    lam : float
        ラプラシアンの射影残差重み。

    Returns
    -------
    L_h : scipy.sparse.csr_matrix
        グローバルラプラシアン (n_h, n_h)。
    rest_Xf_list : list[np.ndarray]
        各面のレスト頂点座標。
    face_area_list : list[float]
        各面の面積。
    face_normal_list : list[np.ndarray]
        各面の法線。
    face_Gf_list : list[np.ndarray]
        各面の勾配演算子。
    """
    rows, cols, vals = [], [], []
    rest_Xf_list, face_area_list, face_normal_list, face_Gf_list = [], [], [], []

    hi = 0
    for fi, floop in enumerate(face_loops):
        n_f = len(floop)
        Xf = np.array([cv_list[v].pos for v in floop])
        rest_Xf_list.append(Xf)

        L_f, G_f, area, normal = _polygon_laplacian_face(Xf, lam)
        face_area_list.append(area)
        face_normal_list.append(normal)
        face_Gf_list.append(G_f)

        he_idxs = list(range(hi, hi + n_f))
        for li in range(n_f):
            for lj in range(n_f):
                val = L_f[li, lj]
                if abs(val) > 1e-15:
                    rows.append(he_idxs[li])
                    cols.append(he_idxs[lj])
                    vals.append(val)
        hi += n_f

    L_h = sp.csr_matrix((vals, (rows, cols)), shape=(n_h, n_h))
    return L_h, rest_Xf_list, face_area_list, face_normal_list, face_Gf_list


def _build_VC_matrices(face_loops, cv_list, he_list, n_h,
                       sample_to_cv, curve_samples):
    """V (n_h × n_v) と C (n_h × n_c) 行列を構築する (§4.2 Eq.3)。

    Parameters
    ----------
    face_loops : list[list[int]]
        各フェイスの頂点インデックス。
    cv_list : list[CutVertex]
        カット頂点プール。
    he_list : list[HalfEdge]
        ハーフエッジリスト (参照のみ)。
    n_h : int
        ハーフエッジ総数。
    sample_to_cv : dict[tuple[int, int], int]
        (curve_idx, sample_idx) → CutVertex idx。
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ。

    Returns
    -------
    V : scipy.sparse.csr_matrix
        未知数マッピング行列 (n_h, n_v)。
    C : scipy.sparse.csr_matrix
        制約マッピング行列 (n_h, n_c)。
    n_v : int
        未知数の数。
    n_c : int
        制約の数。
    v_mesh_idx : list[int]
        未知数 → CutVertex idx のマッピング。
    c_info : list[tuple]
        制約情報 (cv_idx, curve_idx, sample_idx, side)。
    c_offset : np.ndarray
        エッジ交差拘束の残差オフセット (n_h, 3)。

    Notes
    -----
    論文 §4.2 の解空間の分割:

    - 第1グループ (未知数 φ_v) = **メッシュ頂点と一致するカット頂点のみ**
    - 第2グループ (拘束 φ_c) = カーブネットサンプルに対応するカット頂点
      **および カーブネットセグメントとメッシュエッジの交点によって
      作られたカット頂点**

    後者 (CVTYPE_EDGE_X) を未知数側に置くと、その頂点で左右の値が共有
    されカーブを跨いだ不連続が短絡する。ここではセグメント [si, si+1]
    上のパラメータ ``seg_t`` を用いて両端サンプルの線形補間として
    ``C`` に組み込む。重みの和は 1 なので分割単位
    ``V 1_v + C 1_c = 1_h`` は保たれる。

    ただし交差点はメッシュ面上にあり、両端サンプルを結ぶ弦の上には
    乗らない。論文がサンプルに対して残差 ``q̆ - p̆`` を持たせているのと
    同じ考え方で、交差点にも残差オフセット ``c_offset`` を持たせる。
    これによりレスト形状が厳密に再現され、測地線トレースの経路精度に
    依存しなくなる。
    """
    mesh_v_set = set()
    sample_cv_set = set()
    # カーブ上のエッジ交差点 (未知数ではなく補間拘束)
    edgex_cv_set = set()

    for cv in cv_list:
        if cv.vtype & CVTYPE_SAMPLE:
            # カーブネットサンプル → 拘束
            sample_cv_set.add(cv.idx)
        elif (cv.vtype & CVTYPE_EDGE_X) and cv.curve_idx >= 0:
            # §4.2: カーブ × メッシュエッジ交差点 → 補間拘束
            edgex_cv_set.add(cv.idx)
        else:
            # 元メッシュ頂点 → 未知数
            mesh_v_set.add(cv.idx)

    v_mesh_idx = sorted(mesh_v_set)
    v_idx_map = {vi: i for i, vi in enumerate(v_mesh_idx)}
    n_v = len(v_mesh_idx)

    # 制約マッピング: 各サンプル → 2 自由度 (左/右)
    c_info = []
    c_idx_map: dict[tuple[int, int], int] = {}
    # (curve_idx, sample_idx, side) → 制約列。EDGE_X の補間に使用する。
    c_col_by_sample: dict[tuple[int, int, int], int] = {}

    for ci, cd in enumerate(curve_samples):
        if cd is None:
            continue
        for si in range(len(cd['positions'])):
            cv_idx = sample_to_cv.get((ci, si))
            if cv_idx is None:
                continue
            for side in (0, 1):
                c_col = len(c_info)
                c_info.append((cv_idx, ci, si, side))
                c_idx_map[(cv_idx, side)] = c_col
                c_col_by_sample[(ci, si, side)] = c_col
    n_c = len(c_info)

    # V と C を構築
    V_rows, V_cols, V_vals = [], [], []
    C_rows, C_cols, C_vals = [], [], []
    n_edgex_ok = 0
    n_edgex_fallback = 0
    n_ann_corner = 0
    side_stats: dict = {}
    c_offset = np.zeros((n_h, 3))

    hi = 0
    for fi, floop in enumerate(face_loops):
        n_f = len(floop)
        for li in range(n_f):
            cv_idx = floop[li]
            he_idx = hi + li

            if cv_idx in v_idx_map:
                V_rows.append(he_idx)
                V_cols.append(v_idx_map[cv_idx])
                V_vals.append(1.0)
            elif cv_idx in sample_cv_set:
                # §4.3: 交点サンプルは「入射セグメントごとのコピー」を持つ。
                # まずこのコーナーのハーフエッジ注釈から (カーブ, サンプル,
                # 側) を直接引く。cv.curve_idx だけを見ると、複数カーブが
                # 溶接された交点で最後に書いたカーブの拘束が全コーナーに
                # 適用され、交わるカーブの片側の値が失われる。
                col = _resolve_corner_constraint(
                    cv_idx, he_list, hi, n_f, li,
                    c_col_by_sample, sample_to_cv)
                if col is None:
                    side = _determine_side(cv_idx, he_list, hi, n_f, li,
                                           cv_list, face_loop=floop,
                                           curve_samples=curve_samples,
                                           stats=side_stats)
                    col = c_idx_map.get((cv_idx, side))
                    if col is None:
                        col = c_idx_map.get((cv_idx, 0))
                else:
                    n_ann_corner += 1
                if col is not None:
                    C_rows.append(he_idx)
                    C_cols.append(col)
                    C_vals.append(1.0)
            elif cv_idx in edgex_cv_set:
                # §4.2: 隣接する 2 サンプルの線形補間として拘束する
                cv = cv_list[cv_idx]
                side = _determine_side(cv_idx, he_list, hi, n_f, li,
                                       cv_list)
                t = cv.seg_t if cv.seg_t >= 0.0 else 0.0
                col0 = c_col_by_sample.get((cv.curve_idx, cv.sample_idx,
                                            side))
                col1 = c_col_by_sample.get((cv.curve_idx, cv.sample_idx + 1,
                                            side))
                if col0 is not None and col1 is not None:
                    if 1.0 - t > 1e-12:
                        C_rows.append(he_idx)
                        C_cols.append(col0)
                        C_vals.append(1.0 - t)
                    if t > 1e-12:
                        C_rows.append(he_idx)
                        C_cols.append(col1)
                        C_vals.append(t)
                    # 交差点は弦の上には乗らないので残差を記録する
                    cv_s0 = sample_to_cv.get((cv.curve_idx, cv.sample_idx))
                    cv_s1 = sample_to_cv.get((cv.curve_idx,
                                              cv.sample_idx + 1))
                    if cv_s0 is not None and cv_s1 is not None:
                        c_offset[he_idx] = cv.pos - (
                            (1.0 - t) * cv_list[cv_s0].pos
                            + t * cv_list[cv_s1].pos)
                    n_edgex_ok += 1
                elif col0 is not None and t <= 1e-9:
                    # セグメント始点と一致する場合のみ単独拘束にできる。
                    C_rows.append(he_idx)
                    C_cols.append(col0)
                    C_vals.append(1.0)
                    cv_s0 = sample_to_cv.get((cv.curve_idx, cv.sample_idx))
                    if cv_s0 is not None:
                        c_offset[he_idx] = cv.pos - cv_list[cv_s0].pos
                    n_edgex_ok += 1
                else:
                    # 相方サンプルが (アイランド除去などで) 失われている。
                    # ここで col0 に重み 1.0 を与えると頂点がサンプル位置へ
                    # 瞬間移動し、レスト形状を再現できない拘束になるため、
                    # 未知数として扱う (分割単位を壊さないため必ず割り当てる)。
                    n_edgex_fallback += 1
                    new_v_col = n_v
                    v_mesh_idx.append(cv_idx)
                    v_idx_map[cv_idx] = new_v_col
                    n_v += 1
                    V_rows.append(he_idx)
                    V_cols.append(new_v_col)
                    V_vals.append(1.0)
            else:
                new_v_col = n_v
                v_mesh_idx.append(cv_idx)
                v_idx_map[cv_idx] = new_v_col
                n_v += 1
                V_rows.append(he_idx)
                V_cols.append(new_v_col)
                V_vals.append(1.0)
        hi += n_f

    if n_edgex_fallback:
        _log.warning(
            "  %d edge-crossing corners had no matching curve sample "
            "(fell back to unknowns)", n_edgex_fallback)
    _log.info("  edge-crossing constraints: %d corners", n_edgex_ok)
    _log.info("  sample corners resolved from half-edge annotation: %d",
              n_ann_corner)
    if side_stats.get('geom') or side_stats.get('default'):
        _log.warning(
            "  side determination: %d annotated, %d geometric, "
            "%d defaulted to +", side_stats.get('ann', 0),
            side_stats.get('geom', 0), side_stats.get('default', 0))

    V = sp.csr_matrix((V_vals, (V_rows, V_cols)), shape=(n_h, n_v))
    C = sp.csr_matrix((C_vals, (C_rows, C_cols)), shape=(n_h, n_c))

    # §4.2: 分割単位 V 1_v + C 1_c = 1_h を検証する
    part = np.asarray(V @ np.ones(n_v) + C @ np.ones(n_c)).ravel()
    n_bad = int(np.sum(np.abs(part - 1.0) > 1e-9))
    if n_bad:
        _log.warning(
            "  partition of unity violated on %d/%d half-edges "
            "(max dev %.3e)", n_bad, n_h,
            float(np.max(np.abs(part - 1.0))))

    return V, C, n_v, n_c, v_mesh_idx, c_info, c_offset


def _resolve_corner_constraint(cv_idx, he_list, he_start, n_f, li,
                               c_col_by_sample, sample_to_cv):
    """コーナーの拘束列を、そのハーフエッジのセグメント注釈から直接引く。

    論文 §4.3 は、カーブの端点にあるサンプルについて「すべてのインシデント
    セグメントに対してサンプルのコピーを作成し、各コピーに対応するセグメント
    の左側と右側の値を割り当てる」と述べている。

    交点では複数のカーブの端点サンプルが同じカット頂点に溶接される。
    ``CutVertex.curve_idx`` はそのうち 1 本しか覚えていないため、それだけを
    使うと交点まわりの全コーナーが同じカーブの拘束を指してしまい、他の
    カーブ側の値が捨てられる。ハーフエッジの ``seg_ann`` は
    ``(curve_idx, sample_start_idx, is_forward)`` を持っているので、
    コーナーごとに正しいカーブとサンプルを特定できる。

    Parameters
    ----------
    cv_idx : int
        コーナーのカット頂点インデックス。
    he_list : list[HalfEdge]
        ハーフエッジリスト。
    he_start : int
        対象フェイス先頭のハーフエッジインデックス。
    n_f : int
        フェイスのコーナー数。
    li : int
        フェイスループ内の位置。
    c_col_by_sample : dict[tuple[int, int, int], int]
        (curve_idx, sample_idx, side) → 拘束列。
    sample_to_cv : dict[tuple[int, int], int]
        (curve_idx, sample_idx) → CutVertex インデックス。

    Returns
    -------
    int | None
        拘束列。注釈から特定できなければ None。
    """
    # 出射ハーフエッジ: このコーナーはその origin
    he_out = he_list[he_start + li] if he_start + li < len(he_list) else None
    if he_out is not None and he_out.seg_ann is not None:
        ci, si, fwd = he_out.seg_ann
        # forward なら origin = サンプル si、reverse なら si + 1
        s_at = si if fwd else si + 1
        col = _lookup_sample_col(cv_idx, ci, s_at, 0 if fwd else 1,
                                 c_col_by_sample, sample_to_cv)
        if col is not None:
            return col

    # 入射ハーフエッジ: このコーナーはその dest
    idx_in = he_start + (li - 1) % n_f
    he_in = he_list[idx_in] if idx_in < len(he_list) else None
    if he_in is not None and he_in.seg_ann is not None:
        ci, si, fwd = he_in.seg_ann
        # forward なら dest = サンプル si + 1、reverse なら si
        s_at = si + 1 if fwd else si
        col = _lookup_sample_col(cv_idx, ci, s_at, 0 if fwd else 1,
                                 c_col_by_sample, sample_to_cv)
        if col is not None:
            return col

    return None


def _lookup_sample_col(cv_idx, ci, si, side, c_col_by_sample, sample_to_cv):
    """(ci, si) が本当に *cv_idx* を指しているときだけ拘束列を返す。"""
    if si < 0:
        return None
    if sample_to_cv.get((ci, si)) != cv_idx:
        return None
    return c_col_by_sample.get((ci, si, side))


def _determine_side(cv_idx, he_list, he_start, n_f, li, cv_list,
                    face_loop=None, curve_samples=None, stats=None):
    """§4.1/§4.2: ハーフエッジのセグメント注釈に基づいて + (0) / - (1) 側を判定する。

    論文 §4.1 で定義されたハーフエッジの向き付きセグメント注釈を使用する。
    CCW 巻きのフェイスでは、各有向エッジの左側がフェイス内部なので:
    - forward (is_forward=True): フェイス内部 = カーブ左側 = + 側 (0)
    - reverse (is_forward=False): フェイス内部 = カーブ右側 = − 側 (1)

    §4.1 クラック対応: 同一頂点がフェイスループ内に複数回出現する場合、
    位置 li における出射/入射ハーフエッジの注釈で判定する。

    注釈が全く得られない場合は、フェイス重心がカーブのどちら側にあるかを
    幾何的に判定する。従来は無条件に 0 を返していたが、それでは片側の値が
    両側に適用され、そのカット頂点で不連続が消える。

    Parameters
    ----------
    cv_idx : int
        判定対象の CutVertex インデックス。
    he_list : list[HalfEdge]
        ハーフエッジリスト (seg_ann 注釈付き)。
    he_start : int
        対象フェイスの最初のハーフエッジインデックス。
    n_f : int
        対象フェイスのハーフエッジ数。
    li : int
        フェイスループ内での位置インデックス。
    cv_list : list[CutVertex]
        カット頂点プール。
    face_loop : list[int] | None
        対象フェイスの頂点インデックス。幾何フォールバックに使用。
    curve_samples : list[dict | None] | None
        カーブサンプル ('tangents' / 'n_plus')。幾何フォールバックに使用。
    stats : dict | None
        統計収集用 ('ann' / 'geom' / 'default' のカウンタ)。

    Returns
    -------
    int
        0 (+側) または 1 (−側)。
    """
    def _tally(key):
        if stats is not None:
            stats[key] = stats.get(key, 0) + 1

    ci = cv_list[cv_idx].curve_idx
    if ci < 0:
        _tally('default')
        return 0
    # §4.1: この位置の出射 HE を優先確認
    he_out = he_list[he_start + li]
    if he_out.seg_ann is not None and he_out.seg_ann[0] == ci:
        _tally('ann')
        return 0 if he_out.seg_ann[2] else 1
    # §4.1: この位置への入射 HE (直前の出射 HE) を確認
    he_in = he_list[he_start + (li - 1) % n_f]
    if he_in.seg_ann is not None and he_in.seg_ann[0] == ci:
        _tally('ann')
        return 0 if he_in.seg_ann[2] else 1
    # フォールバック 1: フェイス内の全 HE を検索
    for k in range(n_f):
        he = he_list[he_start + k]
        if he.seg_ann is not None and he.seg_ann[0] == ci:
            _tally('ann')
            return 0 if he.seg_ann[2] else 1

    # フォールバック 2 (幾何判定): フェイス重心がカーブのどちら側かを
    # 従法線 b = n × t の符号で判定する。b は接線 t の左手側を指すため
    # dot(centroid - p, b) > 0 なら + 側。
    if face_loop is not None and curve_samples is not None:
        cv = cv_list[cv_idx]
        si = cv.sample_idx
        cd = (curve_samples[ci]
              if 0 <= ci < len(curve_samples) else None)
        if cd is not None and 0 <= si < len(cd['tangents']):
            t_vec = np.asarray(cd['tangents'][si], dtype=float)
            n_vec = (np.asarray(cd['n_plus'][si], dtype=float)
                     if 'n_plus' in cd else None)
            if n_vec is not None:
                b_vec = np.cross(n_vec, t_vec)
                b_len = float(np.linalg.norm(b_vec))
                if b_len > 1e-12:
                    b_vec /= b_len
                    pts = np.array([cv_list[v].pos for v in face_loop])
                    centroid = pts.mean(axis=0)
                    d = float(np.dot(centroid - cv.pos, b_vec))
                    if abs(d) > 1e-12:
                        _tally('geom')
                        return 0 if d > 0.0 else 1

    _tally('default')
    return 0


# ======================================================================
# PoissonBindData — シリアライズ可能なコンテナ
# ======================================================================

# ----------------------------------------------------------------------
# カーブネットの効果範囲モード
# ----------------------------------------------------------------------
# デフォーマの ``falloffMode`` プルダウンと 1 対 1 で対応する。効果範囲は
# レストメッシュのバウンディングボックス対角に対する比で決めるので、
# シーンのスケールにもポーズにも依存しない。
FALLOFF_MODE_OFF = 0
FALLOFF_MODE_NARROW = 1
FALLOFF_MODE_NORMAL = 2
FALLOFF_MODE_WIDE = 3
FALLOFF_MODE_CUSTOM = 4

FALLOFF_MODE_LABELS = {
    FALLOFF_MODE_OFF: "無制限 (論文そのまま)",
    FALLOFF_MODE_NARROW: "狭い",
    FALLOFF_MODE_NORMAL: "標準",
    FALLOFF_MODE_WIDE: "広い",
    FALLOFF_MODE_CUSTOM: "カスタム",
}

# レストサイズ (bbox 対角) に対する効果範囲の比。
FALLOFF_MODE_RATIO = {
    FALLOFF_MODE_NARROW: 1.0 / 12.0,
    FALLOFF_MODE_NORMAL: 1.0 / 6.0,
    FALLOFF_MODE_WIDE: 1.0 / 3.0,
}


def falloff_from_mode(mode, rest_size, custom=0.0):
    """モードとレストメッシュの大きさから実際の効果範囲を求める。

    Parameters
    ----------
    mode      : ``FALLOFF_MODE_*``。
    rest_size : レストメッシュのバウンディングボックス対角。
    custom    : ``FALLOFF_MODE_CUSTOM`` のときに使う距離。

    Returns
    -------
    float
        効果範囲 (シーン単位)。0 で無制限 (論文そのまま)。
    """
    mode = int(mode)
    if mode == FALLOFF_MODE_CUSTOM:
        return max(float(custom), 0.0)
    ratio = FALLOFF_MODE_RATIO.get(mode)
    if ratio is None:
        return 0.0
    return max(float(rest_size), 0.0) * ratio


@dataclass
class PoissonBindData:
    """ランタイムポアソンソルバーが必要とする全データを保持する (§4)。"""

    # レスト吸着の強さ (ラプラシアン代表値に対する倍率)。
    REST_ANCHOR_STRENGTH = 4.0

    # 吸着の立ち上がり区間 (rest_falloff に対する比)。
    #
    # 吸着重みはラプラシアン項と綱引きをしていて、重みがラプラシアンの
    # 代表値と同じ大きさになったあたりでカーブの影響が止まる。素朴に
    # 0 → rest_falloff で smoothstep すると、まだ重みが小さい
    # d ≒ 0.3 * rest_falloff で釣り合ってしまい、実効の到達距離が設定値の
    # 1/3 程度しかなかった。そこで立ち上がりを後ろにずらし、ちょうど
    # d = rest_falloff で釣り合うようにする。こうすると属性値がそのまま
    # 「カーブの影響が届く距離」を意味する。
    #
    # smoothstep(u) = REST_ANCHOR_STRENGTH^-1 となる u は約 0.326 なので、
    # (1 - START) / (END - START) をそこに合わせている。
    REST_RAMP_START = 0.65
    REST_RAMP_END = 2.6

    n_verts: int = 0
    rest_verts: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))

    n_h: int = 0
    n_v: int = 0
    n_c: int = 0

    V: Optional[sp.csc_matrix] = None
    C: Optional[sp.csc_matrix] = None

    v_mesh_idx: list = field(default_factory=list)
    c_info: list = field(default_factory=list)
    # §4.2: エッジ交差拘束の残差オフセット (n_h, 3)
    c_offset: Optional[np.ndarray] = None

    _VtLV: Optional[sp.csc_matrix] = None
    _solver: object = None
    _VtL: Optional[sp.csc_matrix] = None

    rest_Xf_list: list = field(default_factory=list)
    face_loops: list = field(default_factory=list)
    face_areas: list = field(default_factory=list)
    face_normals: list = field(default_factory=list)

    # C++ 移植と一括演算のための flat / CSR 表現 (ensure_flat() が構築)。
    # バインド後は不変なので直列化せず、必要になった時点で作る。
    _face_offsets: Optional[np.ndarray] = None
    _face_sizes: Optional[np.ndarray] = None
    _face_flat: Optional[np.ndarray] = None
    _c_info_arr: Optional[np.ndarray] = None
    # 未知数 / 制約 -> メッシュ頂点の散布インデックス (scatter_maps() が構築)
    _scatter: Optional[tuple] = None
    # X̃_f を (n_h, 3) に連結したもの。レスト差し替えで作り直される。
    _rest_Xf_flat: Optional[np.ndarray] = None

    cv_positions: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))
    cv_mesh_vidx: np.ndarray = field(default_factory=lambda: np.empty(0, int))

    rest_sample_positions: list = field(default_factory=list)
    rest_sample_tangents: list = field(default_factory=list)
    rest_sample_normals_plus: list = field(default_factory=list)
    rest_projected: list = field(default_factory=list)

    free_idx: np.ndarray = field(default_factory=lambda: np.empty(0, int))
    pinned_idx: np.ndarray = field(default_factory=lambda: np.empty(0, int))

    # 論文 §5「点単位のハンドルも重心座標でウェイト付けされたソフト拘束を
    # 通じて formulation に組み込むのが簡単である」。
    # メッシュ頂点ごとのピン留め強度 (n_verts,)。0 = 自由、正 = 留める。
    pin_weights: Optional[np.ndarray] = None

    # カーブネットの影響が及ぶ距離 (シーン単位)。0 以下で無効 (論文そのまま)。
    #
    # 式(5) は勾配 y_h しか目標に持たないため、ブロックの絶対位置は
    # そのブロックに触れているカーブ拘束だけで決まる。カーブに覆われて
    # いない領域は「何にも固定されていない」ので、離れたカーブが動くと
    # まるごと引きずられる。レストポーズへの弱い吸着項を足すことで
    # 補正がカーブから exp(-d / rest_falloff) で減衰するようになる。
    rest_falloff: float = 0.0

    # 論文 §5「プロジェクション対レスト」。カット頂点をプロジェクション
    # ポーズのメッシュ頂点に結合する行列 (n_cv, n_verts)。
    # ``cv_warp @ verts`` で任意のポーズにカットメッシュをワープできる。
    cv_warp: Optional[sp.csr_matrix] = None

    # カット頂点がサーフェスから浮いているぶんの残差 (n_cv, 3)。
    # ``cv_pos = cv_warp @ verts + cv_warp_offset``
    cv_warp_offset: Optional[np.ndarray] = None

    # 現在適用されているレストポーズ。None ならプロジェクションポーズ
    # (= バインド時のメッシュ) をそのままレストとして使う (従来動作)。
    rest_override: Optional[np.ndarray] = None

    # unknown_mesh_vidx() / laplacian_scale() のキャッシュ
    _unknown_mv: Optional[np.ndarray] = None
    _lap_scale: Optional[float] = None
    _edge_len: Optional[float] = None
    _curve_dist: Optional[np.ndarray] = None
    _rest_size: Optional[float] = None
    # apply_rest_pose() のキャッシュ
    _rest_key: Optional[float] = None
    _warped_samples: Optional[list] = None
    _sample_cv_map: Optional[dict] = None
    _proj_snapshot: Optional[tuple] = None

    # ラプラシアンスムージング用メッシュ隣接情報
    # mesh_adj[vi] = 元メッシュの隣接頂点インデックスリスト
    mesh_adj: list = field(default_factory=list)

    # 論文 §3 適応的サンプリング用メッシュ平均エッジ長
    avg_edge_length: float = 0.0

    def ensure_flat(self):
        """C++ 移植と一括演算のための flat / CSR 表現を用意する。

        ``face_loops`` (可変長 list of list) や ``c_info`` (tuple の list) は
        Python では扱いやすいが、C++ へはそのまま渡せず要素ごとの走査も遅い。
        バインド後は不変なので一度だけ連続配列へ畳んでおく。

        Notes
        -----
        生成される配列 (いずれもバインド後は不変):

        ``face_offsets`` (n_faces+1,)
            CSR のオフセット。フェイス *fi* のハーフエッジは
            ``face_offsets[fi] : face_offsets[fi+1]``。
        ``face_sizes`` (n_faces,)
            各フェイスのコーナー数 n_f。
        ``face_flat`` (n_h,)
            ``face_loops`` を連結したカット頂点インデックス。
        ``c_info_arr`` (n_c, 4)
            ``c_info`` の (cv_idx, curve_idx, sample_idx, side)。
        """
        if self._face_offsets is not None:
            return
        sizes = np.array([len(fl) for fl in self.face_loops], dtype=np.int64)
        offs = np.zeros(len(sizes) + 1, dtype=np.int64)
        np.cumsum(sizes, out=offs[1:])
        self._face_sizes = sizes
        self._face_offsets = offs
        self._face_flat = (np.concatenate([np.asarray(fl, dtype=np.int64)
                                           for fl in self.face_loops])
                           if len(self.face_loops)
                           else np.zeros(0, dtype=np.int64))
        self._c_info_arr = (np.asarray(self.c_info, dtype=np.int64)
                            .reshape(-1, 4) if self.c_info
                            else np.zeros((0, 4), dtype=np.int64))

    def rest_Xf_flat(self) -> np.ndarray:
        """静止カットポリゴン X̃_f を (n_h, 3) の連続配列で返す。

        ``rest_Xf_list`` を面ごとに走査する代わりに一括で扱えるようにする。
        レストポーズが差し替わると作り直される (:meth:`apply_rest_pose`)。
        """
        if self._rest_Xf_flat is None:
            self._rest_Xf_flat = (
                np.concatenate([np.asarray(x, dtype=float)
                                for x in self.rest_Xf_list])
                if self.rest_Xf_list else np.zeros((0, 3)))
        return self._rest_Xf_flat

    def _set_rest_Xf_from_cv(self, cv_new):
        """カット頂点座標から X̃_f を作り直す (flat と list を同時に更新)。

        ``rest_Xf_list`` の各要素は flat 配列のビューなので、両者が
        食い違うことがない。
        """
        self.ensure_flat()
        flat = cv_new[self._face_flat]
        offs = self._face_offsets
        self._rest_Xf_flat = flat
        self.rest_Xf_list = [flat[offs[i]:offs[i + 1]]
                             for i in range(len(offs) - 1)]

    def scatter_maps(self):
        """未知数 / 制約からメッシュ頂点への写像を返す (バインド後は不変)。

        ``_reconstruct`` と ``_reconstruct_frames`` は同じ写像を位置と変形
        勾配それぞれに適用している。dict でひとつずつ集計する代わりに、
        散布先インデックスを一度だけ作って ``np.add.at`` で一括集計する。

        Returns
        -------
        tuple
            ``(u_rows, u_mv, u_cnt, c_rows, c_mv, c_cnt, pinned)``

            ``u_rows`` / ``u_mv``
                未知数の行番号と、その散布先メッシュ頂点。
            ``u_cnt`` (N,)
                メッシュ頂点ごとの未知数の寄与数 (平均を取る分母)。
            ``c_rows`` / ``c_mv`` / ``c_cnt``
                制約 (side==0) 側の同じもの。
            ``pinned`` (N,) bool
                制約が書き込む頂点。ここは未知数より優先される。
        """
        if self._scatter is not None:
            return self._scatter
        N, n_v = self.n_verts, self.n_v
        cvm = np.asarray(self.cv_mesh_vidx, dtype=np.int64)

        # --- 未知数側 -------------------------------------------------
        cv_idx = np.asarray(self.v_mesh_idx, dtype=np.int64)
        u_mv = np.where((cv_idx >= 0) & (cv_idx < len(cvm)),
                        cvm[np.clip(cv_idx, 0, max(len(cvm) - 1, 0))],
                        cv_idx)          # カット頂点でなければ頂点番号そのもの
        u_ok = (cv_idx < N) & (u_mv >= 0) & (u_mv < N)
        u_rows = np.nonzero(u_ok)[0]
        u_mv = u_mv[u_ok]
        u_cnt = np.bincount(u_mv, minlength=N).astype(float)

        # --- 制約側 (side==0 のみ) ------------------------------------
        self.ensure_flat()
        ca = self._c_info_arr
        if len(ca):
            c_cv = ca[:, 0]
            sel = (ca[:, 3] == 0) & (c_cv >= 0) & (c_cv < len(cvm))
            c_rows = np.nonzero(sel)[0]
            c_mv = cvm[c_cv[sel]]
            keep = (c_mv >= 0) & (c_mv < N)
            c_rows, c_mv = c_rows[keep], c_mv[keep]
        else:
            c_rows = np.zeros(0, dtype=np.int64)
            c_mv = np.zeros(0, dtype=np.int64)
        c_cnt = np.bincount(c_mv, minlength=N).astype(float)

        pinned = np.zeros(N, dtype=bool)
        pinned[c_mv] = True

        self._scatter = (u_rows, u_mv, u_cnt, c_rows, c_mv, c_cnt, pinned)
        return self._scatter

    def to_json(self) -> str:
        def _sp_tri(M):
            if M is None:
                return None
            coo = M.tocoo()
            return {'r': coo.row.tolist(), 'c': coo.col.tolist(),
                    'v': coo.data.tolist(), 'shape': list(coo.shape)}

        return json.dumps({
            'n_verts': self.n_verts,
            'rest_verts': self.rest_verts.tolist(),
            'n_h': self.n_h, 'n_v': self.n_v, 'n_c': self.n_c,
            'V': _sp_tri(self.V), 'C': _sp_tri(self.C),
            'v_mesh_idx': list(self.v_mesh_idx),
            'c_info': self.c_info,
            'c_offset': (None if self.c_offset is None
                         else self.c_offset.tolist()),
            'rest_Xf_list': [xf.tolist() for xf in self.rest_Xf_list],
            'face_loops': self.face_loops,
            'face_areas': self.face_areas,
            'face_normals': [n.tolist() for n in self.face_normals],
            'cv_positions': self.cv_positions.tolist(),
            'cv_mesh_vidx': self.cv_mesh_vidx.tolist(),
            'rest_sample_positions': [p.tolist() for p in self.rest_sample_positions],
            'rest_sample_tangents': [t.tolist() for t in self.rest_sample_tangents],
            'rest_sample_normals_plus': [n.tolist() for n in self.rest_sample_normals_plus],
            'rest_projected': [p.tolist() for p in self.rest_projected],
            'free_idx': self.free_idx.tolist(),
            'pinned_idx': self.pinned_idx.tolist(),
            'mesh_adj': self.mesh_adj,            'avg_edge_length': self.avg_edge_length,
            'cv_warp': _sp_tri(self.cv_warp),
            'cv_warp_offset': (None if self.cv_warp_offset is None
                               or not self.cv_warp_offset.any()
                               else self.cv_warp_offset.tolist()),
        })

    @classmethod
    def from_json(cls, s: str) -> 'PoissonBindData':
        d = json.loads(s)

        def _sp_from(td):
            if td is None:
                return None
            return sp.coo_matrix(
                (td['v'], (td['r'], td['c'])),
                shape=tuple(td['shape'])).tocsc()

        bd = cls()
        bd.n_verts = d['n_verts']
        bd.rest_verts = np.array(d['rest_verts'])
        bd.n_h = d['n_h']; bd.n_v = d['n_v']; bd.n_c = d['n_c']
        bd.V = _sp_from(d.get('V'))
        bd.C = _sp_from(d.get('C'))
        bd.v_mesh_idx = d['v_mesh_idx']
        bd.c_info = [tuple(ci) for ci in d['c_info']]
        _co = d.get('c_offset')
        bd.c_offset = None if _co is None else np.array(_co, dtype=float)
        bd.rest_Xf_list = [np.array(xf) for xf in d['rest_Xf_list']]
        bd.face_loops = d['face_loops']
        bd.face_areas = d['face_areas']
        bd.face_normals = [np.array(n) for n in d['face_normals']]
        bd.cv_positions = np.array(d['cv_positions'])
        bd.cv_mesh_vidx = np.array(d['cv_mesh_vidx'], dtype=int)
        bd.rest_sample_positions = [np.array(p) for p in d['rest_sample_positions']]
        bd.rest_sample_tangents = [np.array(t) for t in d['rest_sample_tangents']]
        bd.rest_sample_normals_plus = [np.array(n) for n in d['rest_sample_normals_plus']]
        bd.rest_projected = [np.array(p) for p in d['rest_projected']]
        bd.free_idx = np.array(d.get('free_idx', []), dtype=int)
        bd.pinned_idx = np.array(d.get('pinned_idx', []), dtype=int)
        bd.mesh_adj = d.get('mesh_adj', [])
        bd.avg_edge_length = float(d.get('avg_edge_length', 0.0))
        _cw = _sp_from(d.get('cv_warp'))
        bd.cv_warp = None if _cw is None else _cw.tocsr()
        _cwo = d.get('cv_warp_offset')
        bd.cv_warp_offset = (None if _cwo is None
                             else np.array(_cwo, dtype=float))
        bd._rebuild_solver()
        return bd

    def _rebuild_solver(self):
        if self.V is None or self.n_h == 0:
            return
        cv_proxy = [CutVertex(idx=i, pos=self.cv_positions[i],
                               mesh_vidx=int(self.cv_mesh_vidx[i]))
                    for i in range(len(self.cv_positions))]
        L_h, _, _, _, _ = _assemble_cutmesh_laplacian(
            self.face_loops, cv_proxy, self.n_h, [], lam=1.0)
        Vt = self.V.T.tocsc()
        self._VtLV = (Vt @ L_h @ self.V).tocsc()
        self._VtL = (Vt @ L_h).tocsc()

        # 論文 Eq.6: V^T L_h V を直接分解 (Chen et al. 2008)
        self._solver = _factorize_solver(self._VtLV)

    # ------------------------------------------------------------------
    # 点単位ソフト拘束 (§5)
    # ------------------------------------------------------------------

    def unknown_mesh_vidx(self) -> np.ndarray:
        """未知数 ui ごとの元メッシュ頂点インデックス (n_v,) を返す。

        対応するメッシュ頂点が無い未知数は -1。
        """
        if self._unknown_mv is not None:
            return self._unknown_mv
        N = self.n_verts
        out = np.full(self.n_v, -1, dtype=int)
        for ui in range(self.n_v):
            if ui >= len(self.v_mesh_idx):
                break
            cv_idx = self.v_mesh_idx[ui]
            if 0 <= cv_idx < len(self.cv_mesh_vidx):
                mv = int(self.cv_mesh_vidx[cv_idx])
            elif cv_idx < N:
                mv = int(cv_idx)
            else:
                continue
            if 0 <= mv < N:
                out[ui] = mv
        self._unknown_mv = out
        return out

    def unknown_pin_weights(self) -> Optional[np.ndarray]:
        """メッシュ頂点ごとの ``pin_weights`` を未知数空間 (n_v,) へ写す。

        ピンが 1 つも無い (すべて 0) 場合は None を返し、呼び出し側が
        従来どおりの分解済みソルバーをそのまま使えるようにする。
        """
        pw = self.pin_weights
        if pw is None or self.n_v == 0:
            return None
        pw = np.asarray(pw, dtype=float)
        if pw.size == 0 or not np.any(pw > 0.0):
            return None
        mv = self.unknown_mesh_vidx()
        out = np.zeros(self.n_v)
        valid = mv >= 0
        idx = mv[valid]
        inside = idx < pw.size
        out[np.flatnonzero(valid)[inside]] = pw[idx[inside]]
        return out

    def laplacian_scale(self) -> float:
        """V^T L V の代表的な大きさ。ピン重みをメッシュ解像度から独立させる。"""
        if self._lap_scale is not None:
            return self._lap_scale
        s = 1.0
        if self._VtLV is not None and self._VtLV.shape[0] > 0:
            diag = np.abs(self._VtLV.diagonal())
            diag = diag[diag > 0.0]
            if diag.size:
                s = float(np.mean(diag))
        self._lap_scale = s
        return s

    def mean_edge_length(self) -> float:
        """元メッシュの平均エッジ長。頂点ホップと距離を変換するのに使う。"""
        if self._edge_len is not None:
            return self._edge_len
        d = 0.0
        if self.mesh_adj and len(self.rest_verts):
            tot, cnt = 0.0, 0
            for vi, nbs in enumerate(self.mesh_adj):
                if vi >= len(self.rest_verts):
                    break
                for nb in nbs:
                    if 0 <= nb < len(self.rest_verts):
                        tot += float(np.linalg.norm(self.rest_verts[vi]
                                                    - self.rest_verts[nb]))
                        cnt += 1
            if cnt:
                d = tot / cnt
        if d <= 0.0 and len(self.rest_verts) > 1:
            # 隣接情報が無いときはバウンディングボックスから概算する
            ext = self.rest_verts.max(axis=0) - self.rest_verts.min(axis=0)
            d = float(np.linalg.norm(ext)) / max(len(self.rest_verts), 1) ** 0.5
        self._edge_len = d if d > 0.0 else 1.0
        return self._edge_len

    def rest_size(self) -> float:
        """レストメッシュのバウンディングボックス対角を返す。

        効果範囲モードの基準になる大きさ。``rest_verts`` はバインド時に
        固定された形状なので、``exactWorldBoundingBox`` と違って
        その時のポーズに左右されない。
        """
        if self._rest_size is not None:
            return self._rest_size
        s = 0.0
        if len(self.rest_verts) > 1:
            ext = self.rest_verts.max(axis=0) - self.rest_verts.min(axis=0)
            s = float(np.linalg.norm(ext))
        self._rest_size = s
        return s

    def rest_anchor_mu(self) -> float:
        """レスト吸着の最大係数を返す。

        重みは :meth:`rest_anchor_weights` でカーブからの距離に応じて
        0 → mu へなめらかに立ち上げるので、局所化はそちらが担当する。
        ここでの mu は「カーブの影響圏外をどれだけ強く上流の変形へ
        固定するか」だけを決める。ラプラシアンの代表的な大きさと同程度
        にしておくと、影響圏外がほぼそのままスキン結果になる。
        """
        if float(self.rest_falloff or 0.0) <= 0.0:
            return 0.0
        return self.laplacian_scale() * self.REST_ANCHOR_STRENGTH

    def curve_distance(self) -> Optional[np.ndarray]:
        """各メッシュ頂点からカーブ拘束までの測地距離 (n_verts,) を返す。

        カーブに接するカットフェイスのメッシュ頂点を距離 0 の種として
        メッシュ稜線グラフ上を Dijkstra で伝播する。ユークリッド距離だと
        手足の反対側や別パーツに漏れてしまうので、必ず接続をたどる。
        """
        if self._curve_dist is not None:
            return self._curve_dist
        n = int(self.n_verts)
        if n <= 0 or not self.face_loops:
            return None

        cvmv = np.asarray(self.cv_mesh_vidx)
        if cvmv.size == 0:
            return None

        # カーブ由来の CV を含むカットフェイスの、メッシュ頂点側を種にする
        seeds = set()
        for loop in self.face_loops:
            has_curve = False
            mverts = []
            for c in loop:
                mv = int(cvmv[c]) if c < cvmv.size else -1
                if mv < 0:
                    has_curve = True
                elif mv < n:
                    mverts.append(mv)
            if has_curve:
                seeds.update(mverts)
        if not seeds:
            return None

        verts = self.rest_verts
        rows, cols, vals = [], [], []
        for vi, nbs in enumerate(self.mesh_adj or []):
            if vi >= n:
                break
            for nb in nbs:
                if 0 <= nb < n:
                    rows.append(vi)
                    cols.append(nb)
                    vals.append(float(np.linalg.norm(verts[vi] - verts[nb])))
        if not rows:
            return None

        graph = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
        from scipy.sparse.csgraph import dijkstra
        d = dijkstra(graph, directed=False, indices=np.array(sorted(seeds)),
                     min_only=True)
        d = np.asarray(d, dtype=float)
        # 到達できない孤立パーツはカーブから無限遠として扱う
        far = ~np.isfinite(d)
        if far.any():
            finite_max = d[~far].max() if (~far).any() else 1.0
            d[far] = finite_max * 2.0 + 1.0
        self._curve_dist = d
        return d

    def rest_anchor_weights(self) -> Optional[np.ndarray]:
        """未知数空間 (n_v,) のレスト吸着重みを返す。

        カーブ近傍では 0 にしてカーブネットの変形を一切邪魔せず、
        カーブから ``rest_falloff`` 離れたところで吸着がラプラシアン項と
        釣り合い、そこから先は上流のスキンがそのまま残るようになる。
        つまり ``rest_falloff`` が「カーブの影響が届く距離」そのもの。

        立ち上がりは ``REST_RAMP_START`` 〜 ``REST_RAMP_END`` 倍の区間で
        smoothstep する。区間の途中 (= ちょうど ``rest_falloff``) で
        釣り合うように後ろへずらしてあるので、ゼロから素直に立ち上げた
        場合より実効の到達距離が長い。
        """
        mu = self.rest_anchor_mu()
        if mu <= 0.0 or self.n_v == 0:
            return None
        d = self.curve_distance()
        if d is None:
            return None
        lo = self.REST_RAMP_START * float(self.rest_falloff)
        hi = self.REST_RAMP_END * float(self.rest_falloff)
        s = np.clip((d - lo) / max(hi - lo, 1e-12), 0.0, 1.0)
        w_mesh = mu * s * s * (3.0 - 2.0 * s)  # smoothstep

        mv = self.unknown_mesh_vidx()
        out = np.zeros(self.n_v)
        valid = mv >= 0
        idx = mv[valid]
        inside = idx < w_mesh.size
        out[np.flatnonzero(valid)[inside]] = w_mesh[idx[inside]]
        return out

    # ------------------------------------------------------------------
    # プロジェクション対レスト (§5)
    # ------------------------------------------------------------------

    def ensure_warp(self, faces) -> bool:
        """``cv_warp`` が無ければ元メッシュのトポロジーから作り直す (§5)。

        Phase 2 より前にバインドされたシーンは ``poissonBindData`` に
        ``cv_warp`` を持たない。結合はカット頂点位置と元メッシュ形状から
        再現できるので、リバインドを強いずにその場で復元する。

        Parameters
        ----------
        faces : list[list[int]]
            元メッシュのフェイス頂点インデックス。

        Returns
        -------
        bool
            ワープが使える状態になったか。
        """
        if self.can_warp():
            return True
        if not faces or self.rest_verts.size == 0 or not len(self.cv_positions):
            return False

        cv_stub = [
            CutVertex(idx=i, pos=np.asarray(self.cv_positions[i], dtype=float),
                      mesh_vidx=int(self.cv_mesh_vidx[i])
                      if i < len(self.cv_mesh_vidx) else -1)
            for i in range(len(self.cv_positions))
        ]
        try:
            W, off = _build_cv_warp_matrix(cv_stub, faces, self.face_loops,
                                           [], self.rest_verts)
        except Exception as e:
            _log.warning("cv_warp の再構築に失敗: %s", e)
            return False

        err = float(np.abs(W @ self.rest_verts + off - self.cv_positions).max())
        tol = WARP_ACCEPT_TOL_FACTOR * max(float(np.linalg.norm(
            self.rest_verts.max(axis=0) - self.rest_verts.min(axis=0))),
            WARP_BARY_TOL_MIN)
        if err > tol:
            _log.warning("cv_warp の再構築が不正確 (%.3e > %.3e)。"
                         "プロジェクション対レストは使えない", err, tol)
            return False

        _log.info("旧バインドから cv_warp を復元した (誤差 %.3e)", err)
        self.cv_warp = W
        self.cv_warp_offset = off
        return True

    def can_warp(self) -> bool:
        """レストポーズの差し替えに必要な結合を持っているか。"""
        return self.cv_warp is not None and self.cv_warp.shape[0] > 0

    def apply_rest_pose(self, verts) -> Optional[list]:
        """レストポーズを *verts* に差し替える (§5 プロジェクション対レスト)。

        論文 §5 より::

            プロジェクションポーズはカーブネットが設計されるサーフェス形状。
            …逆に、レストポーズはカーブネットのアーティキュレーションの前に
            実施されたサーフェス変形の結果を表す。カーブネットとカットメッシュは
            プロジェクションポーズで作成されるので、カッティングルーティンに
            よって以前にキャッシュされたカーブネットサンプルのサーフェスメッシュの
            最近傍点への結合を再利用することで、レストサーフェスの形状に
            両者をワープする。

        カットメッシュの接続性と ``V^T L_h V`` の分解はプロジェクションポーズの
        ままなので再分解は不要。変わるのは静止ポリゴン ``X̃_f`` と
        カーブネットサンプルの静止位置だけ。

        Parameters
        ----------
        verts : np.ndarray
            新しいレストポーズの頂点 (n_verts, 3)。

        Returns
        -------
        list[np.ndarray] | None
            ワープされたカーブネットサンプルのレスト位置 (カーブごと)。
            結合が無い場合は None (呼び出し側は従来動作に落ちる)。
        """
        if not self.can_warp():
            return None
        verts = np.asarray(verts, dtype=float)
        if verts.shape != self.rest_verts.shape:
            _log.warning("apply_rest_pose: 頂点数が違う (%s vs %s)",
                         verts.shape, self.rest_verts.shape)
            return None

        # プロジェクションポーズの原本を一度だけ退避する。以降のワープは
        # 必ずここから行い、差し替えを何度繰り返しても劣化しないようにする。
        if self._proj_snapshot is None:
            self._proj_snapshot = (
                self.rest_verts.copy(),
                self.cv_positions.copy(),
                [np.asarray(p, dtype=float).copy()
                 for p in self.rest_projected],
                [np.asarray(q, dtype=float).copy()
                 for q in self.rest_sample_positions],
                [np.asarray(x, dtype=float).copy()
                 for x in self.rest_Xf_list],
            )
        p_verts, p_cv, p_proj, p_samp, _p_xf = self._proj_snapshot

        key = float(np.abs(verts).sum())
        if self._rest_key == key and self.rest_override is not None:
            return self._warped_samples

        # 1) カット頂点をレスト形状にワープ
        cv_new = np.asarray(self.cv_warp @ verts)
        if self.cv_warp_offset is not None:
            cv_new = cv_new + self.cv_warp_offset

        # 2) 静止カットポリゴン X̃_f を作り直す
        self._set_rest_Xf_from_cv(cv_new)

        # 3) 投影点 p̃ とサンプル位置 q̃ をワープ。
        #    カーブがサーフェスから浮いているぶん (q̃ - p̃) は結合の一部
        #    なので、ワープ後の投影点にそのまま足し戻す。
        warped_samples = []
        new_projected = []
        for ci in range(len(p_proj)):
            proj = p_proj[ci]
            if proj.size == 0:
                new_projected.append(proj.copy())
                warped_samples.append(proj.copy())
                continue
            new_proj = proj.copy()
            for si in range(len(proj)):
                cvi = self._sample_cv(ci, si)
                if cvi is not None:
                    new_proj[si] = cv_new[cvi]
            new_projected.append(new_proj)
            if ci < len(p_samp):
                warped_samples.append(new_proj + (p_samp[ci] - proj))
            else:
                warped_samples.append(new_proj)

        self.rest_projected = new_projected
        self.cv_positions = cv_new
        self.rest_verts = verts.copy()
        self.rest_override = verts
        self.rest_sample_positions = warped_samples
        self._rest_key = key
        self._warped_samples = warped_samples
        self._lap_scale = None
        return warped_samples

    def restore_projection_pose(self) -> bool:
        """``apply_rest_pose`` の差し替えを取り消す (§5)。

        ``useInputAsRest`` を切ったときなど、プロジェクションポーズを
        レストとして使う従来動作に戻すために使う。
        """
        if self._proj_snapshot is None:
            return False
        (self.rest_verts, self.cv_positions, self.rest_projected,
         self.rest_sample_positions, self.rest_Xf_list) = (
            self._proj_snapshot[0].copy(),
            self._proj_snapshot[1].copy(),
            [p.copy() for p in self._proj_snapshot[2]],
            [q.copy() for q in self._proj_snapshot[3]],
            [x.copy() for x in self._proj_snapshot[4]],
        )
        self.rest_override = None
        self._rest_key = None
        self._warped_samples = None
        self._lap_scale = None
        return True

    def _sample_cv(self, ci, si):
        """``(curve_idx, sample_idx)`` に対応するカット頂点を返す。"""
        if self._sample_cv_map is None:
            m = {}
            for (cvi, c, s, _side) in self.c_info:
                m.setdefault((c, s), cvi)
            self._sample_cv_map = m
        return self._sample_cv_map.get((ci, si))


# ======================================================================
# プリコンピュートヘルパー
# ======================================================================

def _find_unconstrained_components(VtLV, tol=1e-9):
    """``V^T L_h V`` の中でカーブネット拘束を持たない連結成分を探す。

    ``L_h`` は半正定値で定数関数がゼロ空間に入る。カーブネットが通る成分は
    ``C`` 側に拘束が移るぶん行和が残って正定値になるが、カーブが 1 本も
    通らない成分は行和が 0 のまま、つまり定数ベクトルがゼロ空間に残る。

    論文はメッシュ全体にカーブネットが行き渡っている前提だが、実際には
    §5 図9 のように「体に取り付けた髪・眉・眼球」を 1 つのメッシュとして
    バインドし、カーブを本体にしか引かないことがある。その場合この成分が
    特異になり、直接ソルバーはゼロ空間の任意の成分を返す。NaN は出ないので
    無言でメッシュが飛ぶ。

    Parameters
    ----------
    VtLV : scipy.sparse.spmatrix
        左辺行列 (n_v, n_v)。
    tol : float
        行和がゼロとみなす閾値 (行列のスケールに対する相対値)。

    Returns
    -------
    tuple[np.ndarray, int]
        (拘束を持たない成分に属する行を示す bool 配列, 成分数)。
    """
    A = VtLV.tocsr()
    n = A.shape[0]
    if n == 0:
        return np.zeros(0, dtype=bool), 0
    from scipy.sparse.csgraph import connected_components
    scale = float(np.abs(A.diagonal()).max()) or 1.0
    row_sum = np.abs(np.asarray(A @ np.ones(n)).ravel())
    ncomp, labels = connected_components(A, directed=False)
    free = np.zeros(n, dtype=bool)
    n_free_comp = 0
    for c in range(ncomp):
        m = (labels == c)
        # その成分のどの行にも拘束が効いていない = 全行の行和が 0
        if row_sum[m].max() <= tol * scale:
            free |= m
            n_free_comp += 1
    return free, n_free_comp


def _factorize_solver(VtLV):
    """論文 Eq.6 の左辺行列 V^T L_h V を直接分解する (Chen et al. 2008)。

    カーブネット拘束を持たない連結成分があると行列が特異になるため、
    その成分の対角に微小値を足してから分解する。こうすると
    「拘束が無い頂点は右辺 (= レスト形状) のまま動かない」という
    妥当な解が選ばれ、ゼロ空間の任意成分が乗って飛ぶことがなくなる。

    Parameters
    ----------
    VtLV : scipy.sparse.csc_matrix
        V^T L_h V 行列 (n_v, n_v)。

    Returns
    -------
    callable
        rhs を受け取り解を返すソルバー関数。
    """
    A = VtLV.tocsc()
    free, n_free_comp = _find_unconstrained_components(A)
    if n_free_comp:
        scale = float(np.abs(A.diagonal()).max()) or 1.0
        shift_val = SINGULAR_SHIFT_FACTOR * scale
        shift = np.zeros(A.shape[0])
        shift[free] = shift_val
        A = (A + sp.diags(shift)).tocsc()
        _log.warning(
            "カーブネット拘束の無い連結成分が %d 個ある (頂点 %d 個)。"
            "V^T L_h V が特異になるため対角を %.1e だけ持ち上げた。"
            "この領域はカーブネットの影響を受けず、その場に留まる",
            n_free_comp, int(free.sum()), shift_val)
    else:
        free, shift_val = None, 0.0
    _lu = factorized(A)

    def _solve_multi(rhs, _f=_lu):
        if rhs.ndim == 1:
            return _f(rhs)
        out = np.empty_like(rhs)
        for c in range(rhs.shape[1]):
            out[:, c] = _f(rhs[:, c])
        return out

    # 呼び出し側 (_stage1 / _stage2) がシフト分を右辺に補えるように、
    # どの行をどれだけ持ち上げたかを添えておく。これをしないと
    # シフトした成分の解が 0 (= 原点) に引き寄せられてしまう。
    _solve_multi.free_rows = free
    _solve_multi.shift = shift_val
    return _solve_multi


def _collect_rest_curve_data(curve_samples, sample_to_cv, cv_list):
    """レストポーズのカーブ位置、接線、法線、投影点を収集する。

    Parameters
    ----------
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ。
    sample_to_cv : dict[tuple[int, int], int]
        (curve_idx, sample_idx) → CutVertex idx。
    cv_list : list[CutVertex]
        カット頂点プール。

    Returns
    -------
    tuple[list, list, list, list]
        (pos_list, tang_list, nplus_list, proj_list)
        各カーブごとの ndarray リスト。
    """
    pos_list, tang_list, nplus_list, proj_list = [], [], [], []
    for ci, cd in enumerate(curve_samples):
        if cd is None:
            pos_list.append(np.empty((0, 3)))
            tang_list.append(np.empty((0, 3)))
            nplus_list.append(np.empty((0, 3)))
            proj_list.append(np.empty((0, 3)))
        else:
            pos_list.append(cd['positions'].copy())
            tang_list.append(cd['tangents'].copy())
            nplus_list.append(
                cd['n_plus'].copy() if 'n_plus' in cd
                else np.tile([0., 1., 0.], (len(cd['positions']), 1)))
            proj = np.empty((len(cd['positions']), 3))
            for si in range(len(cd['positions'])):
                cv_idx = sample_to_cv.get((ci, si))
                proj[si] = (cv_list[cv_idx].pos if cv_idx is not None
                            else cd['positions'][si])
            proj_list.append(proj)
    return pos_list, tang_list, nplus_list, proj_list


def _build_mesh_adjacency(faces, N):
    """元メッシュのフェイスから頂点ごとの隣接リストを構築する。

    Parameters
    ----------
    faces : list[list[int]]
        フェイス頂点インデックス。
    N : int
        頂点総数。

    Returns
    -------
    list[list[int]]
        adj[vi] = 頂点 vi の隣接頂点インデックスリスト。
    """
    adj: list[list[int]] = [[] for _ in range(N)]
    for face in faces:
        nf = len(face)
        for li in range(nf):
            va, vb = face[li], face[(li + 1) % nf]
            if vb not in adj[va]:
                adj[va].append(vb)
            if va not in adj[vb]:
                adj[vb].append(va)
    return adj


# ======================================================================
# プリコンピュート (バインド時)
# ======================================================================

def precompute(
    rest_verts: np.ndarray,
    faces: list,
    curve_samples: list[dict | None],
    n_trace_oversample: int = 5,
    lam: float = 1.0,
    tol_factor: float = CUT_TOL_FACTOR,
) -> PoissonBindData:
    """§4 の全プリコンピュート: カットメッシュ → ポリゴンラプラシアン → 分解。

    Parameters
    ----------
    rest_verts : np.ndarray
        レストメッシュ頂点 (N, 3)。
    faces : list[list[int]]
        フェイス頂点インデックス。
    curve_samples : list[dict | None]
        カーブごとのサンプルデータ (``'positions'``, ``'tangents'``, ``'n_plus'`` キー)。
    n_trace_oversample : int
        トレースのオーバーサンプル係数 (現在未使用)。
    lam : float
        ラプラシアンの射影残差重み。
    tol_factor : float
        カット判定の許容誤差 (bbox 対角比)。既定は論文 §4.1 の 0.001%。

    Returns
    -------
    PoissonBindData
        ランタイムソルバー用のプリコンピュート済みデータ。
    """
    N = len(rest_verts)

    _log.info("Building cut-mesh (§4.1) ...")
    (cv_list, cut_faces, face_loops, face_parent,
     he_list, sample_to_cv, _) = _build_cutmesh(
        rest_verts, faces, curve_samples, tol_factor=tol_factor)

    n_cv = len(cv_list)
    n_faces = len(face_loops)
    n_h = sum(len(fl) for fl in face_loops)
    _log.info("  Cut-mesh: %d verts, %d faces, %d half-edges",
              n_cv, n_faces, n_h)

    _log.info("Assembling polygon Laplacian (§4.2) ...")
    L_h, rest_Xf_list, face_areas, face_normals, _ = \
        _assemble_cutmesh_laplacian(face_loops, cv_list, n_h, he_list, lam)

    _log.info("Building V/C matrices ...")
    V, C, n_v, n_c, v_mesh_idx, c_info, c_offset = _build_VC_matrices(
        face_loops, cv_list, he_list, n_h, sample_to_cv, curve_samples)
    _log.info("  n_v=%d, n_c=%d", n_v, n_c)

    _log.info("Factorising V^T L_h V ...")
    Vt = V.T.tocsc()
    VtLV = (Vt @ L_h @ V).tocsc()
    VtL = (Vt @ L_h).tocsc()

    cv_positions = np.array([cv.pos for cv in cv_list])

    # §5 プロジェクション対レスト: カット頂点を元メッシュ頂点に結合しておく
    _log.info("Building cut-vertex warp binding (§5) ...")
    cv_warp, cv_warp_offset = _build_cv_warp_matrix(
        cv_list, faces, face_loops, face_parent, rest_verts)
    _warp_err = float(np.abs(cv_warp @ rest_verts + cv_warp_offset
                             - cv_positions).max()) \
        if len(cv_list) else 0.0
    _log.info("  warp reproduces projection pose to %.3e", _warp_err)
    # 再現できないワープを使うとレスト差し替えでメッシュが壊れる。
    # 精度が出ないときは機能ごと無効化して従来動作に落とす。
    _warp_tol = WARP_ACCEPT_TOL_FACTOR * max(float(np.linalg.norm(
        rest_verts.max(axis=0) - rest_verts.min(axis=0))), WARP_BARY_TOL_MIN)
    if _warp_err > _warp_tol:
        _log.warning("  warp binding が不正確 (%.3e > %.3e)。"
                     "プロジェクション対レストを無効化する", _warp_err, _warp_tol)
        cv_warp = None
        cv_warp_offset = None

    # 論文 Eq.6: V^T L_h V を直接分解 (Chen et al. 2008)
    solver = _factorize_solver(VtLV)

    rest_pos_list, rest_tang_list, rest_nplus_list, rest_proj_list = \
        _collect_rest_curve_data(curve_samples, sample_to_cv, cv_list)

    cv_mesh_vidx = np.array([cv.mesh_vidx for cv in cv_list], dtype=int)

    sample_mesh_verts = {cv.mesh_vidx for cv in cv_list
                         if (cv.vtype & CVTYPE_SAMPLE) and cv.mesh_vidx >= 0}
    free_idx = np.array(sorted(v for v in range(N)
                                if v not in sample_mesh_verts), dtype=int)
    pinned_idx = np.array(sorted(sample_mesh_verts), dtype=int)

    mesh_adj = _build_mesh_adjacency(faces, N)

    # 論文 §3: 適応的サンプリング用の平均エッジ長を計算
    _edge_set = set()
    for f in faces:
        nf = len(f)
        for li in range(nf):
            va, vb = f[li], f[(li + 1) % nf]
            _edge_set.add((min(va, vb), max(va, vb)))
    if _edge_set:
        _el = np.array([np.linalg.norm(rest_verts[a] - rest_verts[b])
                        for a, b in _edge_set])
        avg_edge_length = float(_el.mean())
    else:
        avg_edge_length = 1.0
    _log.info("Avg edge length: %.6f (%d edges)",
              avg_edge_length, len(_edge_set))

    bd = PoissonBindData(
        n_verts=N, rest_verts=rest_verts.copy(),
        n_h=n_h, n_v=n_v, n_c=n_c,
        V=V.tocsc(), C=C.tocsc(),
        v_mesh_idx=v_mesh_idx, c_info=c_info, c_offset=c_offset,
        _VtLV=VtLV, _solver=solver, _VtL=VtL,
        rest_Xf_list=rest_Xf_list,
        face_loops=face_loops, face_areas=face_areas,
        face_normals=[n.copy() for n in face_normals],
        cv_positions=cv_positions, cv_mesh_vidx=cv_mesh_vidx,
        rest_sample_positions=rest_pos_list,
        rest_sample_tangents=rest_tang_list,
        rest_sample_normals_plus=rest_nplus_list,
        rest_projected=rest_proj_list,
        free_idx=free_idx, pinned_idx=pinned_idx,
        mesh_adj=mesh_adj,
        avg_edge_length=avg_edge_length,
        cv_warp=cv_warp,
        cv_warp_offset=cv_warp_offset,
    )
    _log.info("Bind complete: %d unknowns, %d constraints.", n_v, n_c)
    return bd


# ======================================================================
# ランタイムソルバー (§4.3)
# ======================================================================

# ======================================================================
# PoissonSolver — ステートフル 2段階ソルバー (§4.3)
# ======================================================================

class PoissonSolver:
    """2段階ポアソンソルバー (Algorithm 1, ステップ 5–9)。

    プリコンピュート済みバインドデータを保持し、フレームごとの
    ``solve()`` 呼び出しにはランタイムポーズデータのみが必要。
    論文の純粋な式を使用 (SVD クランプなし、アンカーなし)。

    Parameters
    ----------
    bd : PoissonBindData
        プリコンピュート済みバインドデータ (行列、分解済みソルバー等)。
    """

    def __init__(self, bd: PoissonBindData):
        self.bd = bd

        # 派生定数 (フレームごとの再読み込みを回避)
        self._N = bd.n_verts
        self._n_v = bd.n_v
        self._n_c = bd.n_c
        self._n_h = bd.n_h
        self._eye9 = np.eye(3).ravel()

        # 論文 Eq.6: プリコンピュートで分解済みのソルバーをそのまま使用。
        self._solver = bd._solver

        # §5 点単位ソフト拘束用。ピンやレスト吸着が設定されたときだけ
        # (V^T L V + W) を分解しなおし、重みが変わるまで再利用する。
        # 目標位置はレストポーズ依存なのでキャッシュしない。
        self._pin_key = None
        self._pin_solver = None
        self._pin_w = None

        # §5 頂点フレーム。solve() のたびに更新する。
        # 補正スカルプトを x_v += F_v @ delta_v で運ぶのに使う。
        self._last_f_verts = None

    # ------------------------------------------------------------------
    # 点単位ソフト拘束 (§5)
    # ------------------------------------------------------------------

    def _pin_state(self):
        """現在のピン設定に対応する ``(重み, ソルバー, レスト目標)`` を返す。

        ピンが 1 つも無ければ ``(None, 分解済みソルバー, None)`` を返し、
        論文そのままの Eq.6 の経路になる。

        Returns
        -------
        tuple
            ``(w, solver, target_v)``。``w`` は未知数空間の重み (n_v,)
            にラプラシアンのスケールを掛けたもの。``target_v`` は
            ピン留め先のレスト頂点位置 (n_v, 3)。
        """
        bd = self.bd
        w_raw = bd.unknown_pin_weights()
        anchor = bd.rest_anchor_weights()
        if w_raw is None and anchor is None:
            return None, self._solver, None
        if w_raw is None:
            w_raw = np.zeros(self._n_v)

        # ピン留めの目標位置 = 現在のレストポーズのその頂点。
        # §5 のレスト分離では rest_verts が毎フレーム上流の変形結果に
        # 更新されるので、ここは絶対にキャッシュしてはいけない。
        # (凍結すると最初に評価したポーズへ引き戻してしまう)
        mv = bd.unknown_mesh_vidx()
        target = np.zeros((self._n_v, 3))
        ok = mv >= 0
        target[ok] = bd.rest_verts[mv[ok]]

        key = (int(w_raw.size), float(w_raw.sum()),
               int(np.count_nonzero(w_raw)),
               float(np.dot(w_raw, np.arange(w_raw.size))),
               float(bd.rest_falloff or 0.0))
        if key == self._pin_key and self._pin_solver is not None:
            return self._pin_w, self._pin_solver, target

        w = w_raw * bd.laplacian_scale()
        if anchor is not None:
            w = w + anchor
        A = (bd._VtLV + sp.diags(w)).tocsc()
        solver = _factorize_solver(A)

        self._pin_key = key
        self._pin_solver = solver
        self._pin_w = w
        _log.info("soft constraints: %d pinned vertices, rest anchor on %d "
                  "vertices (falloff %.4g, mu %.4g, Laplacian scale %.4g)",
                  int(np.count_nonzero(w_raw)),
                  0 if anchor is None else int(np.count_nonzero(anchor)),
                  bd.rest_falloff, bd.rest_anchor_mu(), bd.laplacian_scale())
        return w, solver, target

    # ------------------------------------------------------------------
    # パブリック API
    # ------------------------------------------------------------------

    def solve(
        self,
        posed_F_plus: list[np.ndarray | None],
        posed_F_minus: list[np.ndarray | None],
        posed_sample_positions: list[np.ndarray | None],
        rest_sample_positions: list[np.ndarray | None] | None = None,
        want_frames: bool = False,
    ) -> np.ndarray:
        """2段階ポアソンソルブを実行し、頂点位置を返す。

        Parameters
        ----------
        posed_F_plus / posed_F_minus
            カーブごとの変形勾配配列 (§3 Eq.1)。
        posed_sample_positions
            ポーズ済みカーブネットサンプル位置。
        rest_sample_positions
            レストポーズのカーブネットサンプル位置 (デフォルトはバインドデータ)。
        want_frames
            True なら頂点フレーム (論文 §5) も算出して
            :meth:`vertex_frames` から取れるようにする。
            余分な行列積が入るので既定は False。
        """
        bd = self.bd
        N, n_v, n_c, n_h = self._N, self._n_v, self._n_c, self._n_h
        eye9 = self._eye9

        _log.info("PoissonSolver.solve()")

        if rest_sample_positions is None:
            rest_sample_positions = bd.rest_sample_positions

        self._last_f_verts = None

        if n_v == 0 or bd._solver is None:
            if want_frames:
                self._last_f_verts = np.tile(
                    np.eye(3), (N, 1, 1))
            return bd.rest_verts.copy()

        # ステップ 5: f_c — カーブネット変形勾配 → 制約行列
        f_c = self._build_f_c(posed_F_plus, posed_F_minus)

        # F が完全に単位行列かつ位置もレストと一致 → 変形なしのまま返す
        # (バイアス補正が不要な最速パス)
        if f_c is None and self._is_rest_pose(
                posed_sample_positions, rest_sample_positions):
            if want_frames:
                self._last_f_verts = np.tile(np.eye(3), (N, 1, 1))
            return bd.rest_verts.copy()

        if f_c is None:
            f_c = np.tile(eye9, (n_c, 1))

        # ステップ 6: ステージ1 — 論文 Eq.4
        f_v, f_h = self._stage1(f_c)

        # 論文 §5: 補正スカルプトを運ぶための頂点フレーム
        if want_frames:
            self._last_f_verts = self._reconstruct_frames(f_v, f_c)

        # ステップ 7: y_h — ターゲットポリゴン位置
        y_h = self._build_y_h(f_h)

        # ステップ 8: x_c — 変位済みカーブネットサンプル
        x_c = self._build_x_c(f_c, posed_sample_positions, rest_sample_positions)

        # ステップ 9: ステージ2 — 論文 Eq.5
        x_v = self._stage2(x_c, y_h)

        return self._reconstruct(x_v, x_c)

    def solve_from_frames(
        self,
        posed_frames: list[dict | None],
        deformation_grads: list[dict | None],
        rest_frames: list[dict | None] | None = None,
        want_frames: bool = False,
    ) -> np.ndarray:
        """便利メソッド: フレーム dict から F+/F-/positions を抽出し、
        :meth:`solve` を呼び出す。

        Parameters
        ----------
        posed_frames : list[dict | None]
            カーブごとのポーズフレーム (``'positions'`` キー)。
        deformation_grads : list[dict | None]
            カーブごとの変形勾配 (``'F_plus'``, ``'F_minus'`` キー)。
        rest_frames : list[dict | None] | None
            レストフレーム。None の場合はバインドデータを使用。
        want_frames : bool
            True なら頂点フレーム (論文 §5) も算出する。
            :meth:`vertex_frames` から取得できる。

        Returns
        -------
        np.ndarray
            解いた頂点位置 (N, 3)。
        """
        bd = self.bd
        F_plus, F_minus, positions = [], [], []
        for dg in deformation_grads:
            if dg is None:
                F_plus.append(None); F_minus.append(None)
            else:
                F_plus.append(dg['F_plus']); F_minus.append(dg['F_minus'])
        for ci_w, pf in enumerate(posed_frames):
            if pf is None:
                positions.append(None)
            else:
                positions.append(pf['positions'])
        rest_pos = None
        if rest_frames is not None:
            rest_pos = []
            for ci_w, rf in enumerate(rest_frames):
                if rf is None:
                    rest_pos.append(None)
                else:
                    rest_pos.append(rf['positions'])
        return self.solve(F_plus, F_minus, positions, rest_pos,
                          want_frames=want_frames)

    # ------------------------------------------------------------------
    # 内部ステップ
    # ------------------------------------------------------------------

    def _build_f_c(self, posed_F_plus, posed_F_minus):
        """ステップ 5: 制約変形勾配行列 f_c (n_c×9) を構築する。

        Parameters
        ----------
        posed_F_plus : list[np.ndarray | None]
            +側のカーブごとの変形勾配配列。
        posed_F_minus : list[np.ndarray | None]
            −側のカーブごとの変形勾配配列。

        Returns
        -------
        np.ndarray | None
            f_c (n_c, 9)。全てが単位行列の場合は None (早期終了ヒント)。
        """
        bd = self.bd
        n_c = self._n_c
        eye9 = self._eye9

        f_c = np.zeros((n_c, 9))
        all_identity = True
        for k, (cv_idx, ci, si, side) in enumerate(bd.c_info):
            F_arr = posed_F_plus[ci] if side == 0 else posed_F_minus[ci]
            if F_arr is not None and si < len(F_arr):
                f_c[k] = F_arr[si].ravel()
                if all_identity and np.max(np.abs(f_c[k] - eye9)) > 1e-10:
                    all_identity = False
            else:
                f_c[k] = eye9

        return None if all_identity else f_c

    def _is_rest_pose(self, posed_sample_positions, rest_sample_positions):
        """ポーズ位置がレストと一致するか確認する。

        Parameters
        ----------
        posed_sample_positions : list[np.ndarray | None]
            ポーズ済みサンプル位置。
        rest_sample_positions : list[np.ndarray | None]
            レストサンプル位置。

        Returns
        -------
        bool
            全カーブでポーズがレストと一致する場合 True。
        """
        for ci in range(len(posed_sample_positions)):
            pp = posed_sample_positions[ci]
            rp = rest_sample_positions[ci]
            if pp is None and rp is None:
                continue
            if pp is None or rp is None:
                return False
            if len(pp) != len(rp):
                return False
            if np.max(np.abs(np.asarray(pp) - np.asarray(rp))) > 1e-9:
                return False
        return True

    def _stage1(self, f_c):
        """ステップ 6: Eq.4 を解く — 制約から頂点へ F を補間する。

        Parameters
        ----------
        f_c : np.ndarray
            制約変形勾配 (n_c, 9)。

        Returns
        -------
        f_v : np.ndarray
            未知頂点の変形勾配 (n_v, 9)。
        f_h : np.ndarray
            ハーフエッジごとの変形勾配 (n_h, 9)。
        """
        bd = self.bd
        n_v = self._n_v

        C_fc = bd.C @ f_c
        rhs_1 = -(bd._VtL @ C_fc)

        # §5 ソフト拘束: ピン留め頂点は変形勾配を恒等に引き戻す
        w, solver, _ = self._pin_state()
        if w is not None:
            rhs_1 = rhs_1 + w[:, None] * self._eye9[None, :]

        rhs_1 = self._add_singular_shift_rhs(solver, rhs_1, kind='grad')
        f_v = solver(rhs_1)
        f_h = (bd.V @ f_v) + C_fc
        return f_v, f_h

    def _build_y_h(self, f_h):
        """ステップ 7: ターゲットポリゴン位置 y_h を構築する。

        y_h = rest_Xf @ F_avg^T (論文 Eq.5)。

        Parameters
        ----------
        f_h : np.ndarray
            ハーフエッジ変形勾配 (n_h, 9)。

        Returns
        -------
        np.ndarray
            ターゲット位置 (n_h, 3)。
        """
        bd = self.bd
        n_h = self._n_h

        y_h = np.zeros((n_h, 3))
        self._fill_y_h_from_F(y_h, f_h)
        return y_h

    def _fill_y_h_from_F(self, y_h, f_h):
        """論文 Eq.5: y_h = rest_Xf @ F_avg^T を面ごとに計算する。

        CSR 表現 (``face_offsets`` / ``face_sizes``) で全面を一括処理する。
        フェイス内平均は ``add.reduceat``、ポリゴンの回転は ``einsum``。

        Parameters
        ----------
        y_h : np.ndarray
            出力先バッファ (n_h, 3)。インプレースで書き込まれる。
        f_h : np.ndarray
            ハーフエッジ変形勾配 (n_h, 9)。
        """
        bd = self.bd
        bd.ensure_flat()
        offs, sizes = bd._face_offsets, bd._face_sizes
        if not len(sizes):
            return
        # フェイス内のコーナー値を平均して F_f を得る (論文 §4.3)
        F_face = np.add.reduceat(f_h, offs[:-1], axis=0) / sizes[:, None]
        # 各ハーフエッジへ展開。(Xf @ F^T) の行 r は F @ Xf[r] に等しい。
        F_he = np.repeat(F_face, sizes, axis=0).reshape(-1, 3, 3)
        np.einsum('hij,hj->hi', F_he, bd.rest_Xf_flat(), out=y_h)
        c_off = bd.c_offset
        if c_off is not None:
            # エッジ交差拘束は弦上の線形補間なので、実際の交差位置との
            # 残差をフェイスの変形勾配で回して差し引く。これによりレスト
            # 形状が厳密に再現される (論文のサンプル残差 q̆-p̆ と同じ扱い)。
            y_h -= np.einsum('hij,hj->hi', F_he, c_off)

    def _build_x_c(self, f_c, posed_sample_positions, rest_sample_positions):
        """ステップ 8: 制約位置 x_c を構築する。

        論文: p_i = q_i - F_i (q̃_i - p̃_i)

        Parameters
        ----------
        f_c : np.ndarray
            制約変形勾配 (n_c, 9)。
        posed_sample_positions : list[np.ndarray | None]
            ポーズ済みカーブサンプル位置。
        rest_sample_positions : list[np.ndarray | None]
            レストカーブサンプル位置。

        Returns
        -------
        np.ndarray
            制約位置 (n_c, 3)。
        """
        bd = self.bd
        n_c = self._n_c
        if n_c == 0:
            return np.zeros((0, 3))

        bd.ensure_flat()
        ci_arr = bd._c_info_arr[:, 1]
        si_arr = bd._c_info_arr[:, 2]

        # レスト側の残差 (q̃ - p̃) はカーブごとに長さが違う list of ndarray
        # なので、(n_c, 3) へ一度だけ集めてから一括で回す。
        # レストが差し替わると変わるのでキャッシュはしない。
        offset = np.empty((n_c, 3))
        q_posed = np.empty((n_c, 3))
        for ci in np.unique(ci_arr):
            m = (ci_arr == ci)
            si = si_arr[m]
            q_p = np.asarray(posed_sample_positions[ci])
            q_r = np.asarray(rest_sample_positions[ci])
            if (ci < len(bd.rest_projected)
                    and len(bd.rest_projected[ci]) == len(q_r)):
                p_r = np.asarray(bd.rest_projected[ci])
            else:
                p_r = q_r
            q_posed[m] = q_p[si]
            offset[m] = q_r[si] - p_r[si]

        # 論文 §4.3: p_i = q_i - F_i (q̃_i - p̃_i)
        F = f_c.reshape(n_c, 3, 3)
        return q_posed - np.einsum('kij,kj->ki', F, offset)

    def _stage2(self, x_c, y_h):
        """ステップ 9: Eq.5 を解く — 頂点位置 x_v を計算する。

        Parameters
        ----------
        x_c : np.ndarray
            制約位置 (n_c, 3)。
        y_h : np.ndarray
            ターゲットポリゴン位置 (n_h, 3)。

        Returns
        -------
        np.ndarray
            未知頂点位置 (n_v, 3)。
        """
        bd = self.bd

        C_xc = bd.C @ x_c
        rhs_2 = -(bd._VtL @ (C_xc - y_h))

        # §5 ソフト拘束: ピン留め頂点はレスト位置に引き戻す
        w, solver, target_v = self._pin_state()
        if w is not None:
            rhs_2 = rhs_2 + w[:, None] * target_v

        rhs_2 = self._add_singular_shift_rhs(solver, rhs_2, kind='pos')
        return solver(rhs_2)

    def _add_singular_shift_rhs(self, solver, rhs, kind):
        """特異性回避で足した対角シフトのぶんを右辺にも足す。

        :func:`_factorize_solver` はカーブネット拘束を持たない連結成分の
        対角を ``shift`` だけ持ち上げている。右辺を触らないとその成分の解が
        0 (位置なら原点、変形勾配ならゼロ行列) へ引き寄せられてしまうので、
        ``shift * 目標値`` を足して「その場に留まる」解を選ばせる。

        Parameters
        ----------
        solver : callable
            :func:`_factorize_solver` が返したソルバー。
        rhs : np.ndarray
            右辺 (n_v, 3) または (n_v, 9)。
        kind : str
            ``'pos'`` なら目標はレスト頂点位置、``'grad'`` なら単位行列。

        Returns
        -------
        np.ndarray
            補正後の右辺。シフトが無ければ *rhs* をそのまま返す。
        """
        free = getattr(solver, 'free_rows', None)
        shift = getattr(solver, 'shift', 0.0)
        if free is None or not shift:
            return rhs
        bd = self.bd
        target = np.zeros_like(rhs)
        if kind == 'pos':
            mv = bd.unknown_mesh_vidx()
            ok = (mv >= 0) & free
            target[ok] = bd.rest_verts[mv[ok]]
        else:
            target[free] = self._eye9
        return rhs + shift * target

    def _reconstruct_frames(self, f_v, f_c):
        """頂点ごとの変形勾配 F_v をメッシュ頂点に転写する (論文 §5)。

        位置を転写する :meth:`_reconstruct` と同じ写像を変形勾配に対して
        行う。論文 §5 は補正スカルプトを

            x_v += F_v @ delta_v

        で運ぶと述べており、その F_v がこれにあたる。レスト空間で
        記録したスカルプト差分を頂点フレームで回してやることで、
        カーブネットの解を解き直さずにスカルプトを追従させられる。

        Parameters
        ----------
        f_v : np.ndarray
            未知頂点の変形勾配 (n_v, 9)。
        f_c : np.ndarray
            制約の変形勾配 (n_c, 9)。

        Returns
        -------
        np.ndarray
            メッシュ頂点ごとの変形勾配 (N, 3, 3)。カーブネットの影響が
            届かない頂点は単位行列。
        """
        bd = self.bd
        N = self._N

        f_out = np.tile(self._eye9, (N, 1))
        self._scatter_average(f_out, f_v, f_c)
        f_out = np.where(np.isfinite(f_out), f_out, self._eye9[None, :])
        return f_out.reshape(N, 3, 3)

    def _scatter_average(self, out, u_vals, c_vals):
        """未知数と制約の値をメッシュ頂点へ平均して書き込む。

        同じメッシュ頂点に複数のカット頂点が対応することがあるので平均を
        取る。制約 (カーブネット側) は未知数より優先される — 論文 §4.2 の
        「カーブネット拘束を優先し V^T C = 0 を確保する」と同じ扱い。

        Parameters
        ----------
        out : np.ndarray
            出力先 (N, d)。インプレースで書き換える。
        u_vals : np.ndarray
            未知数の値 (n_v, d)。
        c_vals : np.ndarray
            制約の値 (n_c, d)。
        """
        bd = self.bd
        u_rows, u_mv, u_cnt, c_rows, c_mv, c_cnt, pinned = bd.scatter_maps()
        N, d = out.shape

        if len(u_rows):
            acc = np.zeros((N, d))
            np.add.at(acc, u_mv, u_vals[u_rows])
            # 制約が来る頂点は制約で上書きするので、ここでは触らない
            hit = (u_cnt > 0) & (~pinned)
            out[hit] = acc[hit] / u_cnt[hit, None]
        if len(c_rows):
            acc = np.zeros((N, d))
            np.add.at(acc, c_mv, c_vals[c_rows])
            hit = c_cnt > 0
            out[hit] = acc[hit] / c_cnt[hit, None]

    def vertex_frames(self) -> "np.ndarray | None":
        """直前の :meth:`solve` が算出した頂点フレームを返す (論文 §5)。

        Returns
        -------
        np.ndarray | None
            メッシュ頂点ごとの変形勾配 (N, 3, 3)。まだ解いていない場合や
            レストポーズで早期に返した場合は None。
        """
        return self._last_f_verts

    def _reconstruct(self, x_v, x_c):
        """解いた位置を元メッシュ頂点に転写する。

        複数のカット頂点が同じメッシュ頂点にマッピングされる場合、
        その値は平均される。制約 (side==0) 値は未知数より優先される。

        Parameters
        ----------
        x_v : np.ndarray
            未知頂点位置 (n_v, 3)。
        x_c : np.ndarray
            制約位置 (n_c, 3)。

        Returns
        -------
        np.ndarray
            出力頂点位置 (N, 3)。
        """
        bd = self.bd
        x_out = bd.rest_verts.copy()
        self._scatter_average(x_out, x_v, x_c)

        n_bad = int(np.sum(~np.isfinite(x_out)))
        if n_bad > 0:
            _log.warning("Output has %d NaN/Inf values!", n_bad)

        return x_out
