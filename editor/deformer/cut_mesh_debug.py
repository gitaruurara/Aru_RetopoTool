"""カットメッシュのデバッグ可視化 (§4.1)
==========================================
参考論文:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)

カットメッシュは、カーブネットに沿って元メッシュのフェイスを切り開いた
実体のあるポリゴンメッシュである (§4.1)。各フェイスを重心方向に少し縮めた
「分解表示」にすることで、カットが実際にどこを通り、どのフェイスが
どちらの側に属したのかを目で確認できる。

論文 §4.2 の要点として、閉ループのカーブは ``V^TL_hV`` をブロック対角に
分離する。この連結成分でフェイスを色分けすると「変形がカーブのどちら側に
閉じ込められるか」がそのまま見える。腕だけにカーブネットを付けたときに
胴体が動くかどうかは、この色分けで一目で判定できる。

カット頂点は「元メッシュ頂点のアフィン結合」としてバインドしてあるので、
``live=True`` にするとデフォーマ出力メッシュの現在の形状に追従する。
ポーズを付けたままブロック分離を確認できる。

使い方
------
>>> from Aru_RetopoTool.editor.deformer import cut_mesh_debug as cmd_dbg
>>> print(cmd_dbg.report("profileCurveDeformer1"))
>>> cmd_dbg.show("profileCurveDeformer1", mode="block", live=True)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

import maya.api.OpenMaya as om
import maya.cmds as cmds

from Aru_RetopoTool.editor.deformer.poisson_solve import PoissonBindData
from Aru_RetopoTool.editor.logger import get_logger

_log = get_logger(__name__)

DEBUG_GROUP = "AruCutMeshDebug_grp"

#: 可視化モード
MODES = ("block", "side", "curve", "constraint")

#: ブロック色分け用のパレット (見分けやすい彩度の高い色)
_PALETTE = [
    (0.90, 0.25, 0.25), (0.25, 0.55, 0.95), (0.35, 0.80, 0.35),
    (0.95, 0.70, 0.20), (0.70, 0.40, 0.90), (0.20, 0.80, 0.80),
    (0.95, 0.45, 0.75), (0.60, 0.75, 0.25), (0.95, 0.55, 0.30),
    (0.45, 0.45, 0.85), (0.30, 0.85, 0.60), (0.85, 0.35, 0.55),
]

#: ``_PALETTE`` に対応する色名 (レポートで色とブロックを対応付けるため)
_COLOR_NAMES = [
    "赤", "青", "緑", "橙", "紫", "水色",
    "ピンク", "黄緑", "オレンジ", "青紫", "エメラルド", "赤紫",
]


# ======================================================================
# バインドデータの取得
# ======================================================================

def _resolve_deformer(deformer: Optional[str]) -> str:
    """デフォーマ名を解決する。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。None の場合は選択またはシーン内から探す。

    Returns
    -------
    str
        profileCurveDeformer ノード名。
    """
    if deformer:
        return deformer
    for n in cmds.ls(selection=True) or []:
        if cmds.nodeType(n) == "profileCurveDeformer":
            return n
    found = cmds.ls(type="profileCurveDeformer") or []
    if not found:
        raise RuntimeError("シーンに profileCurveDeformer がありません。")
    return found[0]


def load_bind_data(deformer: Optional[str] = None) -> tuple:
    """デフォーマから ``PoissonBindData`` を読み出す。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。None なら自動解決。

    Returns
    -------
    tuple[str, PoissonBindData]
        (デフォーマ名, バインドデータ)。
    """
    dfm = _resolve_deformer(deformer)
    raw = cmds.getAttr("%s.poissonBindData" % dfm) or ""
    if not raw:
        raise RuntimeError("'%s' に poissonBindData がありません。" % dfm)
    return dfm, PoissonBindData.from_json(raw)


# ======================================================================
# 解析
# ======================================================================

def compute_blocks(bd: PoissonBindData) -> np.ndarray:
    """``V^TL_hV`` の連結成分ラベルを返す (§4.2)。

    論文 §4.2 では、カーブネット上のカット頂点 (サンプルおよびカーブと
    メッシュエッジの交点) は必ず拘束側 φ_c に入り、+/- 側で別々の列に
    マップされる。その結果、閉ループのカーブを跨いだ未知数同士は結合が
    消え、``V^TL_hV`` がブロック対角になる。これが L671-674 の
    "bounds the deformation on each curve side" の実体である。

    Parameters
    ----------
    bd : PoissonBindData
        バインドデータ。

    Returns
    -------
    np.ndarray
        未知数列ごとのブロックラベル (n_v,)。
    """
    from scipy.sparse.csgraph import connected_components

    A = bd._VtLV.tocsr().copy()
    A.data[np.abs(A.data) < 1e-12] = 0.0
    A.eliminate_zeros()
    _n, labels = connected_components(A, directed=False)
    return labels


def _face_half_edge_starts(bd: PoissonBindData) -> list:
    """各フェイスの先頭ハーフエッジインデックスを返す。

    Parameters
    ----------
    bd : PoissonBindData
        バインドデータ。

    Returns
    -------
    list[int]
        フェイスごとの開始 half-edge インデックス。
    """
    starts, acc = [], 0
    for loop in bd.face_loops:
        starts.append(acc)
        acc += len(loop)
    return starts


def find_straddling_faces(bd: PoissonBindData) -> list:
    """同一カーブの + と − の両方を含むカットフェイスを列挙する (§4.2)。

    カットが正しく通っていればカットフェイスはカーブの片側にしか属さない。
    両側の拘束を同時に参照しているフェイスはカーブを跨いで短絡している
    証拠であり、そこから変形が反対側へ漏れる。

    Parameters
    ----------
    bd : PoissonBindData
        バインドデータ。

    Returns
    -------
    list[tuple[int, int]]
        (フェイスインデックス, カーブインデックス) のリスト。
    """
    C = bd.C.tocsr()
    starts = _face_half_edge_starts(bd)
    out = []
    for fi, loop in enumerate(bd.face_loops):
        sides: dict = {}
        for li in range(len(loop)):
            for col in C.getrow(starts[fi] + li).indices:
                _cv, ci, _si, side = bd.c_info[col]
                sides.setdefault(ci, set()).add(side)
        for ci, ss in sides.items():
            if len(ss) > 1:
                out.append((fi, ci))
    return out


def report(deformer: Optional[str] = None) -> str:
    """カットメッシュの健全性レポートを文字列で返す。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。None なら自動解決。

    Returns
    -------
    str
        レポート文字列。
    """
    dfm, bd = load_bind_data(deformer)
    labels = compute_blocks(bd)
    counts = np.bincount(labels)
    order = np.argsort(counts)[::-1]
    cv_pos = np.asarray(bd.cv_positions)
    v_pos = cv_pos[list(bd.v_mesh_idx)]

    lines = ["[cut mesh] %s" % dfm,
             "  元メッシュ  : %d 頂点 / %d フェイス"
             % (bd.n_verts, len(bd.rest_verts) and len(bd.face_areas)),
             "  カットメッシュ: %d カット頂点 / %d カットフェイス / %d ハーフエッジ"
             % (len(cv_pos), len(bd.face_loops), bd.n_h),
             "  未知数 φ_v  : %d" % bd.n_v,
             "  拘束   φ_c  : %d" % bd.n_c,
             "",
             "  V^TL_hV の連結成分 (= 変形が閉じ込められる領域): %d"
             % len(counts),
             "  ※ 色は block 表示のパレット順。#0 が最大ブロック = 赤。"]
    for rank, b in enumerate(order[:12]):
        q = v_pos[labels == b]
        lines.append(
            "    #%-2d %-9s n=%-6d (%5.1f%%) bbox x[%7.1f %7.1f] "
            "y[%7.1f %7.1f] z[%7.1f %7.1f]"
            % (rank, _COLOR_NAMES[rank % len(_COLOR_NAMES)], counts[b],
               100.0 * counts[b] / max(bd.n_v, 1),
               q[:, 0].min(), q[:, 0].max(), q[:, 1].min(), q[:, 1].max(),
               q[:, 2].min(), q[:, 2].max()))
    if len(counts) > 12:
        lines.append("    ... 他 %d ブロック" % (len(counts) - 12))

    if len(counts) == 1:
        lines.append("")
        lines.append("  [警告] ブロックが 1 つしかありません。カーブネットの")
        lines.append("         閉ループが成立しておらず、変形がメッシュ全体に")
        lines.append("         波及します (論文 §4.2 の分離が効いていない)。")
    elif counts[order[0]] > 0.5 * max(bd.n_v, 1):
        lines.append("")
        lines.append("  [注意] 最大ブロック #0 (赤) が全体の %.0f%% を占めています。"
                     % (100.0 * counts[order[0]] / max(bd.n_v, 1)))
        lines.append("         このブロックは 1 つの連立系として解かれるので、")
        lines.append("         その境界にあるカーブを動かすとブロック全体が")
        lines.append("         まとめて動きます (例: 腕のカーブで胴体が揺れる)。")
        lines.append("         胴体を切り離したい位置に閉ループのカーブを 1 本")
        lines.append("         足すと、そこでブロックが分かれて波及が止まります")
        lines.append("         (論文 §4.2 \"bounds the deformation on each")
        lines.append("         curve side\")。")

    strad = find_straddling_faces(bd)
    lines.append("")
    lines.append("  カーブを跨いでいるカットフェイス: %d" % len(strad))
    for fi, ci in strad[:10]:
        ctr = cv_pos[bd.face_loops[fi]].mean(axis=0)
        lines.append("    face %-6d curve %-3d  中心 %s"
                     % (fi, ci, np.round(ctr, 2)))
    if len(strad) > 10:
        lines.append("    ... 他 %d 件" % (len(strad) - 10))

    return "\n".join(lines)


# ======================================================================
# 可視化
# ======================================================================

def _corner_colors(bd: PoissonBindData, mode: str) -> np.ndarray:
    """ハーフエッジ (フェイスコーナー) ごとの RGB 色を返す。

    Parameters
    ----------
    bd : PoissonBindData
        バインドデータ。
    mode : str
        ``MODES`` のいずれか。

    Returns
    -------
    np.ndarray
        (n_h, 3) の RGB。
    """
    colors = np.full((bd.n_h, 3), 0.35)
    V = bd.V.tocsr()
    C = bd.C.tocsr()

    if mode == "block":
        labels = compute_blocks(bd)
        # 大きいブロックから順にパレットを割り当てて見分けやすくする
        counts = np.bincount(labels)
        rank = {int(b): i for i, b in enumerate(np.argsort(counts)[::-1])}
        starts = _face_half_edge_starts(bd)
        for fi, loop in enumerate(bd.face_loops):
            blk = None
            for li in range(len(loop)):
                idx = V.getrow(starts[fi] + li).indices
                if len(idx):
                    blk = int(labels[idx[0]])
                    break
            col = (_PALETTE[rank[blk] % len(_PALETTE)] if blk is not None
                   else (0.25, 0.25, 0.25))
            colors[starts[fi]:starts[fi] + len(loop)] = col
        return colors

    if mode == "side":
        for he in range(bd.n_h):
            idx = C.getrow(he).indices
            if not len(idx):
                continue
            side = bd.c_info[idx[0]][3]
            colors[he] = (0.95, 0.30, 0.30) if side == 0 else (0.30, 0.50, 0.95)
        return colors

    if mode == "curve":
        for he in range(bd.n_h):
            idx = C.getrow(he).indices
            if not len(idx):
                continue
            ci = bd.c_info[idx[0]][1]
            colors[he] = _PALETTE[ci % len(_PALETTE)]
        return colors

    # constraint: 未知数 = 灰 / 拘束 = 黄
    for he in range(bd.n_h):
        if len(C.getrow(he).indices):
            colors[he] = (0.95, 0.85, 0.20)
        else:
            colors[he] = (0.40, 0.40, 0.45)
    return colors


# ======================================================================
# トポロジ + 元メッシュへのバインド (変形追従用)
# ======================================================================

#: 1 カット頂点をアフィン結合で表すときに使う元メッシュ頂点の最大数
_BIND_K = 8


class CutMeshTopology(object):
    """カットメッシュの描画トポロジと、元メッシュ頂点へのバインド。

    カット頂点の座標は「元メッシュ頂点のアフィン結合」として保持する。
    こうすると、デフォーマ出力メッシュの現在の頂点座標を代入するだけで
    カットメッシュを変形後の姿で描けるため、ビューポートで実際の変形と
    ブロック分離を重ねて確認できる。

    Attributes
    ----------
    loop_flat : np.ndarray
        (H,) 有効カットフェイスのコーナーを平坦化したカット頂点インデックス。
    loop_face : np.ndarray
        (H,) 各コーナーが属する (再採番後の) フェイスインデックス。
    nxt : np.ndarray
        (H,) 同一フェイス内の次コーナーの平坦インデックス。
    face_start, face_len : np.ndarray
        (F,) フェイスごとの開始位置と辺数。
    tri_colors : np.ndarray
        (3H, 4) 三角形頂点カラー (RGBA)。座標と違い変形しないので使い回す。
    cv_rest : np.ndarray
        (n_cv, 3) カット頂点のレスト座標。
    bind_idx : np.ndarray
        (n_cv, K) 元メッシュ頂点インデックス。
    bind_w : np.ndarray
        (n_cv, K) アフィン重み。行和は 1 (バインドできない頂点は 0)。
    bind_ok : np.ndarray
        (n_cv,) bool。False の頂点はレスト座標をそのまま使う。
    n_faces, n_blocks : int
        カットフェイス数とブロック数。
    """

    __slots__ = ("loop_flat", "loop_face", "nxt", "face_start", "face_len",
                 "tri_colors", "cv_rest", "bind_idx", "bind_w", "bind_ok",
                 "bind_off", "n_faces", "n_blocks", "n_mesh_verts")


def _affine_weights(target: np.ndarray, quad: np.ndarray) -> Optional[np.ndarray]:
    """``sum w_j Q_j = target`` かつ ``sum w_j = 1`` を最小二乗で解く。

    アフィン結合なので、元メッシュが剛体移動しても相対位置が保たれる。
    アンカーが 4 点以上あると系は劣決定になるが、``lstsq`` は最小ノルム解を
    返すため重みが発散せず、点がアンカーのアフィン包に含まれていれば厳密に
    再現できる。

    Parameters
    ----------
    target : np.ndarray
        (3,) 再現したい点。
    quad : np.ndarray
        (k, 3) 元メッシュ頂点のレスト座標。

    Returns
    -------
    np.ndarray | None
        (k,) の重み。解が発散する場合は None。
    """
    k = len(quad)
    if k == 0:
        return None
    if k == 1:
        return np.array([1.0])

    # sum w = 1 の行は座標行と桁を揃えるためスケールしてから連立する
    scale = float(np.abs(quad - quad.mean(axis=0)).max()) or 1.0
    A = np.empty((4, k))
    A[:3] = quad.T
    A[3] = scale * 1e3
    b = np.empty(4)
    b[:3] = target
    b[3] = scale * 1e3

    w, _res, _rank, _sv = np.linalg.lstsq(A, b, rcond=None)
    if not np.all(np.isfinite(w)) or np.abs(w).max() > 20.0:
        return None
    return w


#: アフィン再現がこの割合 (バウンディングボックス比) を超えたら不採用
_BIND_TOL = 1e-4


def _build_vertex_binding(bd: PoissonBindData, topo: CutMeshTopology) -> None:
    """カット頂点を元メッシュ頂点のアフィン結合として表す。

    - 元メッシュ頂点そのもののカット頂点 (``cv_mesh_vidx >= 0``) は重み 1。
    - カーブサンプルやエッジ交差点は、同じカットフェイスに含まれる
      「元メッシュ頂点コーナー」のアフィン結合で表す。エッジ交差点は
      2 点の線形補間になるため厳密に一致する。

    Parameters
    ----------
    bd : PoissonBindData
        バインドデータ。
    topo : CutMeshTopology
        書き込み先トポロジ。
    """
    cv_pos = topo.cv_rest
    cv_mv = np.asarray(bd.cv_mesh_vidx, dtype=int)
    rest = np.asarray(bd.rest_verts, dtype=float)
    n_cv = len(cv_pos)

    idx = np.zeros((n_cv, _BIND_K), dtype=np.int32)
    wgt = np.zeros((n_cv, _BIND_K), dtype=float)
    ok = np.zeros(n_cv, dtype=bool)

    direct = (cv_mv >= 0) & (cv_mv < len(rest))
    idx[direct, 0] = cv_mv[direct]
    wgt[direct, 0] = 1.0
    ok[direct] = True

    # 各カット頂点について、同じフェイスにある元メッシュ頂点コーナーを集める
    fs, fl = topo.face_start, topo.face_len
    face_corners = [topo.loop_flat[fs[f]:fs[f] + fl[f]]
                    for f in range(len(fs))]
    face_anchors = [[int(c) for c in cor if direct[c]] for cor in face_corners]

    cv_faces: dict = {}
    cand: dict = {}
    for f, cor in enumerate(face_corners):
        for c in cor:
            c = int(c)
            if direct[c]:
                continue
            cv_faces.setdefault(c, []).append(f)
            if face_anchors[f]:
                cand.setdefault(c, set()).update(face_anchors[f])

    scale = float(np.linalg.norm(rest.max(axis=0) - rest.min(axis=0))) or 1.0
    tol = scale * _BIND_TOL
    worst = 0.0

    def _solve(cvi, anchors):
        """アンカー集合から重みと残差を求める。"""
        a = sorted(anchors)
        q = cv_pos[a]
        if len(a) > _BIND_K:
            d = np.linalg.norm(q - cv_pos[cvi], axis=1)
            sel = np.argsort(d)[:_BIND_K]
            a = [a[i] for i in sel]
            q = q[sel]
        w = _affine_weights(cv_pos[cvi], q)
        if w is None:
            return None, None, np.inf
        res = float(np.linalg.norm(w.dot(q) - cv_pos[cvi]))
        return a, w, res

    for cvi in sorted(cv_faces):
        anchors = cand.get(cvi)
        a, w, res = (None, None, np.inf) if not anchors \
            else _solve(cvi, anchors)
        if res > tol:
            # 隣接フェイスまで広げてアンカーを増やす (細いフェイスの救済)
            wide = set(anchors or ())
            for f in cv_faces[cvi]:
                for c in face_corners[f]:
                    for f2 in cv_faces.get(int(c), ()):
                        wide.update(face_anchors[f2])
            if len(wide) > len(anchors or ()):
                a2, w2, res2 = _solve(cvi, wide)
                if res2 < res:
                    a, w, res = a2, w2, res2
        if a is None:
            continue
        worst = max(worst, res)
        k = len(a)
        idx[cvi, :k] = cv_mv[a]
        wgt[cvi, :k] = w
        ok[cvi] = True

    topo.bind_idx = idx
    topo.bind_w = wgt
    topo.bind_ok = ok
    topo.bind_off = np.zeros((n_cv, 3), dtype=float)
    topo.n_mesh_verts = int(bd.n_verts)

    # どのカットフェイスからもアンカーを拾えなかった頂点は最近傍頂点に付ける。
    # レストのまま置き去りにすると、そこだけ変形に追従せず大きく破綻する。
    for cvi in np.flatnonzero(~ok):
        nv = int(np.argmin(np.linalg.norm(rest - cv_pos[cvi], axis=1)))
        idx[cvi, 0] = nv
        wgt[cvi, 0] = 1.0
        topo.bind_off[cvi] = cv_pos[cvi] - rest[nv]
        ok[cvi] = True

    if worst > tol:
        _log.debug("[cut mesh] バインド残差 max=%.4g (許容 %.4g)", worst, tol)


def build_topology(deformer: Optional[str] = None, mode: str = "block",
                   bd: Optional[PoissonBindData] = None) -> CutMeshTopology:
    """描画用トポロジ・カラー・バインドをまとめて構築する。

    重い処理はここに集約し、フレームごとの更新は
    ``evaluate_positions`` + ``buffers_from_positions`` だけで済むようにする。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。``bd`` を渡す場合は無視される。
    mode : str
        色分けモード。``build_draw_buffers`` を参照。
    bd : PoissonBindData | None
        読み込み済みのバインドデータ。

    Returns
    -------
    CutMeshTopology
        トポロジ。
    """
    if mode not in MODES:
        raise ValueError("mode は %s のいずれかです。" % (MODES,))
    if bd is None:
        _dfm, bd = load_bind_data(deformer)

    he_colors = _corner_colors(bd, mode)
    starts = _face_half_edge_starts(bd)

    keep_h, loop_flat, loop_face, nxt = [], [], [], []
    face_start, face_len = [], []
    for fi, loop in enumerate(bd.face_loops):
        n = len(loop)
        if n < 3:
            continue
        base = len(loop_flat)
        f = len(face_start)
        face_start.append(base)
        face_len.append(n)
        for li in range(n):
            loop_flat.append(int(loop[li]))
            loop_face.append(f)
            nxt.append(base + (li + 1) % n)
            keep_h.append(starts[fi] + li)

    if not loop_flat:
        raise RuntimeError("カットフェイスがありません。")

    topo = CutMeshTopology()
    topo.loop_flat = np.asarray(loop_flat, dtype=np.int32)
    topo.loop_face = np.asarray(loop_face, dtype=np.int32)
    topo.nxt = np.asarray(nxt, dtype=np.int32)
    topo.face_start = np.asarray(face_start, dtype=np.int32)
    topo.face_len = np.asarray(face_len, dtype=np.int32)
    topo.cv_rest = np.asarray(bd.cv_positions, dtype=float)
    topo.n_faces = len(face_start)
    topo.n_blocks = int(len(np.unique(compute_blocks(bd))))

    cols = np.asarray(he_colors, dtype=float)[keep_h]
    ctr_col = (np.add.reduceat(cols, topo.face_start, axis=0)
               / topo.face_len[:, None])
    tri_c = np.empty((len(cols) * 3, 4), dtype=float)
    tri_c[0::3, :3] = ctr_col[topo.loop_face]
    tri_c[1::3, :3] = cols
    tri_c[2::3, :3] = cols[topo.nxt]
    tri_c[:, 3] = 1.0
    topo.tri_colors = tri_c

    _build_vertex_binding(bd, topo)
    return topo


def evaluate_positions(topo: CutMeshTopology,
                       live_verts: Optional[np.ndarray] = None) -> np.ndarray:
    """カット頂点の現在座標を返す。

    Parameters
    ----------
    topo : CutMeshTopology
        トポロジ。
    live_verts : np.ndarray | None
        (n_verts, 3) 変形後の元メッシュ頂点座標 (ワールド)。
        None ならレスト座標をそのまま返す。

    Returns
    -------
    np.ndarray
        (n_cv, 3) カット頂点座標。
    """
    if live_verts is None:
        return topo.cv_rest
    lv = np.asarray(live_verts, dtype=float)
    if lv.shape[0] != topo.n_mesh_verts:
        # 頂点数が違う = バインド時と別のメッシュ。レストにフォールバック
        return topo.cv_rest
    pos = np.einsum("ik,ikj->ij", topo.bind_w, lv[topo.bind_idx])
    pos += topo.bind_off
    if not topo.bind_ok.all():
        pos[~topo.bind_ok] = topo.cv_rest[~topo.bind_ok]
    return pos


def deformed_mesh_points(deformer: str) -> Optional[np.ndarray]:
    """デフォーマ出力メッシュの現在の頂点座標 (ワールド) を返す。

    バインドデータはワールド空間で作られている
    (``curve_profile_rig`` が ``MSpace.kWorld`` で取得) ため、こちらも
    ワールド空間で読む。

    Parameters
    ----------
    deformer : str
        profileCurveDeformer ノード名。

    Returns
    -------
    np.ndarray | None
        (n, 3) の頂点座標。取得できない場合は None。
    """
    try:
        geo = cmds.deformer(deformer, query=True, geometry=True) or []
    except Exception:
        geo = []
    for g in geo:
        try:
            shp = g if cmds.nodeType(g) == "mesh" else None
            if shp is None:
                shp = (cmds.listRelatives(g, shapes=True,
                                          noIntermediate=True,
                                          fullPath=True) or [None])[0]
            if not shp or cmds.nodeType(shp) != "mesh":
                continue
            sel = om.MSelectionList()
            sel.add(shp)
            fn = om.MFnMesh(sel.getDagPath(0))
            pts = fn.getPoints(om.MSpace.kWorld)
            return np.array([[p.x, p.y, p.z] for p in pts], dtype=float)
        except Exception:
            continue
    return None


def buffers_from_positions(topo: CutMeshTopology, cv_pos: np.ndarray,
                           shrink: float = 0.12) -> "CutMeshDrawBuffers":
    """カット頂点座標から描画バッファを組み立てる (§4.1)。

    各カットフェイスを重心方向へ *shrink* だけ縮めた分解表示にする。
    三角形化は重心ファンなので、凹形状や重複頂点を含むフェイスでも破綻
    しない。

    Parameters
    ----------
    topo : CutMeshTopology
        トポロジ。
    cv_pos : np.ndarray
        (n_cv, 3) カット頂点座標。
    shrink : float
        重心方向へ縮める割合 (0.0〜0.45)。

    Returns
    -------
    CutMeshDrawBuffers
        描画バッファ。
    """
    shrink = float(min(max(shrink, 0.0), 0.45))
    P = np.asarray(cv_pos, dtype=float)[topo.loop_flat]
    ctr = (np.add.reduceat(P, topo.face_start, axis=0)
           / topo.face_len[:, None])
    ctr_h = ctr[topo.loop_face]
    Ps = P + (ctr_h - P) * shrink
    Pn = Ps[topo.nxt]

    h = len(P)
    tri = np.empty((h * 3, 3), dtype=float)
    tri[0::3] = ctr_h
    tri[1::3] = Ps
    tri[2::3] = Pn

    line = np.empty((h * 2, 3), dtype=float)
    line[0::2] = Ps
    line[1::2] = Pn

    buf = CutMeshDrawBuffers()
    buf.tri_points = tri
    buf.tri_colors = topo.tri_colors[:, :3]
    buf.line_points = line
    buf.bbox_min = tri.min(axis=0)
    buf.bbox_max = tri.max(axis=0)
    buf.n_faces = topo.n_faces
    buf.n_blocks = topo.n_blocks
    return buf


class CutMeshDrawBuffers(object):
    """ロケータ描画用に展開済みの三角形・線分バッファ。

    Attributes
    ----------
    tri_points : np.ndarray
        (3T, 3) 三角形頂点座標。インデックスなしの展開済み。
    tri_colors : np.ndarray
        (3T, 3) 三角形頂点カラー。
    line_points : np.ndarray
        (2E, 3) カットフェイス外周の線分。
    bbox_min, bbox_max : np.ndarray
        バウンディングボックス。
    n_faces, n_blocks : int
        カットフェイス数とブロック数。
    """

    __slots__ = ("tri_points", "tri_colors", "line_points",
                 "bbox_min", "bbox_max", "n_faces", "n_blocks")


def build_draw_buffers(deformer: Optional[str] = None, mode: str = "block",
                       shrink: float = 0.12,
                       live: bool = False) -> CutMeshDrawBuffers:
    """カットメッシュを描画バッファに展開する (§4.1)。

    各カットフェイスを重心方向に *shrink* だけ縮めた「分解表示」にする。
    こうするとカット線が隙間として現れ、元メッシュのどこがどう切り開かれた
    かが見える。三角形化は重心ファンで行うため、フェイスが重複頂点を持つ
    (クラック) 場合や凹形状でも破綻しない。

    ポリゴンを実体化せずロケータで直接描画するため、マテリアルもシェーディング
    グループも不要で、シーンにジオメトリを残さない。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。None なら選択またはシーンから自動解決。
    mode : str
        色分けモード。

        - ``"block"``     : ``V^TL_hV`` の連結成分。変形が閉じ込められる
          領域がそのまま見える (既定)。
        - ``"side"``      : カーブの + 側 (赤) / − 側 (青)。
        - ``"curve"``     : 拘束が属するカーブごとの色。
        - ``"constraint"``: 未知数 φ_v (灰) と拘束 φ_c (黄)。
    shrink : float
        フェイスを重心方向へ縮める割合 (0.0〜0.45)。
    live : bool
        True ならデフォーマ出力メッシュの現在の頂点座標に追従させる。

    Returns
    -------
    CutMeshDrawBuffers
        描画バッファ。
    """
    if mode not in MODES:
        raise ValueError("mode は %s のいずれかです。" % (MODES,))

    dfm, bd = load_bind_data(deformer)
    topo = build_topology(mode=mode, bd=bd)
    lv = deformed_mesh_points(dfm) if live else None
    return buffers_from_positions(topo, evaluate_positions(topo, lv), shrink)


def show(deformer: Optional[str] = None, mode: str = "block",
         shrink: float = 0.12, name: str = "cutMeshDebug",
         live: bool = True) -> str:
    """カットメッシュをデバッグロケータとして表示する (§4.1)。

    ``AruCutMeshLocator`` を生成し、VP2 上にカットメッシュを直接描画する。
    ポリゴンではないのでマテリアルの割り当てが不要で、シーンにジオメトリを
    残さず、書き出しにも影響しない。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。None なら選択またはシーンから自動解決。
    mode : str
        色分けモード。``build_draw_buffers`` を参照。
    shrink : float
        フェイスを重心方向へ縮める割合 (0.0〜0.45)。
    name : str
        生成するトランスフォーム名。
    live : bool
        True ならデフォーマ出力メッシュの変形に追従させる。

    Returns
    -------
    str
        生成したロケータのトランスフォーム名。
    """
    if mode not in MODES:
        raise ValueError("mode は %s のいずれかです。" % (MODES,))

    dfm, bd = load_bind_data(deformer)
    # データを読めることを先に確認してからノードを作る
    del bd

    from Aru_RetopoTool.editor.curvenet import cut_mesh_locator

    if not cmds.pluginInfo("aru_retopo_guide_plugin", query=True, loaded=True):
        raise RuntimeError("aru_retopo_guide_plugin が読み込まれていません。")

    clear(name)
    xform = cmds.createNode("transform", name=name)
    shape = cmds.createNode(cut_mesh_locator.CutMeshLocator.kNodeName,
                            name="%sShape" % name, parent=xform)
    cmds.setAttr("%s.deformer" % shape, dfm, type="string")
    cmds.setAttr("%s.mode" % shape, MODES.index(mode))
    cmds.setAttr("%s.shrink" % shape, float(shrink))
    cmds.setAttr("%s.live" % shape, bool(live))

    if not cmds.objExists(DEBUG_GROUP):
        cmds.group(empty=True, name=DEBUG_GROUP)
    xform = cmds.parent(xform, DEBUG_GROUP)[0]

    _log.info("[cut mesh] %s: locator=%s mode=%s", dfm, xform, mode)
    try:
        print(report(dfm))
    except UnicodeEncodeError:
        # batch モードの cp932 コンソールでは記号が化けることがある
        pass
    return xform


def clear(name: str = "cutMeshDebug") -> None:
    """デバッグ表示を削除する。

    Parameters
    ----------
    name : str
        トランスフォーム名。
    """
    from Aru_RetopoTool.editor.curvenet import cut_mesh_locator

    for pat in ("%s*" % name, "cutMeshStraddle*"):
        for n in (cmds.ls(pat, type="transform", long=True) or []):
            if cmds.objExists(n):
                cmds.delete(n)
    cut_mesh_locator.invalidate()
    if cmds.objExists(DEBUG_GROUP):
        if not (cmds.listRelatives(DEBUG_GROUP, children=True) or []):
            cmds.delete(DEBUG_GROUP)


def select_straddling_faces(deformer: Optional[str] = None) -> int:
    """カーブを跨いでいるカットフェイスの位置にロケータを立てる。

    カットメッシュはロケータ描画でコンポーネントを持たないため、該当フェイス
    の中心にロケータを作って選択する。短絡箇所を直接目で確認できる。

    Parameters
    ----------
    deformer : str | None
        デフォーマ名。

    Returns
    -------
    int
        マークしたフェイス数。
    """
    dfm, bd = load_bind_data(deformer)
    cv_pos = np.asarray(bd.cv_positions, dtype=float)
    strad = find_straddling_faces(bd)

    for n in (cmds.ls("cutMeshStraddle*", type="transform", long=True) or []):
        if cmds.objExists(n):
            cmds.delete(n)
    if not strad:
        cmds.select(clear=True)
        print("[cut mesh] %s: カーブを跨ぐフェイスはありません。" % dfm)
        return 0

    if not cmds.objExists(DEBUG_GROUP):
        cmds.group(empty=True, name=DEBUG_GROUP)

    made = []
    for fi, ci in strad:
        ctr = cv_pos[bd.face_loops[fi]].mean(axis=0)
        loc = cmds.spaceLocator(name="cutMeshStraddle_f%d_c%d" % (fi, ci))[0]
        cmds.xform(loc, translation=[float(v) for v in ctr], worldSpace=True)
        made.append(cmds.parent(loc, DEBUG_GROUP)[0])

    cmds.select(made, replace=True)
    print("[cut mesh] %s: %d 個の短絡フェイスをマークしました。"
          % (dfm, len(made)))
    return len(made)
