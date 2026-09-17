# -*- coding: utf-8 -*-
"""
RetopoGuide Node -- MPxSurfaceShape + GeomIterator + ShapeUI (API 1.0)
====================================================================
"""

from __future__ import annotations

import json as _json
import sys
import time

import maya.OpenMaya as om1
import maya.OpenMayaMPx as ompx
import maya.OpenMayaUI as omui1

import maya.api.OpenMaya as om2
import maya.api.OpenMayaRender as omr

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet import sculpt_pose as _sp

from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import (
    kPluginNodeName, kPluginNodeId,
    kDrawDbClassification, kDrawRegistrantId,
    _ctx,
)
import maya.cmds as cmds


# ======================================================================
# EP CP → Handle parallel translation (shared helper)
# ======================================================================

def _translate_handles_by_ep_cp(positions, splines, ep_set, ep_cp_deltas):
    """EP の CP デルタ（手動移動分）を紐づくハンドルに平行移動で伝播する。

    skinCluster ありの場合、ジョイント回転によるハンドル追従は inSurface に
    含まれるが、ユーザーが EP を CP 経由で手動移動した分は skinCluster を
    通らないためハンドルに反映されない。この関数がその差分を補う。

    positions     : list[[x,y,z]] — インプレース更新される
    splines       : list[(ep0, h0, h1, ep1)]
    ep_set        : set of EP indices
    ep_cp_deltas  : dict {ep_idx: [dx,dy,dz]} — EP の CP デルタ (envelope 済み)
    """
    if not ep_cp_deltas:
        return

    # EP → ハンドルのマッピングを構築
    # 各ハンドルは「自分の親 EP」のデルタで平行移動する
    for sp in splines:
        if len(sp) < 4:
            continue
        ep0, h0, h1, ep1 = sp[0], sp[1], sp[2], sp[3]

        # h0 は ep0 の子ハンドル
        if ep0 in ep_cp_deltas and h0 < len(positions):
            dd = ep_cp_deltas[ep0]
            positions[h0][0] += dd[0]
            positions[h0][1] += dd[1]
            positions[h0][2] += dd[2]

        # h1 は ep1 の子ハンドル
        if ep1 in ep_cp_deltas and h1 < len(positions):
            dd = ep_cp_deltas[ep1]
            positions[h1][0] += dd[0]
            positions[h1][1] += dd[1]
            positions[h1][2] += dd[2]


# ======================================================================
# EP → Handle rotation-aware propagation (shared helper)
# ======================================================================

def _propagate_handles(positions, base_positions, splines, ep_set, all_deltas,
                       handle_user_offsets=None):
    """EP の移動から、対応するハンドルの位置をタンジェント回転で伝播する。

    各スプラインの rest/posed タンジェント方向の変化（最小回転）を Rodrigues の
    回転公式で計算し、EP→ハンドルの rest オフセットに適用することで
    ハンドル位置を自動更新する。

    EP→ハンドルのオフセットはタンジェント方向成分と垂直方向成分に分解される。
    タンジェント成分には回転に加えてスプライン伸縮率（posed_len / rest_len）の
    スケールも適用され、垂直成分は回転のみ（スケールなし）で変換される。
    これにより谷折り/山折りが自然に再現される。

    rest タンジェントまたは posed タンジェントの長さがゼロの場合（縮退ケース）は、
    EP の平行移動デルタのみを rest ハンドル位置に加算するフォールバックを行う。

    handle_user_offsets が与えられた場合、ユーザーの手動オフセット（rest 空間）を
    同じ回転行列 R で変換して自動計算位置に加算する。
    縮退ケースではユーザーオフセットは回転せずそのまま加算する。
    これにより EP を動かしてもハンドルの手動編集が自然に保持される。

    positions      : list[[x,y,z]] — EP は deformed 位置が設定済み。
                     ハンドルはインプレースで上書きされる。
    base_positions : list[[x,y,z]] — rest ポーズ (読み取りのみ)
    splines        : list[(ep0, h0, h1, ep1)] — スプライン定義。各要素は
                     ep0: 始端 EP インデックス, h0: ep0 側ハンドルインデックス,
                     h1: ep1 側ハンドルインデックス, ep1: 終端 EP インデックス。
    ep_set         : set of EP indices — EP として扱うインデックスの集合
    all_deltas     : dict {idx: [dx,dy,dz]} — 動いた CP のデルタ (EP のみ参照)
    handle_user_offsets : dict {h_idx: [dx,dy,dz]} — ハンドルの手動 CP デルタ
                         (rest 空間)。指定時は回転変換して自動位置に加算する。

    positions はインプレース更新される。
    """
    import math

    moved_eps = {idx for idx in all_deltas if idx in ep_set}
    if not moved_eps:
        return

    def _min_rotation_matrix(src, dst):
        """src ベクトルを dst ベクトルに写す最小回転行列 (3x3) を返す。

        Rodrigues の回転公式を使用。
        src, dst は正規化済みの単位ベクトル。
        """
        # cross product
        cx = src[1]*dst[2] - src[2]*dst[1]
        cy = src[2]*dst[0] - src[0]*dst[2]
        cz = src[0]*dst[1] - src[1]*dst[0]
        sin_a = math.sqrt(cx*cx + cy*cy + cz*cz)
        cos_a = src[0]*dst[0] + src[1]*dst[1] + src[2]*dst[2]

        if sin_a < 1e-12:
            # ほぼ同じ方向 → 単位行列、または180度反転
            if cos_a > 0:
                return [[1,0,0],[0,1,0],[0,0,1]]
            else:
                # 180度反転: 任意の垂直軸で回転
                # 最も小さい成分を探して外積で軸を作る
                ax = [abs(src[0]), abs(src[1]), abs(src[2])]
                mi = ax.index(min(ax))
                perp = [0.0, 0.0, 0.0]
                perp[mi] = 1.0
                # src × perp
                ux = src[1]*perp[2] - src[2]*perp[1]
                uy = src[2]*perp[0] - src[0]*perp[2]
                uz = src[0]*perp[1] - src[1]*perp[0]
                ul = math.sqrt(ux*ux + uy*uy + uz*uz)
                ux /= ul; uy /= ul; uz /= ul
                # R = 2*u*u^T - I
                return [
                    [2*ux*ux - 1, 2*ux*uy,     2*ux*uz],
                    [2*uy*ux,     2*uy*uy - 1,  2*uy*uz],
                    [2*uz*ux,     2*uz*uy,      2*uz*uz - 1],
                ]

        # 正規化された回転軸
        kx = cx / sin_a
        ky = cy / sin_a
        kz = cz / sin_a

        # Rodrigues: R = I + sin(a)*K + (1-cos(a))*K^2
        # K = skew-symmetric matrix of (kx, ky, kz)
        K = [[0, -kz, ky], [kz, 0, -kx], [-ky, kx, 0]]
        K2 = [[0.0]*3 for _ in range(3)]
        for r in range(3):
            for c in range(3):
                for m in range(3):
                    K2[r][c] += K[r][m] * K[m][c]

        R = [[0.0]*3 for _ in range(3)]
        for r in range(3):
            for c in range(3):
                R[r][c] = (1.0 if r == c else 0.0) + sin_a * K[r][c] + (1.0 - cos_a) * K2[r][c]
        return R

    if handle_user_offsets is None:
        handle_user_offsets = {}

    for sp in splines:
        if len(sp) < 4:
            continue
        ep0, h0, h1, ep1 = sp[0], sp[1], sp[2], sp[3]

        for ep_idx, h_idx, other_ep in ((ep0, h0, ep1), (ep1, h1, ep0)):
            if ep_idx not in moved_eps:
                continue
            if h_idx >= len(positions) or other_ep >= len(positions):
                continue

            # rest タンジェント: ep → other_ep
            rest_t = [base_positions[other_ep][k] - base_positions[ep_idx][k]
                      for k in range(3)]
            rest_len = math.sqrt(sum(x*x for x in rest_t))
            if rest_len < 1e-12:
                dd = all_deltas[ep_idx]
                auto_pos = [base_positions[h_idx][k] + dd[k]
                            for k in range(3)]
                # ユーザーオフセットは回転できない (タンジェント方向不明)
                # → そのまま加算
                if h_idx in handle_user_offsets:
                    uo = handle_user_offsets[h_idx]
                    auto_pos = [auto_pos[k] + uo[k] for k in range(3)]
                positions[h_idx] = auto_pos
                continue

            rest_t = [x / rest_len for x in rest_t]

            # posed タンジェント: ep → other_ep (現在位置)
            posed_t = [positions[other_ep][k] - positions[ep_idx][k]
                       for k in range(3)]
            posed_len = math.sqrt(sum(x*x for x in posed_t))
            if posed_len < 1e-12:
                dd = all_deltas[ep_idx]
                auto_pos = [base_positions[h_idx][k] + dd[k]
                            for k in range(3)]
                if h_idx in handle_user_offsets:
                    uo = handle_user_offsets[h_idx]
                    auto_pos = [auto_pos[k] + uo[k] for k in range(3)]
                positions[h_idx] = auto_pos
                continue

            posed_t = [x / posed_len for x in posed_t]

            # rest → posed の最小回転
            R = _min_rotation_matrix(rest_t, posed_t)

            # タンジェント方向のスケール比も考慮
            scale = posed_len / rest_len

            # EP→ハンドルの rest オフセットを回転 + スケール
            offset = [base_positions[h_idx][k] - base_positions[ep_idx][k]
                      for k in range(3)]

            # オフセットをタンジェント成分と垂直成分に分解
            # タンジェント成分はスケール、垂直成分はスケールなし
            dot_t = sum(offset[k] * rest_t[k] for k in range(3))
            tang_part = [dot_t * rest_t[k] for k in range(3)]
            perp_part = [offset[k] - tang_part[k] for k in range(3)]

            # 回転を適用
            rot_tang = [sum(R[r][c] * tang_part[c] for c in range(3))
                        for r in range(3)]
            rot_perp = [sum(R[r][c] * perp_part[c] for c in range(3))
                        for r in range(3)]

            # タンジェント方向にスケール適用
            new_off = [rot_tang[k] * scale + rot_perp[k] for k in range(3)]

            auto_pos = [positions[ep_idx][k] + new_off[k]
                        for k in range(3)]

            # ユーザーの手動オフセットがあれば、同じ R で回転して加算
            if h_idx in handle_user_offsets:
                uo = handle_user_offsets[h_idx]
                rot_uo = [sum(R[r][c] * uo[c] for c in range(3))
                          for r in range(3)]
                auto_pos = [auto_pos[k] + rot_uo[k] for k in range(3)]

            positions[h_idx] = auto_pos


# ======================================================================
# コンポーネント削除の undo 用スナップショット置き場
# ======================================================================
# MPxSurfaceShape::deleteComponents / undeleteComponents の受け渡しは
# MDoubleArray しか使えない。カーブネットの状態は数値では表せないので
# ここに控え、控え番号 (token) だけを MDoubleArray に載せる。
# redo でもう一度 deleteComponents が呼ばれると新しい控えが積まれるため、
# 古い控えが無限に溜まらないよう上限を設けている。

_DELETE_SNAPSHOTS: dict = {}
_DELETE_SNAPSHOT_ORDER: list = []
_DELETE_SNAPSHOT_LIMIT = 64
_DELETE_SNAPSHOT_SEQ = [0]


def _push_delete_snapshot(snap):
    _DELETE_SNAPSHOT_SEQ[0] += 1
    token = _DELETE_SNAPSHOT_SEQ[0]
    _DELETE_SNAPSHOTS[token] = snap
    _DELETE_SNAPSHOT_ORDER.append(token)
    while len(_DELETE_SNAPSHOT_ORDER) > _DELETE_SNAPSHOT_LIMIT:
        _DELETE_SNAPSHOTS.pop(_DELETE_SNAPSHOT_ORDER.pop(0), None)
    return token


def _peek_delete_snapshot(token):
    """控えを取り出す。undo/redo の往復で何度も使うので消さない。"""
    return _DELETE_SNAPSHOTS.get(int(token))


# ======================================================================
# MPxGeometryIterator — コンポーネント反復子 (API 1.0)
# ======================================================================

def _count_component_elements(component):
    """MObject / MObjectArray から反復対象の要素数を数える。

    None を返した場合は「コンポーネント指定なし = ジオメトリ全体」の意味。
    """
    if component is None:
        return None
    try:
        # geometryIteratorSetup は componentList (MObjectArray) を渡す
        if isinstance(component, om1.MObjectArray):
            total = 0
            for i in range(component.length()):
                obj = component[i]
                if obj.isNull() or not obj.hasFn(
                        om1.MFn.kSingleIndexedComponent):
                    return None
                total += om1.MFnSingleIndexedComponent(obj).elementCount()
            return total if component.length() else None
        if component.isNull():
            return None
        if not component.hasFn(om1.MFn.kSingleIndexedComponent):
            return None
        return om1.MFnSingleIndexedComponent(component).elementCount()
    except Exception:
        return None


class RetopoGuideGeomIterator(ompx.MPxGeometryIterator):
    """RetopoGuideNode の制御点を反復するイテレータ (API 1.0)。"""

    def __init__(self, positions, basePositions, component, shapeObj):
        # positions: list of [x,y,z]  — final (skin + CP delta)
        # basePositions: list of [x,y,z] — base from netData (rest pose)
        # shapeObj: om1.MObject of the shape node
        self._positions = positions        # skinCluster 込みの最終位置
        self._basePositions = basePositions  # netData のベース位置 (rest)
        self._shapeObj = shapeObj
        # コンポーネント指定時の反復要素数 (None = 全点)
        self._componentCount = _count_component_elements(component)

        # skinCluster / サーフェスワープ後の位置 (controlPoints 未適用)
        # point() は skin_base + controlPoints delta を返す
        self._skinBase = list(basePositions)  # デフォルト = rest
        self._hasSurfaceBind = False  # setPoint() で使用
        try:
            fn = om1.MFnDependencyNode(shapeObj)
            # --- Path 1: サーフェスバインド (driverMesh + surfaceBindData) ---
            try:
                sbd_str = fn.findPlug("surfaceBindData", False).asString()
                dm_plug = fn.findPlug("driverMesh", False)
                if sbd_str and dm_plug.isDestination():
                    dm_obj = dm_plug.asMObject()
                    if not dm_obj.isNull():
                        dm_fn = om1.MFnMesh(dm_obj)
                        dm_pts = om1.MPointArray()
                        dm_fn.getPoints(dm_pts, om1.MSpace.kWorld)
                        if dm_pts.length() > 0:
                            driver_verts = [
                                [dm_pts[i].x, dm_pts[i].y, dm_pts[i].z]
                                for i in range(dm_pts.length())]
                            bind_data = _json.loads(sbd_str)
                            self._skinBase = RetopoGuideNode._computeSurfaceWarp(
                                basePositions, bind_data, driver_verts)
                            self._hasSurfaceBind = True
            except Exception:
                pass
            # --- Path 2: inSurface (skinCluster 後方互換) ---
            if not self._hasSurfaceBind:
                inPlug = fn.findPlug("inSurface", False)
                if inPlug.isDestination:
                    inObj = inPlug.asMObject()
                    if not inObj.isNull():
                        meshFn = om1.MFnMesh(inObj)
                        pts = om1.MPointArray()
                        meshFn.getPoints(pts, om1.MSpace.kObject)
                        if pts.length() > 0:
                            self._skinBase = [
                                [pts[i].x, pts[i].y, pts[i].z]
                                for i in range(pts.length())
                            ]
        except Exception:
            pass

        # parent ctor に最終位置 + component を渡す
        mpa = om1.MPointArray()
        for p in positions:
            mpa.append(om1.MPoint(p[0], p[1], p[2]))
        super(RetopoGuideGeomIterator, self).__init__(mpa, component)
        self.reset()

    def reset(self):
        super(RetopoGuideGeomIterator, self).reset()
        self.setMaxPoints(len(self._basePositions))

    def point(self):
        idx = self.index()
        if 0 <= idx < len(self._skinBase):
            # _skinBase (サーフェスワープ / skinCluster / rest) + CP デルタ
            # CP はプラグからライブ読みするのでドラッグ中も即座に追従する
            sb = self._skinBase[idx]
            dx, dy, dz = 0.0, 0.0, 0.0
            try:
                fn = om1.MFnDependencyNode(self._shapeObj)
                cp_plug = fn.findPlug("controlPoints", False)
                elem = cp_plug.elementByLogicalIndex(idx)
                dx = elem.child(0).asDouble()
                dy = elem.child(1).asDouble()
                dz = elem.child(2).asDouble()
            except Exception:
                pass
            return om1.MPoint(sb[0] + dx, sb[1] + dy, sb[2] + dz)
        return om1.MPoint()

    def setPoint(self, pt):
        idx = self.index()
        if 0 <= idx < len(self._skinBase):
            # _skinBase からのデルタを CP に格納
            sb = self._skinBase[idx]
            new_dx = pt.x - sb[0]
            new_dy = pt.y - sb[1]
            new_dz = pt.z - sb[2]
            # PSD: この編集がどのポーズで行われたかを記録する。
            # CP を書き換える *前* に呼ぶこと。後だと新しいポーズでの
            # ドラッグ量が旧ポーズのターゲットに混入する。
            _record_sculpt_pose(self._shapeObj, [idx])
            try:
                fn = om1.MFnDependencyNode(self._shapeObj)
                cp_plug = fn.findPlug("controlPoints", False)
                elem = cp_plug.elementByLogicalIndex(idx)
                elem.child(0).setDouble(new_dx)
                elem.child(1).setDouble(new_dy)
                elem.child(2).setDouble(new_dz)
            except Exception:
                pass

    def iteratorCount(self):
        """反復対象の点数。

        MPxGeometryIterator の規約では「コンポーネント指定があればその要素数、
        なければジオメトリ全体の点数」を返す。常に全点数を返すと
        MItGeometry.count() が実際の反復数と食い違う。
        """
        if self._componentCount is not None:
            return self._componentCount
        return len(self._basePositions)

    def maxPoints(self):
        return len(self._basePositions)


# ======================================================================
# Sculpt envelope helper
# ======================================================================
SCULPT_FALLOFF_FRACTION = 0.35


def _compute_sculpt_envelopes(base_positions, deformed_positions,
                              ref_fraction=None):
    """CV ごとのポーズ依存スカルプトのエンベロープ (0..1) を返す。

    バインドポーズ (スキン変位ゼロ) で 0.0、``ref_fraction`` × バウンディング
    ボックス対角ぶん変位したところで 1.0 になり、その間を smoothstep で
    なめらかにつなぐ。

    CV ごとに評価するのが重要。全体の max を使うと、
      * 腕を動かしただけで脚のスカルプトまで一斉に効いてしまう
      * どこか 1 点が動いた瞬間に全体が 0 → 1 に飛ぶ
    という 2 つの問題が起きる。自分自身の変位で判定すればどちらも起きず、
    スキン変位はカーブに沿ってなめらかに変化するのでエンベロープも
    なめらかにつながる。
    """
    n = min(len(base_positions), len(deformed_positions))
    if n <= 0:
        return []

    frac = (SCULPT_FALLOFF_FRACTION if ref_fraction is None
            else float(ref_fraction))
    if frac <= 0.0:
        # 0 以下はフェード無効 (常に全効き)
        return [1.0] * n

    lo = [1e30, 1e30, 1e30]
    hi = [-1e30, -1e30, -1e30]
    for p in base_positions:
        for k in range(3):
            if p[k] < lo[k]:
                lo[k] = p[k]
            if p[k] > hi[k]:
                hi[k] = p[k]
    diag = ((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2
            + (hi[2] - lo[2]) ** 2) ** 0.5
    ref = max(diag * frac, 1e-4)

    out = []
    for i in range(n):
        dx = deformed_positions[i][0] - base_positions[i][0]
        dy = deformed_positions[i][1] - base_positions[i][1]
        dz = deformed_positions[i][2] - base_positions[i][2]
        s = (dx * dx + dy * dy + dz * dz) ** 0.5 / ref
        if s >= 1.0:
            out.append(1.0)
        elif s <= 0.0:
            out.append(0.0)
        else:
            out.append(s * s * (3.0 - 2.0 * s))
    return out


def _envelope_at(envelopes, idx):
    """``_compute_sculpt_envelopes`` の結果を範囲外に強い形で引く。"""
    if not envelopes:
        return 0.0
    if idx < 0 or idx >= len(envelopes):
        return 0.0
    return envelopes[idx]


def _compute_sculpt_envelope(base_positions, deformed_positions,
                             ref_fraction=None):
    """代表エンベロープ (全 CV の最大値)。後方互換用。"""
    env = _compute_sculpt_envelopes(base_positions, deformed_positions,
                                    ref_fraction)
    return max(env) if env else 0.0


# ======================================================================
# Pose-space sculpt (PSD) — 論文 §3「リギング」
# ======================================================================
# カーブネットの CV は「点数の少ない普通のジオメトリ」であり、その補正
# スカルプトは普通のポーズスペースデフォームとして振る舞うべきである。
# スカルプト時の CV 局所回転を sculptPose に記録し、評価時の回転との
# 近さで重みを決め、オフセット自体もフレームに追従させる。
# 詳細は curvenet/sculpt_pose.py を参照。
def _deformed_positions_from_plug(dep_fn, count):
    """``inSurface`` から変形後の CV 位置を読む (デフォーマ無しなら None)。"""
    try:
        plug = dep_fn.findPlug("inSurface", False)
        dest = plug.isDestination
        if not (dest() if callable(dest) else dest):
            return None
        obj = plug.asMObject()
        if obj.isNull():
            return None
        pts = om1.MPointArray()
        om1.MFnMesh(obj).getPoints(pts, om1.MSpace.kObject)
        if pts.length() <= 0:
            return None
        return [[pts[i].x, pts[i].y, pts[i].z]
                for i in range(min(pts.length(), count))]
    except Exception:
        return None


# 補正のポーズ依存化は Maya 標準の blendShape に一本化した
# (blend_target.create_blend_target)。CV を触るたびに暗黙にポーズが
# 増えていく挙動をやめるため、自動記録は既定で無効。
AUTO_POSE_RECORD = False


# MPxSurfaceShape の頂点キャッシュモード (MVertexCachingMode)。
# transformUsing / tweakUsing に cachingMode として渡ってくる。
# ビューポートのドラッグは kSavePoints → kUpdatePoints の連続で来て、
# undo は kRestorePoints で来る。
_kNoPointCaching = 0
_kSavePoints = 1
_kRestorePoints = 2
_kUpdatePoints = 3


def _tweak_get(builder, idx):
    """tweak 配列の要素を ``[x, y, z]`` で読む (無ければ 0)。"""
    h = builder.addElement(idx)
    for getter in ("asDouble3", "asFloat3"):
        try:
            v = getattr(h, getter)()
            return [float(v[0]), float(v[1]), float(v[2])]
        except Exception:
            continue
    return [0.0, 0.0, 0.0]


def _tweak_set(builder, idx, x, y, z):
    """tweak 配列の要素へ書く。"""
    h = builder.addElement(idx)
    for setter in ("set3Double", "set3Float"):
        try:
            getattr(h, setter)(float(x), float(y), float(z))
            return True
        except Exception:
            continue
    return False


def _record_sculpt_pose(shape_obj, indices):
    """CP を編集した「今のポーズ」を ``sculptPose`` に記録する (無効化済み)。

    以前は CV を触るたびにポーズを暗黙に記録し、独自 PSD で補正を
    ポーズ依存にしていた。しかしこの方式ではアーティストの意図しない
    ターゲットが際限なく増えてしまう。

    現在はポーズ依存化を Maya 標準の blendShape に一本化しているため
    (``blend_target.create_blend_target()``)、``AUTO_POSE_RECORD`` が
    False の間このフックは何もしない。属性自体は旧シーンを読み込める
    ように残してある。
    """
    if not AUTO_POSE_RECORD:
        return
    if not indices:
        return
    try:
        fn = om1.MFnDependencyNode(shape_obj)
        raw = fn.findPlug("netData", False).asString()
        if not raw:
            return
        cn = RetopoGuideData.from_json(raw)
        base = cn.positions
        if not base:
            return
        deformed = _deformed_positions_from_plug(fn, len(base))
        if deformed is None:
            return
        rots = _sp.compute_cv_rotations(base, deformed, cn.splines)
        pose_plug = fn.findPlug("sculptPose", False)
        cp_plug = fn.findPlug("controlPoints", False)
        targets = _read_sculpt_targets(fn)
        pose_map = _read_sculpt_pose_map(fn)
        falloff = _plug_double(fn, "poseFalloff", _sp.POSE_FALLOFF_DEFAULT)
        dirty = False

        for idx in sorted(set(indices)):
            if idx < 0 or idx >= len(rots):
                continue
            q = _sp._matrix_to_rotvec(rots[idx])
            q_old = pose_map.get(idx)
            d = _cp_value(cp_plug, idx)
            # 別ポーズへ移った状態で編集が残っている → 前の編集を確定する。
            # こうしないと 1 CV につき 1 ポーズしか保持できない。
            if (q_old is not None and d is not None
                    and _sp._length(d) > 1.0e-9
                    and _sp._length(_sp._sub(list(q), list(q_old)))
                    > _sp.POSE_MERGE_TOL):
                stored = _sp.unpack_targets(targets.get(idx))
                e = _sp.pending_target(q_old, d, stored, falloff)
                targets[idx] = _sp.pack_targets(
                    _sp.commit_target(stored, list(q_old), e))
                _cp_zero(cp_plug, idx)
                dirty = True
            elem = pose_plug.elementByLogicalIndex(idx)
            elem.child(0).setDouble(q[0])
            elem.child(1).setDouble(q[1])
            elem.child(2).setDouble(q[2])

        if dirty:
            _write_sculpt_targets(fn, targets)
    except Exception:
        pass

def _read_sculpt_targets(dep_fn):
    """``sculptTargets`` (JSON) から {idx: [[q,e], ...]} を読む。"""
    try:
        raw = dep_fn.findPlug("sculptTargets", False).asString()
        if not raw:
            return {}
        return {int(k): v for k, v in _json.loads(raw).items()}
    except Exception:
        return {}


def _write_sculpt_targets(dep_fn, data):
    """``sculptTargets`` へ JSON を書き戻す。"""
    try:
        payload = {str(k): v for k, v in data.items() if v}
        dep_fn.findPlug("sculptTargets", False).setString(
            _json.dumps(payload, separators=(",", ":")))
        return True
    except Exception:
        return False


def _cp_value(cp_plug, idx):
    """``controlPoints[idx]`` を読む (無ければ None)。"""
    try:
        elem = cp_plug.elementByLogicalIndex(idx)
        return [elem.child(0).asDouble(),
                elem.child(1).asDouble(),
                elem.child(2).asDouble()]
    except Exception:
        return None


def _cp_zero(cp_plug, idx):
    """``controlPoints[idx]`` をゼロにする。"""
    try:
        elem = cp_plug.elementByLogicalIndex(idx)
        for c in range(3):
            elem.child(c).setDouble(0.0)
        return True
    except Exception:
        return False


def _plug_double(dep_fn, name, default):
    """MFnDependencyNode (API 1.0 / 2.0 どちらでも) から double を読む。"""
    try:
        return dep_fn.findPlug(name, False).asDouble()
    except Exception:
        return default


def _is_array_plug(plug):
    """``isArray`` は API 1.0 ではメソッド、2.0 ではプロパティ。"""
    a = plug.isArray
    return a() if callable(a) else a


def _read_sculpt_pose_map(dep_fn):
    """``sculptPose`` から {idx: (qx, qy, qz)} を読む。

    compute / 選択 / VP2 描画 の 3 経路から呼ばれ、前二者は API 1.0、
    後者は API 2.0 の MFnDependencyNode を渡してくるので両対応する。
    """
    out = {}
    try:
        plug = dep_fn.findPlug("sculptPose", False)
        if not _is_array_plug(plug):
            return out
        for pi in range(plug.evaluateNumElements()):
            elem = plug.elementByPhysicalIndex(pi)
            out[elem.logicalIndex()] = (elem.child(0).asDouble(),
                                        elem.child(1).asDouble(),
                                        elem.child(2).asDouble())
    except Exception:
        pass
    return out


def _apply_sculpt(base_positions, deformed_positions, splines,
                  delta_map, pose_map, pose_falloff, legacy_fraction,
                  target_map=None):
    """スカルプトオフセットを求める共通入口 (compute/manip/VP2 で共有)。

    補正のポーズ依存化は Maya 標準の blendShape に委ねる
    (``blend_target.create_blend_target()``)。したがってここでの
    ``controlPoints`` は「ターゲットに確定する前の作業バッファ」であり、
    ポーズ重みを掛けずに 1:1 で適用する。こうしないと
    「ドラッグした場所に CV が来ない」という状態になる。

    ``sculptTargets`` は旧シーン互換のため読み取り専用で評価し続ける
    (新規記録は ``AUTO_POSE_RECORD`` で停止済み)。
    """
    delta_map = delta_map or {}
    target_map = target_map or {}
    out = {}
    if target_map:
        try:
            out = _sp.sculpt_offsets(
                base_positions, deformed_positions, splines,
                {}, {}, pose_falloff, legacy_fraction, target_map)
        except Exception:
            out = {}
    for idx, d in delta_map.items():
        prev = out.get(idx)
        if prev is None:
            out[idx] = [d[0], d[1], d[2]]
        else:
            out[idx] = [prev[0] + d[0], prev[1] + d[1], prev[2] + d[2]]
    return out

# ======================================================================
# RetopoGuideNode — MPxSurfaceShape (API 1.0)
# ======================================================================

# API 1.0 用 MTypeId (int で直接指定)
_kNodeIdInt = 0x00131AD2


class RetopoGuideNode(ompx.MPxSurfaceShape):
    """カーブネットデータを保持する MPxSurfaceShape (API 1.0)。

    データモデル (Pixar §3 準拠):
      * ``netData`` (JSON) — **レスト形状**。bind_skin() 前に
        bake_control_points() で CP を焼き込むため、バインド後は不変。
      * ``controlPoints`` (inherited) — **ポーズ依存のスカルプト補正**。
        スキンバインド後は skin displacement envelope でスケールされ、
        バインドポーズ (envelope=0) では効果がゼロになり元のレスト形状に戻る。
        バインド前は従来どおり直接適用 (レスト編集)。
      * ``cachedSurface`` — 純粋な netData 位置のみ (**CP を含まない**)。
        skinCluster はこの純粋レスト形状を変形する。

    * ``transformUsing()`` が API 1.0 では正しく C++ → Python に
      仮想ディスパッチされるため、移動ツールが動作する。
    """
    kNodeId   = om1.MTypeId(_kNodeIdInt)
    kNodeName = kPluginNodeName

    aNetData    = om1.MObject()
    aMeshName   = om1.MObject()
    aOutNetData = om1.MObject()
    aOutPositions = om1.MObject()
    aEditPreviewPositions = om1.MObject()

    # サーフェス追従 (Pixar 2023 Talks §3)
    aDriverMesh      = om1.MObject()   # deformed target mesh input
    aSurfaceBindData = om1.MObject()   # JSON: per-CV binding info

    # デフォーマチェーン (kMesh triangle-fan) — skinCluster 対応 (後方互換)
    aInSurface     = om1.MObject()
    aOutSurface    = om1.MObject()
    aCachedSurface = om1.MObject()
    aWorldSurface  = om1.MObject()

    # 描画オプション
    aXray             = om1.MObject()   # メッシュに隠れず手前に描画する
    aXrayDepthPriority = om1.MObject()  # 手前に出す強さ
    aCurveColor       = om1.MObject()
    aCurveWidth       = om1.MObject()
    aPointSize        = om1.MObject()
    aHandleSize       = om1.MObject()
    aHandleColor      = om1.MObject()
    aShowHandles      = om1.MObject()
    aSculptFalloff    = om1.MObject()   # ポーズ依存スカルプトのフェード幅
    aSculptPose       = om1.MObject()   # スカルプト時の CV 局所回転 (PSD)
    aSculptPoseX      = om1.MObject()
    aSculptPoseY      = om1.MObject()
    aSculptPoseZ      = om1.MObject()
    aSculptTargets    = om1.MObject()   # 多ポーズ補正 (JSON)
    aPoseFalloff      = om1.MObject()   # ポーズ空間の横ずれ許容量

    # inherited attribute objects — set in postConstructor
    _aCp  = om1.MObject()
    _aCpX = om1.MObject()
    _aCpY = om1.MObject()
    _aCpZ = om1.MObject()

    def __init__(self):
        ompx.MPxSurfaceShape.__init__(self)
        self._computing = False  # re-entrancy guard
    @staticmethod
    def creator():
        return ompx.asMPxPtr(RetopoGuideNode())

    @staticmethod
    def initialize():
        tAttr = om1.MFnTypedAttribute()

        # netData — トポロジ + ベース位置 (JSON)
        RetopoGuideNode.aNetData = tAttr.create(
            "netData", "nd", om1.MFnData.kString)
        tAttr.setStorable(True)
        tAttr.setWritable(True)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aNetData)

        # meshName — 参照メッシュ名
        RetopoGuideNode.aMeshName = tAttr.create(
            "meshName", "mn", om1.MFnData.kString)
        tAttr.setStorable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aMeshName)

        # outNetData — 最終位置 JSON 出力
        RetopoGuideNode.aOutNetData = tAttr.create(
            "outNetData", "ond", om1.MFnData.kString)
        tAttr.setStorable(False)
        tAttr.setWritable(False)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aOutNetData)
        RetopoGuideNode.aOutPositions = tAttr.create(
            "outPositions", "opos", om1.MFnData.kDoubleArray)
        tAttr.setStorable(False)
        tAttr.setWritable(False)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aOutPositions)

        # Absolute object-space positions for an in-progress numeric edit.
        # Empty means inactive. A context must commit or clear before ending.
        RetopoGuideNode.aEditPreviewPositions = tAttr.create(
            "editPreviewPositions", "epp", om1.MFnData.kDoubleArray)
        tAttr.setStorable(False)
        tAttr.setWritable(True)
        tAttr.setReadable(True)
        tAttr.setHidden(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aEditPreviewPositions)
        for target in (RetopoGuideNode.aOutPositions, RetopoGuideNode.aOutNetData):
            RetopoGuideNode.attributeAffects(RetopoGuideNode.aEditPreviewPositions, target)


        # dirty 伝播
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aNetData, RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aNetData, RetopoGuideNode.aOutPositions)

        # --- サーフェス追従 (Pixar 2023 Talks §3) ---
        # driverMesh: 変形済みターゲットメッシュ (worldMesh[0] に接続)
        RetopoGuideNode.aDriverMesh = tAttr.create(
            "driverMesh", "dm", om1.MFnData.kMesh)
        tAttr.setStorable(False)
        tAttr.setWritable(True)
        tAttr.setReadable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aDriverMesh)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aDriverMesh, RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aDriverMesh, RetopoGuideNode.aOutPositions)

        # surfaceBindData: JSON — per-CV binding info (face, bary, frame)
        RetopoGuideNode.aSurfaceBindData = tAttr.create(
            "surfaceBindData", "sbd", om1.MFnData.kString)
        tAttr.setStorable(True)
        tAttr.setWritable(True)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aSurfaceBindData)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aSurfaceBindData, RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aSurfaceBindData, RetopoGuideNode.aOutPositions)

        # --- デフォーマチェーン (kMesh — skinCluster 対応: 後方互換) ---
        RetopoGuideNode.aInSurface = tAttr.create(
            "inSurface", "is", om1.MFnData.kMesh)
        tAttr.setStorable(False)
        tAttr.setWritable(True)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aInSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aInSurface, RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aInSurface, RetopoGuideNode.aOutPositions)

        RetopoGuideNode.aOutSurface = tAttr.create(
            "outSurface", "os", om1.MFnData.kMesh)
        tAttr.setStorable(False)
        tAttr.setWritable(False)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aOutSurface)

        RetopoGuideNode.aCachedSurface = tAttr.create(
            "cachedSurface", "cs", om1.MFnData.kMesh)
        tAttr.setStorable(True) # <--- Origノードにデータを残すため必須
        tAttr.setWritable(True)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aCachedSurface)

        RetopoGuideNode.aWorldSurface = tAttr.create(
            "worldSurface", "ws", om1.MFnData.kMesh)
        tAttr.setArray(True)
        tAttr.setUsesArrayDataBuilder(True)
        tAttr.setStorable(False)
        tAttr.setWritable(False)
        tAttr.setReadable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aWorldSurface)

        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aNetData, RetopoGuideNode.aOutSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aNetData, RetopoGuideNode.aCachedSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aNetData, RetopoGuideNode.aWorldSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aInSurface, RetopoGuideNode.aWorldSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aCachedSurface, RetopoGuideNode.aWorldSurface)

        # driverMesh → 全出力
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aDriverMesh, RetopoGuideNode.aOutSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aDriverMesh, RetopoGuideNode.aCachedSurface)
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aDriverMesh, RetopoGuideNode.aWorldSurface)
        # surfaceBindData → outNetData
        RetopoGuideNode.attributeAffects(
            RetopoGuideNode.aSurfaceBindData, RetopoGuideNode.aOutSurface)

        # controlPoints → outNetData/outSurface は setDependentsDirty で手動処理

        # --- 描画オプション ---
        # カーブネットはメッシュ表面に張り付くため、そのまま描くとメッシュに
        # 埋もれて見えなくなる。深度優先度を上げて手前に描くと、カーブを
        # 掴んだり繋いだりする操作が格段にやりやすくなる。
        nAttr = om1.MFnNumericAttribute()
        RetopoGuideNode.aXray = nAttr.create(
            "xray", "xry", om1.MFnNumericData.kBoolean, True)
        nAttr.setStorable(True)
        nAttr.setKeyable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aXray)

        # MRenderItem.sSelectionDepthPriority (21) より少し上に置くと
        # 通常のサーフェスより確実に手前へ出る。
        RetopoGuideNode.aXrayDepthPriority = nAttr.create(
            "xrayDepthPriority", "xdp", om1.MFnNumericData.kInt, 26)
        nAttr.setMin(0)
        nAttr.setMax(64)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aXrayDepthPriority)

        # --- 見た目 (複数のカーブネットを色や太さで見分ける) ---
        RetopoGuideNode.aCurveColor = nAttr.createColor("curveColor", "ccl")
        nAttr.setDefault(0.4, 0.8, 1.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        nAttr.setUsedAsColor(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aCurveColor)

        RetopoGuideNode.aCurveWidth = nAttr.create(
            "curveWidth", "cwd", om1.MFnNumericData.kFloat, 2.0)
        nAttr.setMin(0.5)
        nAttr.setSoftMax(8.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aCurveWidth)

        RetopoGuideNode.aPointSize = nAttr.create(
            "pointSize", "psz", om1.MFnNumericData.kFloat, 8.0)
        nAttr.setMin(1.0)
        nAttr.setSoftMax(24.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aPointSize)

        RetopoGuideNode.aHandleSize = nAttr.create(
            "handleSize", "hsz", om1.MFnNumericData.kFloat, 6.0)
        nAttr.setMin(1.0)
        nAttr.setSoftMax(24.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aHandleSize)

        RetopoGuideNode.aHandleColor = nAttr.createColor("handleColor", "hcl")
        nAttr.setDefault(0.3, 0.85, 0.85)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        nAttr.setUsedAsColor(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aHandleColor)

        # ハンドルとタンジェント線はリグで使うときには邪魔なので隠せる
        RetopoGuideNode.aShowHandles = nAttr.create(
            "showHandles", "shh", om1.MFnNumericData.kBoolean, True)
        nAttr.setStorable(True)
        nAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aShowHandles)

        # --- ポーズ依存スカルプトのフェード ---
        # CP 編集はポーズ依存の補正なので、バインドポーズに戻ると消える。
        # その消え方をどれだけの変位で完了させるかをバウンディングボックス
        # 対角に対する割合で指定する。小さすぎると 0/1 のスイッチのように
        # 感じられるので既定は 20%。0 でフェード無効 (常に全効き)。
        RetopoGuideNode.aSculptFalloff = nAttr.create(
            "sculptFalloff", "scf", om1.MFnNumericData.kDouble,
            SCULPT_FALLOFF_FRACTION)
        nAttr.setMin(0.0)
        nAttr.setSoftMax(1.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aSculptFalloff)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptFalloff,
                                      RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptFalloff,
                                      RetopoGuideNode.aOutPositions)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptFalloff,
                                      RetopoGuideNode.aOutSurface)

        # --- ポーズスペーススカルプト (PSD) ---
        # sculptPose: CP を編集したときの CV 局所回転ベクトル。
        # controlPoints と同じインデックスで対になる。
        RetopoGuideNode.aSculptPoseX = nAttr.create(
            "sculptPoseX", "spx", om1.MFnNumericData.kDouble, 0.0)
        RetopoGuideNode.aSculptPoseY = nAttr.create(
            "sculptPoseY", "spy", om1.MFnNumericData.kDouble, 0.0)
        RetopoGuideNode.aSculptPoseZ = nAttr.create(
            "sculptPoseZ", "spz", om1.MFnNumericData.kDouble, 0.0)
        cAttr = om1.MFnCompoundAttribute()
        RetopoGuideNode.aSculptPose = cAttr.create("sculptPose", "spo")
        cAttr.addChild(RetopoGuideNode.aSculptPoseX)
        cAttr.addChild(RetopoGuideNode.aSculptPoseY)
        cAttr.addChild(RetopoGuideNode.aSculptPoseZ)
        cAttr.setArray(True)
        cAttr.setUsesArrayDataBuilder(True)
        cAttr.setStorable(True)
        cAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aSculptPose)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptPose,
                                      RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptPose,
                                      RetopoGuideNode.aOutPositions)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptPose,
                                      RetopoGuideNode.aOutSurface)

        # sculptTargets: JSON — 1 CV に複数ポーズの補正を保持する。
        # {cv_index: [[qx,qy,qz,ex,ey,ez], ...]}
        # q は記録時の CV 局所回転ベクトル、e はローカルフレームでの
        # オフセット。アニメーションでは 1 ポーズでは足りないため、
        # 論文 §3 が委ねる「補正ブレンドシェープ」に相当する多ターゲットを
        # ここで保持する。
        RetopoGuideNode.aSculptTargets = tAttr.create(
            "sculptTargets", "stg", om1.MFnData.kString)
        tAttr.setStorable(True)
        tAttr.setKeyable(False)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aSculptTargets)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptTargets,
                                      RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptTargets,
                                      RetopoGuideNode.aOutPositions)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aSculptTargets,
                                      RetopoGuideNode.aOutSurface)

        # poseFalloff: スカルプトしたポーズからどれだけ横にずれたら
        # 補正を消すか (|q| に対する比)。小さいほどポーズに敏感。
        RetopoGuideNode.aPoseFalloff = nAttr.create(
            "poseFalloff", "pof", om1.MFnNumericData.kDouble,
            _sp.POSE_FALLOFF_DEFAULT)
        nAttr.setMin(0.0)
        nAttr.setSoftMax(2.0)
        nAttr.setStorable(True)
        nAttr.setKeyable(True)
        RetopoGuideNode.addAttribute(RetopoGuideNode.aPoseFalloff)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aPoseFalloff,
                                      RetopoGuideNode.aOutNetData)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aPoseFalloff,
                                      RetopoGuideNode.aOutPositions)
        RetopoGuideNode.attributeAffects(RetopoGuideNode.aPoseFalloff,
                                      RetopoGuideNode.aOutSurface)

        # worldSurface も outSurface と同じ最終形状 (デフォーマ + tweak)
        # を返すようになったので、形状に影響する入力はすべて
        # worldSurface にも伝播させる。ここが漏れると blendShape が
        # 古い形状を読んでターゲットの差分がずれる。
        for _src in (RetopoGuideNode.aSculptFalloff, RetopoGuideNode.aSculptPose,
                     RetopoGuideNode.aSculptTargets, RetopoGuideNode.aPoseFalloff,
                     RetopoGuideNode.aSurfaceBindData):
            RetopoGuideNode.attributeAffects(_src, RetopoGuideNode.aWorldSurface)

        for target in (RetopoGuideNode.aOutSurface, RetopoGuideNode.aWorldSurface):
            RetopoGuideNode.attributeAffects(RetopoGuideNode.aEditPreviewPositions, target)

    # クラス属性名 → Maya 属性名。initialize() が走らない状況 (プラグインが
    # アンロードできないままモジュールだけ reload された等) で
    # クラス属性を既存ノードから復元するために使う。
    _ATTR_NAMES = {
        "aNetData": "netData", "aMeshName": "meshName",
        "aEditPreviewPositions": "editPreviewPositions",
        "aOutPositions": "outPositions", "aOutNetData": "outNetData", "aDriverMesh": "driverMesh",
        "aSurfaceBindData": "surfaceBindData", "aInSurface": "inSurface",
        "aOutSurface": "outSurface", "aCachedSurface": "cachedSurface",
        "aWorldSurface": "worldSurface", "aXray": "xray",
        "aXrayDepthPriority": "xrayDepthPriority",
        "aCurveColor": "curveColor", "aCurveWidth": "curveWidth",
        "aPointSize": "pointSize", "aHandleSize": "handleSize",
        "aHandleColor": "handleColor", "aShowHandles": "showHandles",
        "aSculptFalloff": "sculptFalloff", "aSculptPose": "sculptPose",
        "aSculptPoseX": "sculptPoseX", "aSculptPoseY": "sculptPoseY",
        "aSculptPoseZ": "sculptPoseZ", "aSculptTargets": "sculptTargets",
        "aPoseFalloff": "poseFalloff",
    }

    @classmethod
    def _restore_class_attributes(cls, fn):
        """reload で空になったクラス属性 MObject をノードから埋め直す。"""
        if not cls.aInSurface.isNull():
            return
        for cls_attr, name in cls._ATTR_NAMES.items():
            try:
                setattr(cls, cls_attr, fn.attribute(name))
            except Exception:
                pass

    def postConstructor(self):
        self.setExistWithoutInConnections(True)
        self.setExistWithoutOutConnections(True)
        # ノード作成後なら inherited attribute を取得可能
        try:
            fn = om1.MFnDependencyNode(self.thisMObject())
            RetopoGuideNode._restore_class_attributes(fn)
            RetopoGuideNode._aCp  = fn.attribute("controlPoints")
            RetopoGuideNode._aCpX = fn.attribute("xValue")
            RetopoGuideNode._aCpY = fn.attribute("yValue")
            RetopoGuideNode._aCpZ = fn.attribute("zValue")
            RetopoGuideNode.attributeAffects(
                RetopoGuideNode._aCp, RetopoGuideNode.aOutNetData)
            RetopoGuideNode.attributeAffects(
                RetopoGuideNode._aCp, RetopoGuideNode.aOutPositions)
            RetopoGuideNode.attributeAffects(
                RetopoGuideNode._aCp, RetopoGuideNode.aOutSurface)
            RetopoGuideNode.attributeAffects(
                RetopoGuideNode._aCp, RetopoGuideNode.aCachedSurface)
            RetopoGuideNode.attributeAffects(
                RetopoGuideNode._aCp, RetopoGuideNode.aWorldSurface)
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Deformer chain overrides (skinCluster 対応)
    # -----------------------------------------------------------------
    def isDeformable(self):
        return True

    def match(self, mask, componentList):
        # オブジェクト選択
        if componentList.length() == 0:
            return mask.intersects(om1.MSelectionMask.kSelectMeshes)
        # コンポーネント: kSelectCVs (VP2 選択) と kSelectMeshVerts (deformer) の両方を受容
        for i in range(componentList.length()):
            if componentList[i].apiType() == om1.MFn.kMeshVertComponent:
                if (mask.intersects(om1.MSelectionMask.kSelectCVs)
                        or mask.intersects(
                            om1.MSelectionMask.kSelectMeshVerts)):
                    return True
        return False

    def localShapeInAttr(self):
        return RetopoGuideNode.aInSurface

    def localShapeOutAttr(self):
        return RetopoGuideNode.aOutSurface

    def cachedShapeAttr(self):
        return RetopoGuideNode.aCachedSurface

    def worldShapeOutAttr(self):
        return RetopoGuideNode.aWorldSurface

    def matchTopology(self, shape, pts):
        return True

    def geometryData(self):
        """デフォーマチェーン構築時に呼ばれ、Origノードにコピーされるジオメトリを返す。

        cmds.deformer() → Orig ノード生成時に Maya が呼ぶ。
        有効な kMesh MObject を返さないと「変形可能なオブジェクトが
        選択されていません」エラーになる。

        取得優先順位:
          1. cachedSurface プラグに既に non-null なデータがある → そのまま返す
             (759650bb 互換: hasFn チェックを行わない — Maya 内部が
              kMeshData かどうかを判断するため、ここでは isNull のみ確認)
          2. netData から positions/splines を読んでメッシュを構築して返す
          3. 最終フォールバック: ダミー3頂点メッシュ
        """
        try:
            dagFn = om1.MFnDagNode(self.thisMObject())
            node_name = dagFn.name()

            if dagFn.isIntermediateObject() or node_name.endswith("Orig"):
                self._recover_netdata_if_empty(dagFn, node_name)

            # --- cachedSurface から既存データを取得 ---
            # 759650bb と同じ: isNull でないならそのまま返す。
            # hasFn / numVertices チェックを入れると cmds.deformer() の
            # 内部呼び出し時に弾かれて「変形可能ではありません」になる。
            plug = dagFn.findPlug("cachedSurface", False)
            dataObj = plug.asMObject()
            if not dataObj.isNull():
                return dataObj
        except Exception as e:
            print(f"[RetopoGuide] Error in geometryData (phase1): {e}")

        # --- フォールバック: netData からメッシュを構築 ---
        try:
            positions = self._getBasePositions()
            splines = self._getSplines()
            if positions:
                dataObj = RetopoGuideNode._buildMeshData(positions, splines)
                # 構築したメッシュを cachedSurface にもセットしておく
                # (次回の geometryData / deformer chain で再利用されるように)
                try:
                    dagFn = om1.MFnDagNode(self.thisMObject())
                    cs_plug = dagFn.findPlug("cachedSurface", False)
                    cs_plug.setMObject(dataObj)
                except Exception:
                    pass
                return dataObj
        except Exception as e:
            print(f"[RetopoGuide] Error in geometryData (phase2): {e}")

        # 最終フォールバック: 最小限のダミーメッシュ (3頂点1三角形)
        return RetopoGuideNode._buildMeshData([[0, 0, 0], [1, 0, 0], [0, 1, 0]])

    def _recover_netdata_if_empty(self, dagFn, node_name):
        """Origノード生成時にnetDataが欠落している場合、元ノードから物理的にコピーする。"""
        try:
            nd_plug = dagFn.findPlug("netData", False)
            if nd_plug.asString():
                return  # 既にデータあり
                
            # 1. 兄弟ノードからのコピーを試行
            if dagFn.parentCount() > 0:
                parent_fn = om1.MFnDagNode(dagFn.parent(0))
                for i in range(parent_fn.childCount()):
                    child_obj = parent_fn.child(i)
                    if child_obj == self.thisMObject() or not child_obj.hasFn(om1.MFn.kShape):
                        continue
                    
                    sib_val = om1.MFnDagNode(child_obj).findPlug("netData", False).asString()
                    if sib_val:
                        nd_plug.setString(sib_val)
                        return
            
            # 2. 親から取れない場合、名前一致(_Orig除去)でのコピーを試行
            if not node_name.endswith("Orig"):
                return
                
            base_name = node_name[:-4]
            import maya.cmds as cmds
            if cmds.objExists(base_name) and cmds.objectType(base_name, isType="retopoGuideNode"):
                val = cmds.getAttr(base_name + ".netData")
                if val:
                    nd_plug.setString(val)
        except Exception as e:
            pass

    # -----------------------------------------------------------------
    # compute (API 1.0)
    # -----------------------------------------------------------------
    def compute(self, plug, dataBlock):
        # Re-entrancy guard: prevent freeze from recursive evaluation
        # (e.g. marking menu → plug query → compute → plug query → ...)
        if self._computing:
            return om1.kUnknownParameter
        self._computing = True
        try:
            return self._computeInner(plug, dataBlock)
        finally:
            self._computing = False

    def _computeInner(self, plug, dataBlock):
        if plug == RetopoGuideNode.aOutNetData:
            self._computeOutNetData(dataBlock)
        elif plug == RetopoGuideNode.aOutPositions:
            self._computeOutNetData(dataBlock, positions_only=True)
        elif plug == RetopoGuideNode.aCachedSurface:
            self._computeCachedSurface(dataBlock)
        elif plug == RetopoGuideNode.aOutSurface:
            self._computeOutSurface(dataBlock)
        elif plug == RetopoGuideNode.aWorldSurface:
            self._computeWorldSurface(plug, dataBlock)
        else:
            return om1.kUnknownParameter

    # -----------------------------------------------------------------
    # _getDeformedPositions — デフォーマチェーン出力から変形位置を読む
    # -----------------------------------------------------------------
    def _hasActiveDeformer(self):
        """inSurface に実際のデフォーマが繋がっているかを判定する。

        DetachSkin (Maya 標準) は skinCluster を削除しても Orig ノードを
        残し、inSurface を ``<shape>Orig.worldSurface`` へ繋ぎ替えるだけで
        ある。inSurface にデータがあるか否かだけで判定すると、この状態を
        「デフォーマあり」と誤認して以下の不具合が出る:

          * controlPoints のスカルプトが envelope=0 で常時無効化される
            (アンバインド後にカーブネットが編集不能になる)
          * netData の編集が Orig のスナップショットで上書きされ、
            バインド時の形状に固定されたままになる

        そのため、接続元が実際に geometryFilter (skinCluster, blendShape,
        cluster, tweak など) である場合のみ「デフォーマあり」とみなす。
        接続元が中間 shape (Orig) の場合はデフォーマなしとして扱う。
        """
        try:
            plug = om1.MPlug(self.thisMObject(), RetopoGuideNode.aInSurface)
            if plug.isNull():
                return False
            srcs = om1.MPlugArray()
            plug.connectedTo(srcs, True, False)
            if srcs.length() == 0:
                return False
            return srcs[0].node().hasFn(om1.MFn.kGeometryFilt)
        except Exception:
            return False

    def _getDeformedPositions(self, dataBlock):
        """デフォーマチェーン経由で inSurface から変形後の頂点位置を返す。

        実際に geometryFilter が繋がっていない場合は None を返し、
        呼び出し側を「デフォーマなし」経路 (netData + controlPoints を
        直接適用) へ倒す。
        """
        if not self._hasActiveDeformer():
            return None
        try:
            inHandle = dataBlock.inputValue(RetopoGuideNode.aInSurface)
            inObj = inHandle.data()
            if inObj.isNull():
                return None
            meshFn = om1.MFnMesh(inObj)
            pts = om1.MPointArray()
            meshFn.getPoints(pts, om1.MSpace.kObject)
            if pts.length() > 0:
                return [[pts[i].x, pts[i].y, pts[i].z]
                        for i in range(pts.length())]
        except Exception:
            pass
        return None

    # -----------------------------------------------------------------
    # Surface-following (Pixar 2023 Talks §3)
    # -----------------------------------------------------------------
    def _getDriverMeshVerts(self, dataBlock):
        """driverMesh 属性から変形済みメッシュ頂点を読む。"""
        try:
            inHandle = dataBlock.inputValue(RetopoGuideNode.aDriverMesh)
            inObj = inHandle.data()
            if inObj.isNull():
                return None
            meshFn = om1.MFnMesh(inObj)
            pts = om1.MPointArray()
            meshFn.getPoints(pts, om1.MSpace.kWorld)
            if pts.length() > 0:
                return [[pts[i].x, pts[i].y, pts[i].z]
                        for i in range(pts.length())]
        except Exception:
            pass
        return None

    def _getSurfaceBindData(self, dataBlock):
        """surfaceBindData (JSON) をパースして返す。キャッシュ付き。"""
        try:
            s = dataBlock.inputValue(
                RetopoGuideNode.aSurfaceBindData).asString()
            if not s:
                return None
            if not hasattr(self, '_sbd_cache_str') or s != self._sbd_cache_str:
                self._sbd_cache = _json.loads(s)
                self._sbd_cache_str = s
            return self._sbd_cache
        except Exception:
            return None

    @staticmethod
    def _computeSurfaceWarp(base_positions, bind_data, driver_verts):
        """サーフェスバインドから各 CV のワープ位置を計算する。

        Pixar 2023 Talks §3:
        投影ポーズ → レストポーズへのワープ。各 CV を変形メッシュ表面上の
        重心座標で追従させ、rest offset をローカルフレーム回転で補正する。

        Parameters
        ----------
        base_positions : list[[x,y,z]] — netData の rest 位置
        bind_data : dict — surfaceBindData (parsed JSON)
        driver_verts : list[[x,y,z]] — 変形済みメッシュ頂点

        Returns
        -------
        warped : list[[x,y,z]] — ワープ後の CV 位置
        """
        import math
        warped = [list(p) for p in base_positions]
        bindings = bind_data.get("bindings", [])
        n_driver = len(driver_verts)

        for b in bindings:
            cv_idx = b["cv_idx"]
            if cv_idx >= len(warped):
                continue
            tri_v = b["tri_verts"]
            # 頂点インデックスの範囲チェック
            if any(v >= n_driver or v < 0 for v in tri_v):
                continue
            bary = b["bary"]
            rest_offset = b["rest_offset"]
            rest_N = b["rest_normal"]
            rest_T = b["rest_tangent"]
            rest_B = b["rest_binormal"]

            # 変形三角形の頂点
            v0 = driver_verts[tri_v[0]]
            v1 = driver_verts[tri_v[1]]
            v2 = driver_verts[tri_v[2]]

            # 重心補間 → ワープ先サーフェス点
            wx = bary[0]*v0[0] + bary[1]*v1[0] + bary[2]*v2[0]
            wy = bary[0]*v0[1] + bary[1]*v1[1] + bary[2]*v2[1]
            wz = bary[0]*v0[2] + bary[1]*v1[2] + bary[2]*v2[2]

            # 変形三角形のローカルフレーム
            e1 = [v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2]]
            e2 = [v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2]]
            # normal = e1 × e2
            nx = e1[1]*e2[2] - e1[2]*e2[1]
            ny = e1[2]*e2[0] - e1[0]*e2[2]
            nz = e1[0]*e2[1] - e1[1]*e2[0]
            nl = math.sqrt(nx*nx + ny*ny + nz*nz)
            if nl < 1e-12:
                warped[cv_idx] = [wx, wy, wz]
                continue
            nx /= nl; ny /= nl; nz /= nl
            # tangent = normalize(e1)
            tl = math.sqrt(e1[0]**2 + e1[1]**2 + e1[2]**2)
            if tl < 1e-12:
                warped[cv_idx] = [wx, wy, wz]
                continue
            tx = e1[0]/tl; ty = e1[1]/tl; tz = e1[2]/tl
            # binormal = normal × tangent
            bx = ny*tz - nz*ty
            by = nz*tx - nx*tz
            bz = nx*ty - ny*tx

            # offset をレストフレーム座標に変換: R_rest^T @ offset
            ox = (rest_T[0]*rest_offset[0] + rest_T[1]*rest_offset[1]
                  + rest_T[2]*rest_offset[2])
            oy = (rest_B[0]*rest_offset[0] + rest_B[1]*rest_offset[1]
                  + rest_B[2]*rest_offset[2])
            oz = (rest_N[0]*rest_offset[0] + rest_N[1]*rest_offset[1]
                  + rest_N[2]*rest_offset[2])

            # 変形フレームでワールド空間に戻す: D @ (ox, oy, oz)
            rx = tx*ox + bx*oy + nx*oz
            ry = ty*ox + by*oy + ny*oz
            rz = tz*ox + bz*oy + nz*oz

            warped[cv_idx] = [wx + rx, wy + ry, wz + rz]

        return warped

    # -----------------------------------------------------------------
    # _readControlPointDeltas
    # -----------------------------------------------------------------
    def _readControlPointDeltas(self, dataBlock):
        """controlPoints からデルタマップ {idx: [dx,dy,dz]} を読む。"""
        delta_map = {}
        if RetopoGuideNode._aCp.isNull():
            return delta_map
        try:
            cp_handle = dataBlock.inputArrayValue(RetopoGuideNode._aCp)
            count = cp_handle.elementCount()
            for pi in range(count):
                try:
                    cp_handle.jumpToArrayElement(pi)
                except Exception:
                    break
                idx = cp_handle.elementIndex()
                child = cp_handle.inputValue()
                dx = child.child(RetopoGuideNode._aCpX).asDouble()
                dy = child.child(RetopoGuideNode._aCpY).asDouble()
                dz = child.child(RetopoGuideNode._aCpZ).asDouble()
                if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                    delta_map[idx] = [dx, dy, dz]
        except Exception:
            pass
        return delta_map

    # -----------------------------------------------------------------
    # _buildMeshData — スプライン構造を反映したメッシュ構築
    # -----------------------------------------------------------------
    @staticmethod
    def _buildMeshData(positions, splines=None):
        """スプライン接続を反映した kMesh データを構築する。

        各スプライン (ep0, h0, h1, ep1) を 2 三角形 (ep0-h0-h1, ep0-h1-ep1) で
        表現することで、skinCluster が EP-Handle 間のエッジに沿って正しく
        スムース補間できるようにする。

        スプラインがないか空の場合は、最低限の triangle-fan にフォールバック
        して Maya の kMesh 要件を満たす。
        """
        meshDataFn = om1.MFnMeshData()
        dataObj = meshDataFn.create()
        n = len(positions)
        if n < 3:
            positions = list(positions)
            while len(positions) < 3:
                positions.append(
                    positions[-1] if positions else [0, 0, 0])
            n = len(positions)

        pts = om1.MPointArray()
        for p in positions:
            pts.append(om1.MPoint(p[0], p[1], p[2]))

        face_counts = om1.MIntArray()
        face_connects = om1.MIntArray()

        used_verts = set()
        if splines:
            for sp in splines:
                if len(sp) < 4:
                    continue
                i0, i1, i2, i3 = sp[0], sp[1], sp[2], sp[3]
                if any(idx >= n for idx in (i0, i1, i2, i3)):
                    continue
                # Quad (ep0, h0, h1, ep1) → 2 triangles
                # Triangle 1: ep0 - h0 - h1
                face_counts.append(3)
                face_connects.append(i0)
                face_connects.append(i1)
                face_connects.append(i2)
                # Triangle 2: ep0 - h1 - ep1
                face_counts.append(3)
                face_connects.append(i0)
                face_connects.append(i2)
                face_connects.append(i3)
                used_verts.update((i0, i1, i2, i3))

        # スプラインのない孤立頂点のために最低1フェイスを確保する
        # (Maya の skinCluster は頂点がフェイスに属していないとバインドしない)
        orphans = [i for i in range(n) if i not in used_verts]
        if orphans:
            # 孤立頂点を三角形ファンで繋ぐ
            # アンカーを最初の孤立頂点にする
            anchor = orphans[0]
            for j in range(1, len(orphans) - 1):
                face_counts.append(3)
                face_connects.append(anchor)
                face_connects.append(orphans[j])
                face_connects.append(orphans[j + 1])

        if face_counts.length() == 0:
            # フォールバック: 最低限 1 三角形
            face_counts.append(3)
            face_connects.append(0)
            face_connects.append(min(1, n - 1))
            face_connects.append(min(2, n - 1))

        meshFn = om1.MFnMesh()
        meshFn.create(n, face_counts.length(), pts,
                      face_counts, face_connects, dataObj)
        return dataObj

    # -----------------------------------------------------------------
    # _computeCachedSurface / _computeOutSurface — デフォーマチェーン
    # -----------------------------------------------------------------
    def _computeCachedSurface(self, dataBlock):
        """変形前のローカルジオメトリ (純粋な netData ベース位置) を計算。

        controlPoints は cachedSurface に含め **ない**。
        bind_skin() が事前に bake_control_points() で CP を netData に
        焼き込むため、バインド後の cachedSurface は正しい rest 形状になる。
        CP はポーズ依存の補正として outNetData / 描画側でのみスケール適用される。
        """
        # Origノードなど、作成済みメッシュがすでにセットされている場合は保護する。
        # ただし netData が書き換えられたとき (カーブネットのトポロジ編集) は
        # スキンクラスタの入力も新しい点数にならないと困るので作り直す。
        base_str = dataBlock.inputValue(RetopoGuideNode.aNetData).asString()
        try:
            oldHandle = dataBlock.outputValue(RetopoGuideNode.aCachedSurface)
            oldObj = oldHandle.data()
            if not oldObj.isNull():
                fn = om1.MFnDependencyNode(self.thisMObject())
                if fn.isIntermediateObject():
                    used = getattr(self, "_cached_net_str", None)
                    if not base_str or used is None or used == base_str:
                        if used is None and base_str:
                            self._cached_net_str = base_str
                        dataBlock.setClean(RetopoGuideNode.aCachedSurface)
                        return oldObj
        except Exception:
            pass

        positions = []
        splines = []
        if base_str:
            try:
                cn = RetopoGuideData.from_json_cached(base_str)
                positions = [list(p) for p in cn.positions]
                splines = cn.splines
            except Exception as e:
                print("Error parsing netData:", e)

        # NOTE: controlPoints は含めない — ポーズ補正は outNetData で適用

        dataObj = RetopoGuideNode._buildMeshData(positions, splines)
        handle = dataBlock.outputValue(RetopoGuideNode.aCachedSurface)
        handle.setMObject(dataObj)
        dataBlock.setClean(RetopoGuideNode.aCachedSurface)
        self._cached_net_str = base_str
        return dataObj

    def _isIntermediate(self):
        try:
            return om1.MFnDagNode(self.thisMObject()).isIntermediateObject()
        except Exception:
            return False

    def _finalPositions(self, dataBlock):
        """outNetData の最終位置 (デフォーマ + スカルプト補正) を取り出す。

        Maya の標準シェイプは「出力ジオメトリ = デフォーマチェーンの結果
        + tweak (controlPoints)」という契約になっていて、blendShape や
        sculptTarget はこの契約に乗って動く。retopoGuideNode の「実際に
        見える形状」は outNetData にあるので、それを outSurface /
        worldSurface へも流して契約を守る。

        compute() には再入ガード (_computing) があるため
        ``inputValue(aOutNetData)`` では入れ子の compute が走らず古い値が
        返る。dirty のときだけ _computeOutNetData() を直接呼ぶ。
        """
        try:
            need = True
            try:
                need = not dataBlock.isClean(RetopoGuideNode.aOutNetData)
            except Exception:
                pass
            if need:
                self._computeOutNetData(dataBlock)
            s = dataBlock.outputValue(RetopoGuideNode.aOutNetData).asString()
            if s:
                cn = RetopoGuideData.from_json_cached(s)
                return [list(p) for p in cn.positions], cn.splines
        except Exception as e:
            print("[RetopoGuide] Error in _finalPositions:", e)
        return None, None

    def _instanceMatrix(self, plug):
        """worldSurface[i] に対応するインスタンスのワールド行列。"""
        idx = 0
        try:
            if plug.isElement():
                idx = plug.logicalIndex()
        except Exception:
            idx = 0
        try:
            paths = om1.MDagPathArray()
            om1.MFnDagNode(self.thisMObject()).getAllPaths(paths)
            if paths.length() == 0:
                return None
            if idx >= paths.length():
                idx = 0
            return paths[idx].inclusiveMatrix()
        except Exception:
            return None

    def _computeOutSurface(self, dataBlock):
        """ローカル空間の最終メッシュを出力する。

        「デフォーマの結果 + controlPoints (tweak) + ハンドル追従」を
        含んだ形状を返す。これで Maya の標準シェイプと同じ契約になり、
        blendShape がこのシェイプを正しく扱えるようになる。
        """
        outHandle = dataBlock.outputValue(RetopoGuideNode.aOutSurface)

        # 中間オブジェクト (Orig) は変形前のスナップショットを保つ
        if self._isIntermediate():
            inObj = dataBlock.inputValue(RetopoGuideNode.aInSurface).data()
            if not inObj.isNull():
                outHandle.setMObject(inObj)
            else:
                outHandle.setMObject(self._computeCachedSurface(dataBlock))
            dataBlock.setClean(RetopoGuideNode.aOutSurface)
            return

        positions, splines = self._finalPositions(dataBlock)
        if positions:
            outHandle.setMObject(
                RetopoGuideNode._buildMeshData(positions, splines))
        else:
            inObj = dataBlock.inputValue(RetopoGuideNode.aInSurface).data()
            if not inObj.isNull():
                outHandle.setMObject(inObj)
            else:
                outHandle.setMObject(self._computeCachedSurface(dataBlock))

        dataBlock.setClean(RetopoGuideNode.aOutSurface)

    def _computeWorldSurface(self, plug, dataBlock):
        """ワールド空間の最終メッシュを出力する。

        outSurface と同じ「デフォーマ + tweak」込みの形状に、その
        インスタンスのワールド行列を掛けたもの。blendShape は
        worldSurface を読むので、ここが実際の形状と一致していないと
        ターゲットの差分が正しく取れない。

        中間オブジェクト (Orig ノード) はデフォーマチェーンの入力なので、
        レスト形状 (cachedSurface) をそのまま返す。
        """
        try:
            outHandle = dataBlock.outputValue(plug)

            positions = None
            splines = None
            if not self._isIntermediate():
                positions, splines = self._finalPositions(dataBlock)

            if not positions:
                outHandle.setMObject(self._computeCachedSurface(dataBlock))
                dataBlock.setClean(plug)
                return

            mat = self._instanceMatrix(plug)
            if mat is not None:
                world = []
                for p in positions:
                    q = om1.MPoint(p[0], p[1], p[2]) * mat
                    world.append([q.x, q.y, q.z])
                positions = world

            outHandle.setMObject(
                RetopoGuideNode._buildMeshData(positions, splines))
            dataBlock.setClean(plug)
        except Exception as e:
            print("[RetopoGuide] Error in _computeWorldSurface:", e)

    # -----------------------------------------------------------------
    # _computeOutNetData — JSON 出力 (Poisson deformer 用)
    # -----------------------------------------------------------------
    def _computeOutNetData(self, dataBlock, positions_only=False):
        """outNetData (JSON) を計算する。

        データフロー (優先順位):
          1. サーフェス追従: driverMesh + surfaceBindData → ワープ + CP
          2. デフォーマあり: inSurface (skin(rest)) + CP * envelope
          3. デフォーマなし: base + controlPoints (直接適用)
          → outNetData JSON

        サーフェス追従の場合 (Pixar 2023 Talks §3):
          カーブネットの CV は変形メッシュ表面に重心座標で追従。
          controlPoints はワープ後のゼロ点からのデルタとして適用。
          → 二重トランスフォームは発生しない。
        """
        base_str = dataBlock.inputValue(RetopoGuideNode.aNetData).asString()
        output_attr = RetopoGuideNode.aOutPositions if positions_only else RetopoGuideNode.aOutNetData
        outHandle = dataBlock.outputValue(output_attr)
        def write_positions(pos):
            if positions_only:
                values = [x for p in pos for x in p]
                util = om1.MScriptUtil()
                if values:
                    util.createFromList(values, len(values))
                    array = om1.MDoubleArray(util.asDoublePtr(), len(values))
                else:
                    array = om1.MDoubleArray()
                outHandle.setMObject(om1.MFnDoubleArrayData().create(array))
            else:
                outHandle.setString(_out_json(pos))
            dataBlock.setClean(output_attr)

        if not base_str:
            if positions_only: write_positions([])
            else: outHandle.setString(""); dataBlock.setClean(output_attr)
            return

        try:
            cn = RetopoGuideData.from_json_cached(base_str)
        except Exception:
            if positions_only: write_positions([])
            else: outHandle.setString(base_str); dataBlock.setClean(output_attr)
            return

        base_positions = [list(p) for p in cn.positions]
        splines = cn.splines
        positions = [list(p) for p in cn.positions]

        # 共有インスタンスを壊さずに位置だけ差し替えた JSON を作る
        def _out_json(pos):
            d = cn.to_dict()
            d["positions"] = [list(p) for p in pos]
            return _json.dumps(d, separators=(",", ":"))

        preview = dataBlock.inputValue(RetopoGuideNode.aEditPreviewPositions).data()
        if not preview.isNull():
            values = om1.MFnDoubleArrayData(preview).array()
            if values.length() == len(cn.positions)*3 and values.length():
                if positions_only:
                    outHandle.setMObject(preview)
                    dataBlock.setClean(output_attr)
                else:
                    write_positions([[values[i],values[i+1],values[i+2]]
                                     for i in range(0,values.length(),3)])
                return

        # --- EP set & handle set ---
        ep_set = cn.ep_indices
        handle_set = cn.handle_indices

        # ==============================================================
        # Path 1: サーフェス追従 (driverMesh + surfaceBindData)
        # ==============================================================
        bind_data = self._getSurfaceBindData(dataBlock)
        driver_verts = self._getDriverMeshVerts(dataBlock) if bind_data else None

        if bind_data and driver_verts:
            # ワープ: 各 CV を変形メッシュ表面に追従させる
            positions = self._computeSurfaceWarp(
                base_positions, bind_data, driver_verts)

            # controlPoints: ワープ後のゼロ点からのデルタ (ユーザー調整)
            # サーフェスバインドではハンドルも重心座標で正しくワープ済みなので
            # _propagate_handles は不要。全 CP を直接加算する。
            delta_map = self._readControlPointDeltas(dataBlock)
            if delta_map:
                for idx, (dx, dy, dz) in delta_map.items():
                    if idx < len(positions):
                        positions[idx][0] += dx
                        positions[idx][1] += dy
                        positions[idx][2] += dz

            write_positions(positions)
            dataBlock.setClean(output_attr)
            return

        # ==============================================================
        # Path 2: デフォーマチェーン (inSurface — skinCluster 後方互換)
        # ==============================================================
        # --- Deformer chain (inSurface) ---
        # skinCluster はハンドルにタンジェント回転を適用済みなので
        # inSurface から全頂点 (ハンドル含む) の変形位置を取得する。
        all_deltas = {}
        deformed_pos = self._getDeformedPositions(dataBlock)
        if deformed_pos is not None:
            for i in range(min(len(positions), len(deformed_pos))):
                dx = deformed_pos[i][0] - base_positions[i][0]
                dy = deformed_pos[i][1] - base_positions[i][1]
                dz = deformed_pos[i][2] - base_positions[i][2]
                if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                    all_deltas[i] = [dx, dy, dz]
                positions[i] = list(deformed_pos[i])

        # --- controlPoints: pose-dependent sculpt corrections ---
        # デフォーマなし → CP を直接適用 (レスト形状の編集)
        #   ハンドルは handle_user_offsets に記録し _propagate_handles 経由で適用
        # デフォーマあり → 全 CP をスキン変位エンベロープでスケール
        #   バインドポーズ (envelope≈0) で補正はゼロになり元のレストに戻る
        #   ハンドル CP も envelope スケールで適用 (VP2描画と同じ)
        handle_user_offsets = {}
        delta_map = self._readControlPointDeltas(dataBlock)
        # 確定済みの多ポーズターゲットは CP がゼロでも適用する必要がある
        target_map = _read_sculpt_targets(
            om1.MFnDependencyNode(self.thisMObject()))
        if delta_map or target_map:
            if deformed_pos is None:
                # No deformer — direct rest editing
                # ハンドルは handle_user_offsets に記録 → _propagate_handles で処理
                for idx, (dx, dy, dz) in delta_map.items():
                    if idx < len(positions):
                        if idx in handle_set:
                            handle_user_offsets[idx] = [dx, dy, dz]
                        else:
                            positions[idx][0] += dx
                            positions[idx][1] += dy
                            positions[idx][2] += dz
            else:
                # Deformer active — envelope-scaled sculpt corrections
                # ハンドル CP も含めて全て envelope スケール (VP2描画と統一)
                # エンベロープは CV ごと。全体の max だと腕を動かしただけで
                # 脚の補正まで効いてしまい、しかも 0/1 で飛ぶ。
                try:
                    frac = dataBlock.inputValue(
                        RetopoGuideNode.aSculptFalloff).asDouble()
                except Exception:
                    frac = SCULPT_FALLOFF_FRACTION
                try:
                    pof = dataBlock.inputValue(
                        RetopoGuideNode.aPoseFalloff).asDouble()
                except Exception:
                    pof = _sp.POSE_FALLOFF_DEFAULT
                pose_map = _read_sculpt_pose_map(
                    om1.MFnDependencyNode(self.thisMObject()))
                offsets = _apply_sculpt(
                    base_positions, deformed_pos, splines,
                    delta_map, pose_map, pof, frac, target_map)
                ep_cp_deltas = {}  # EP の CP デルタを記録 → ハンドル平行移動用
                for idx, (ex, ey, ez) in offsets.items():
                    if idx < len(positions):
                        positions[idx][0] += ex
                        positions[idx][1] += ey
                        positions[idx][2] += ez
                        prev = all_deltas.get(idx, [0, 0, 0])
                        all_deltas[idx] = [prev[0] + ex,
                                           prev[1] + ey,
                                           prev[2] + ez]
                        if idx in ep_set:
                            ep_cp_deltas[idx] = [ex, ey, ez]

                # EP の CP 移動分をハンドルに平行移動で伝播
                if ep_cp_deltas:
                    _translate_handles_by_ep_cp(
                        positions, splines, ep_set, ep_cp_deltas)

        if (not all_deltas and deformed_pos is None
                and not delta_map):
            # Neither deformer nor manual deltas — nothing changed
            write_positions(positions)
            dataBlock.setClean(output_attr)
            return

        # ハンドル自動追従: deformer なし (skinCluster なし) の場合のみ
        # _propagate_handles で EP の回転推定からハンドルを計算する。
        # deformer ありの場合は skinCluster がハンドル回転を既に適用済み。
        if deformed_pos is None and all_deltas:
            rest_positions = [list(p) for p in base_positions]
            _propagate_handles(positions, rest_positions, splines,
                               ep_set, all_deltas,
                               handle_user_offsets=handle_user_offsets)
        elif deformed_pos is None and handle_user_offsets:
            # deformer なし、EP 不動、ハンドルの手動オフセットだけある
            for idx, uo in handle_user_offsets.items():
                if idx < len(positions):
                    positions[idx][0] += uo[0]
                    positions[idx][1] += uo[1]
                    positions[idx][2] += uo[2]

        write_positions(positions)
        dataBlock.setClean(output_attr)

    # -----------------------------------------------------------------
    # Evaluation Manager (parallel / serial)
    # -----------------------------------------------------------------
    # EM モードでは setDependentsDirty は評価グラフ構築時にしか呼ばれず、
    # 以降のジョイント操作では VP2 へ再描画要求が届かない。DevKit の
    # apiMeshShape と同様に postEvaluation で draw dirty を通知する。
    _kEvalDirtyAttrs = ("aInSurface", "aDriverMesh", "aNetData", "aEditPreviewPositions",
                        "aSurfaceBindData", "aSculptPose",
                        "aSculptTargets", "_aCp")

    def postEvaluation(self, context, evaluationNode, evalType):
        try:
            if not context.isNormal():
                return
            for attr_name in RetopoGuideNode._kEvalDirtyAttrs:
                attr = getattr(RetopoGuideNode, attr_name)
                if not attr.isNull() and evaluationNode.dirtyPlugExists(attr):
                    self.childChanged(ompx.MPxSurfaceShape.kObjectChanged)
                    obj2 = _thisMObject_to_om2(self.thisMObject())
                    if obj2 is not None:
                        omr.MRenderer.setGeometryDrawDirty(obj2)
                    return
        except Exception:
            pass

    # -----------------------------------------------------------------
    # setDependentsDirty
    # -----------------------------------------------------------------
    def setDependentsDirty(self, plug, plugArray):
        # print("[RetopoGuideNode] setDependentsDirty called for plug:", plug.name())
        try:
            attr = om1.MFnAttribute(plug.attribute())
            name = attr.name()
            if name in ("controlPoints", "xValue", "yValue", "zValue", "inSurface", "netData", "editPreviewPositions", "driverMesh", "surfaceBindData",
                        "xray", "xrayDepthPriority",
                        "curveColor", "curveColorR", "curveColorG", "curveColorB",
                        "curveWidth", "pointSize", "handleSize", "showHandles",
                        "handleColor", "handleColorR", "handleColorG", "handleColorB"):
                self.childChanged(ompx.MPxSurfaceShape.kObjectChanged)
                
                # controlPoints系は inherited attr のため attributeAffects が効かない場合があるので明示的に追加
                if name in ("controlPoints", "xValue", "yValue", "zValue"):
                    if not RetopoGuideNode.aOutPositions.isNull():
                        plugArray.append(om1.MPlug(self.thisMObject(), RetopoGuideNode.aOutPositions))
                    if not RetopoGuideNode.aOutNetData.isNull():
                        plugArray.append(
                            om1.MPlug(self.thisMObject(),
                                      RetopoGuideNode.aOutNetData))
                    if not RetopoGuideNode.aOutSurface.isNull():
                        plugArray.append(
                            om1.MPlug(self.thisMObject(),
                                      RetopoGuideNode.aOutSurface))
                    if not RetopoGuideNode.aWorldSurface.isNull():
                        plugArray.append(
                            om1.MPlug(self.thisMObject(),
                                      RetopoGuideNode.aWorldSurface))
                    if not RetopoGuideNode.aCachedSurface.isNull():
                        plugArray.append(
                            om1.MPlug(self.thisMObject(),
                                      RetopoGuideNode.aCachedSurface))
                
                # VP2 に再描画を要求 (API 2.0 経由)
                obj2 = _thisMObject_to_om2(self.thisMObject())
                if obj2 is not None:
                    omr.MRenderer.setGeometryDrawDirty(obj2)
        except Exception:
            pass
        return ompx.MPxSurfaceShape.setDependentsDirty(self, plug, plugArray)

    # -----------------------------------------------------------------
    # Component support
    # -----------------------------------------------------------------

    # MatchResult 定数 — C++ enum を Python で安全に取得
    _kMatchOk = getattr(ompx.MPxSurfaceShape, 'kMatchOk', 0)
    _kMatchNone = getattr(ompx.MPxSurfaceShape, 'kMatchNone', 1)
    _kMatchInvalidAttributeRange = getattr(
        ompx.MPxSurfaceShape, 'kMatchInvalidAttributeRange', 4)

    def matchComponent(self, item, spec, list_):
        """Component specification matcher (apiMeshShape パターン).

        C++ MatchResult enum:
          kMatchOk = 0, kMatchNone = 1, ...
        Python の True=1=kMatchNone なので、enum 定数で返す必要がある。
        """
        try:
            if spec.length() != 1:
                return RetopoGuideNode._kMatchNone

            attrSpec = spec[0]
            # API 1.0: dimensions / name は SWIG メソッド (callable)
            # API 2.0 やバージョン差異でプロパティの場合もあるため両方対応
            _dim = attrSpec.dimensions
            dim = _dim() if callable(_dim) else _dim
            _name = attrSpec.name
            name = str(_name() if callable(_name) else _name)

            if dim == 0 or name not in ("vtx", "cv", "controlPoints"):
                return RetopoGuideNode._kMatchNone

            numVerts = self._getPositionCount()
            if numVerts == 0:
                return RetopoGuideNode._kMatchNone

            attrIndex = attrSpec[0]

            # デフォルト: 全頂点 (ワイルドカード * 用)
            lower = 0
            upper = numVerts - 1

            if attrIndex.hasLowerBound():
                try:
                    lower = attrIndex.getLower()
                except TypeError:
                    # API 1.0: C++ 参照パラメータは MScriptUtil 経由
                    util = om1.MScriptUtil()
                    util.createFromInt(0)
                    ptr = util.asIntPtr()
                    attrIndex.getLower(ptr)
                    lower = om1.MScriptUtil.getInt(ptr)
            if attrIndex.hasUpperBound():
                try:
                    upper = attrIndex.getUpper()
                except TypeError:
                    util = om1.MScriptUtil()
                    util.createFromInt(0)
                    ptr = util.asIntPtr()
                    attrIndex.getUpper(ptr)
                    upper = om1.MScriptUtil.getInt(ptr)

            if lower > upper or upper >= numVerts:
                return RetopoGuideNode._kMatchInvalidAttributeRange

            dag = om1.MDagPath()
            item.getDagPath(0, dag)

            comp_fn = om1.MFnSingleIndexedComponent()
            comp = comp_fn.create(om1.MFn.kMeshVertComponent)
            for i in range(lower, upper + 1):
                comp_fn.addElement(i)

            list_.add(dag, comp)
            return RetopoGuideNode._kMatchOk
        except Exception as e:
            import sys
            sys.stderr.write("[RetopoGuide matchComponent] {}\n".format(e))
            import traceback; traceback.print_exc()
            return RetopoGuideNode._kMatchNone

    def componentToPlugs(self, component, list_):
        """コンポーネントを、実際に書き換わるプラグへ変換する。

        Maya はコンポーネント編集の undo を作るとき、このメソッドで
        「これから変更されるプラグ」を集め、その値を退避しておく。
        したがって返すプラグは *実際の書き込み先* でなければならない。

        履歴 (blendShape や tweak) がある状態では書き込み先は自分の
        ``controlPoints`` ではなく履歴側になる。``convertToTweakNodePlug``
        はその変換を Maya が用意してくれているもので、blendShape の
        ターゲット編集モード中は ``blendShape.inputTarget[N].controlPoints``
        を指すようになる。

        これを怠って常に自分の ``controlPoints`` を返していると、Maya は
        変化しないプラグを退避することになり、undo しても値が元のまま
        =「まったく反応しない」という症状になる。
        """
        if component.isNull():
            return
        if not component.hasFn(om1.MFn.kSingleIndexedComponent):
            return
        comp_fn = om1.MFnSingleIndexedComponent(component)
        fn = om1.MFnDependencyNode(self.thisMObject())
        attr = fn.attribute("controlPoints")
        plug = om1.MPlug(self.thisMObject(), attr)
        try:
            self.convertToTweakNodePlug(plug)
        except Exception:
            pass
        # 変換後は要素プラグ (...controlPoints[0]) になっていることが
        # あるので、配列へ戻してからインデックスを選び直す。
        try:
            if plug.isElement():
                plug = plug.array()
        except Exception:
            pass
        for i in range(comp_fn.elementCount()):
            try:
                list_.add(plug.elementByLogicalIndex(comp_fn.element(i)))
            except Exception:
                pass

    def createFullVertexGroup(self):
        """全頂点を含むコンポーネントを返す。

        retopoGuideSkinCluster がハンドル頂点にも EP のウェイトを適用するため、
        デフォーマメンバーには全頂点を含める。
        """
        comp_fn = om1.MFnSingleIndexedComponent()
        comp = comp_fn.create(om1.MFn.kMeshVertComponent)
        count = len(self._getBasePositions())
        for i in range(count):
            comp_fn.addElement(i)
        return comp

    # -----------------------------------------------------------------
    # geometryIteratorSetup (API 1.0)
    # -----------------------------------------------------------------
    def geometryIteratorSetup(self, componentList, components,
                               forReadOnly=False):
        positions = self._getFinalPositions()
        if not positions:
            # Return minimal iterator to prevent freeze
            positions = [[0, 0, 0]]
        basePositions = self._getBasePositions()
        if not basePositions:
            basePositions = list(positions)
        shapeObj = self.thisMObject()
        if components.isNull():
            it = RetopoGuideGeomIterator(positions, basePositions,
                                      componentList, shapeObj)
        else:
            it = RetopoGuideGeomIterator(positions, basePositions,
                                      components, shapeObj)
        # prevent GC before Maya finishes using the iterator
        self.__geometryIterator = it
        return it

    # -----------------------------------------------------------------
    # transformUsing / tweakUsing (API 1.0 — 正しく仮想ディスパッチされる)
    #
    # コンポーネント編集の undo は Maya 標準の仕組みに任せる。Maya は
    # ドラッグ開始時に kSavePoints で呼び、そのとき pointCache に積んだ
    # 内容をコマンド側に保持しておき、undo のときに kRestorePoints で
    # 返してくる。つまり pointCache はプラグイン専用の退避領域であって、
    # 中身の形式はこちらで自由に決めてよい。
    #
    # ここでは (値, インデックス) の組を積む。こうしておくと復元時に
    # componentList を当てにしなくて済み、EP に連動して動かした
    # ハンドルのような「選択されていないが書き換えた点」も確実に
    # 元へ戻せる。
    #
    # 以前は setDouble で直接書いたあと cmds.setAttr で undo チャンクを
    # 作り直す独自機構を持っていた。しかし transformUsing に
    # kRestorePoints の分岐が無かったため、undo の 1 回目がその機構の
    # 起動に消費されてしまい「1 回目は無反応、2 回目でやっと戻る」と
    # いう二度押しになっていた。独自機構は撤去した。
    # -----------------------------------------------------------------
    def _cpPlug(self):
        fn = om1.MFnDependencyNode(self.thisMObject())
        return fn.findPlug("controlPoints", False)

    @staticmethod
    def _cpGet(cp_plug, idx):
        elem = cp_plug.elementByLogicalIndex(idx)
        return (elem.child(0).asDouble(),
                elem.child(1).asDouble(),
                elem.child(2).asDouble())

    @staticmethod
    def _cpSet(cp_plug, idx, x, y, z):
        elem = cp_plug.elementByLogicalIndex(idx)
        elem.child(0).setDouble(x)
        elem.child(1).setDouble(y)
        elem.child(2).setDouble(z)

    @staticmethod
    def _cacheSave(pointCache, idx, value):
        """undo 用に (値, インデックス) の組を積む。"""
        pointCache.append(om1.MPoint(value[0], value[1], value[2]))
        pointCache.append(om1.MPoint(float(idx), 0.0, 0.0))

    @staticmethod
    def _cacheItems(pointCache):
        """``_cacheSave`` で積んだ組を ``(idx, 値)`` の列で取り出す。"""
        out = []
        if pointCache is None:
            return out
        for i in range(0, pointCache.length() - 1, 2):
            v = pointCache[i]
            out.append((int(round(pointCache[i + 1].x)), (v.x, v.y, v.z)))
        return out

    def _editTargets(self, componentList, cachingMode, stateAttr):
        """編集対象と基準位置を求める。

        ``kUpdatePoints`` の ``mat`` は前フレームからの増分なので、
        基準にする位置も前フレームのものでなければならない。
        ``_getFinalPositions()`` は 50ms のキャッシュを持っていて
        ドラッグ中は古い値を返すため、基準位置は ``stateAttr`` に
        自前で持ち越す。

        戻り値は ``(sel, extra, owner, base)``。``sel`` が選択された
        CV、``extra`` が EP に連動して動かすハンドル、``owner`` が
        ハンドル → 連動元 EP、``base`` が基準位置。
        """
        drag = getattr(self, stateAttr, None)
        if cachingMode == _kUpdatePoints and drag:
            return drag["sel"], drag["extra"], drag["owner"], drag["pos"]

        positions = self._getFinalPositions()
        if not positions:
            return [], [], {}, {}
        sel, extra, owner = self._tweakSplit(componentList, len(positions))
        base = {}
        for idx in sel + extra:
            p = positions[idx]
            base[idx] = om1.MPoint(p[0], p[1], p[2])
        return sel, extra, owner, base

    @staticmethod
    def _editDeltas(sel, extra, owner, base, mat):
        """``mat`` による変位と、その適用後の基準位置を求める。

        EP を動かしたら対応するハンドルも同じだけ平行移動させて
        カーブの形状を保つ。
        """
        deltas = {}
        nextbase = {}
        for idx in sel:
            pt = base[idx]
            npt = pt * mat
            deltas[idx] = (npt.x - pt.x, npt.y - pt.y, npt.z - pt.z)
            nextbase[idx] = npt
        for idx in extra:
            d = deltas.get(owner.get(idx), (0.0, 0.0, 0.0))
            deltas[idx] = d
            pt = base[idx]
            nextbase[idx] = om1.MPoint(pt.x + d[0], pt.y + d[1], pt.z + d[2])
        return deltas, nextbase

    def transformUsing(self, mat, componentList,
                       cachingMode=None, pointCache=None):
        """コンポーネント編集を ``controlPoints`` へ適用する。

        blendShape などの履歴が無い素の状態ではこちらが呼ばれる。
        履歴があるときは ``tweakUsing`` が呼ばれる。
        """
        cp_plug = self._cpPlug()

        # undo (kRestorePoints)。退避した値を書き戻すだけで、形状の
        # 評価には一切依存させない。undo は形状が計算できるかどうかに
        # 関わらず必ず成立しなければならない。
        if cachingMode == _kRestorePoints:
            for idx, v in self._cacheItems(pointCache):
                self._cpSet(cp_plug, idx, v[0], v[1], v[2])
            self._drag_state = None
            self._pullOutNetData()
            self._afterTweak()
            return

        sel, extra, owner, base = self._editTargets(
            componentList, cachingMode, "_drag_state")
        if not sel:
            return
        order = sel + extra

        if cachingMode == _kSavePoints and pointCache is not None:
            pointCache.clear()
            for idx in order:
                self._cacheSave(pointCache, idx, self._cpGet(cp_plug, idx))

        if cachingMode != _kUpdatePoints:
            # PSD: この編集がどのポーズで行われたかを記録する。
            # CP を書き換える *前* に呼ぶこと。ドラッグ中にポーズは
            # 変わらないので開始時に 1 度だけでよい。
            _record_sculpt_pose(self.thisMObject(), list(order))

        deltas, nextbase = self._editDeltas(sel, extra, owner, base, mat)
        for idx in order:
            d = deltas[idx]
            if max(abs(c) for c in d) < 1e-12:
                continue
            cur = self._cpGet(cp_plug, idx)
            self._cpSet(cp_plug, idx,
                        cur[0] + d[0], cur[1] + d[1], cur[2] + d[2])

        if cachingMode in (_kSavePoints, _kUpdatePoints):
            self._drag_state = {"sel": sel, "extra": extra,
                                "owner": owner, "pos": nextbase}
        else:
            self._drag_state = None

        self._pullOutNetData()
        self._afterTweak()

    def tweakUsing(self, mat, componentList, cachingMode, pointCache, handle):
        """tweak を Maya が指定した書き込み先 (``handle``) へ適用する。

        ``handle`` は Maya が用意した tweak 用の ``MArrayDataHandle`` で、
        普段は自分の ``controlPoints`` を指すが、blendShape のターゲット
        編集モード (``cmds.sculptTarget``) 中はそのターゲットを指す。
        標準の mesh / NURBS が「ターゲットを編集状態にして頂点を動かすと
        変位がターゲットに入る」という挙動になるのはこの仕組みによる。

        ``controlPoints`` プラグへ直接書くとこの仕組みを丸ごと迂回する
        ことになり、Shape Editor でいくら編集してもターゲットには何も
        入らない。必ず ``handle`` を経由すること。

        ``pointCache`` に積むのは *その編集で加えた累積変位* であって、
        編集前の値でも位置でもない (``transformUsing`` とは規約が違う)。
        これは書き込み先によって復元の仕方が変わるため。

        - 自分の ``controlPoints`` や tweak ノードが相手のとき、書き込みは
          *代入* なので「編集前の値」を書けば戻る。
        - blendShape のターゲット編集モードでは、blendShape が handle の
          値をターゲットへ *加算* してから handle をクリアする。そのため
          undo 時に読める現在値は常にゼロで、「編集前の値」を書いても
          加算される差分がゼロになり **何も起こらない**。

        両方を一つの式で満たすには ``現在値 - 累積変位`` を書けばよい。
        代入型なら ``(編集前 + d) - d = 編集前``、加算型なら ``0 - d``
        が入って加算結果がゼロに戻る。
        """
        builder = handle.builder()

        if cachingMode == _kRestorePoints:
            items = self._cacheItems(pointCache)
            if not items:
                st = getattr(self, "_tweak_state", None) or {}
                items = sorted((st.get("accum") or {}).items())
            for idx, d in items:
                cur = _tweak_get(builder, idx)
                _tweak_set(builder, idx,
                           cur[0] - d[0], cur[1] - d[1], cur[2] - d[2])
            handle.set(builder)
            self._tweak_state = None
            self._afterTweak()
            return

        sel, extra, owner, base = self._editTargets(
            componentList, cachingMode, "_tweak_state")
        if not sel:
            return
        order = sel + extra

        deltas, nextbase = self._editDeltas(sel, extra, owner, base, mat)

        # 累積変位を更新して退避する。ドラッグ中は kUpdatePoints が
        # 何度も来るので、そのたびに積み直して総変位を保つ。
        accum = {}
        if cachingMode == _kUpdatePoints:
            prev = (getattr(self, "_tweak_state", None) or {}).get("accum")
            accum.update(prev or {})
        for idx in order:
            d = deltas[idx]
            a = accum.get(idx, (0.0, 0.0, 0.0))
            accum[idx] = (a[0] + d[0], a[1] + d[1], a[2] + d[2])

        if (cachingMode in (_kSavePoints, _kUpdatePoints)
                and pointCache is not None):
            pointCache.clear()
            for idx in sorted(accum):
                self._cacheSave(pointCache, idx, accum[idx])

        for idx in order:
            d = deltas[idx]
            if max(abs(c) for c in d) < 1e-12:
                continue
            old = _tweak_get(builder, idx)
            _tweak_set(builder, idx,
                       old[0] + d[0], old[1] + d[1], old[2] + d[2])

        # 変位がゼロでも handle.set() は必ず呼ぶ。builder には
        # addElement() で要素を足してあるので、set しないと Maya 側の
        # データと食い違い、その後の undo が成立しなくなる。
        handle.set(builder)

        if cachingMode in (_kSavePoints, _kUpdatePoints):
            self._tweak_state = {"sel": sel, "extra": extra, "owner": owner,
                                 "pos": nextbase, "accum": accum}
        else:
            self._tweak_state = None

        self._afterTweak()

    def _pullOutNetData(self):
        """下流を更新するために outNetData を強制評価する。"""
        try:
            om1.MFnDependencyNode(self.thisMObject()).findPlug(
                "outNetData", False).asString()
        except Exception:
            pass

    def _afterTweak(self):
        """点を書き換えたあとの通知をまとめる。"""
        for name in ("kBoundingBoxChanged", "kObjectChanged"):
            what = getattr(ompx.MPxSurfaceShape, name, None)
            if what is not None:
                try:
                    self.childChanged(what)
                except Exception:
                    pass
        obj2 = _thisMObject_to_om2(self.thisMObject())
        if obj2 is not None:
            omr.MRenderer.setGeometryDrawDirty(obj2)

    def _tweakSplit(self, componentList, limit=None):
        """編集対象を (選択分, EP 連動ハンドル分, 連動元) に分ける。

        pointCache には「選択分 → 連動ハンドル分」の順で積む。
        連動ハンドルは必ずソートして順序を決定的にする。
        """
        if limit is None:
            try:
                limit = self._getPositionCount()
            except Exception:
                limit = 0
        indices = self._componentIndices(componentList, limit)
        moved = set(indices)
        owner = {}
        try:
            ep_map = self._getEPHandleMap()
        except Exception:
            ep_map = {}
        for ep_idx, h_indices in ep_map.items():
            if ep_idx not in moved:
                continue
            for h_idx in h_indices:
                if h_idx in moved or h_idx in owner:
                    continue
                if 0 <= h_idx < limit:
                    owner[h_idx] = ep_idx
        return indices, sorted(owner), owner

    def _componentIndices(self, componentList, limit):
        """コンポーネントリストから CV インデックスを取り出す。"""
        indices = []
        for ci in range(componentList.length()):
            comp = componentList[ci]
            if (comp.isNull()
                    or not comp.hasFn(om1.MFn.kSingleIndexedComponent)):
                continue
            cfn = om1.MFnSingleIndexedComponent(comp)
            for ei in range(cfn.elementCount()):
                idx = cfn.element(ei)
                if 0 <= idx < limit:
                    indices.append(idx)
        return indices

    def acceptsGeometryIterator(self, writeable=True, forReadOnly=True):
        return True

    # -----------------------------------------------------------------
    # コンポーネントの削除 (コンポーネントモードで選択 → Delete)
    # -----------------------------------------------------------------
    # Maya の ``delete`` (= doDelete = Delete キー) は、カスタムシェイプの
    # コンポーネントに対して MPxSurfaceShape::deleteComponents を呼ぶ。
    # undo は ``undeleteComponents`` に戻す責任があり、両者の受け渡しには
    # ``undoInfo`` (MDoubleArray) しか使えない。実際の状態は数値では
    # 表せないのでモジュール側に控え、その控え番号だけを載せる。

    def _shapeName(self):
        try:
            fn = om1.MFnDagNode(self.thisMObject())
            return fn.fullPathName() or fn.name()
        except Exception:
            try:
                return om1.MFnDependencyNode(self.thisMObject()).name()
            except Exception:
                return ""

    def deleteComponents(self, componentList, undoInfo):
        try:
            from Aru_RetopoTool.editor.curvenet import curve_net_edit as _edit
            shape = self._shapeName()
            if not shape:
                return False
            indices = self._componentIndices(componentList,
                                             self._getPositionCount())
            if not indices:
                return False

            token = _push_delete_snapshot(_edit.snapshot_curvenet(shape))
            try:
                undoInfo.clear()
            except Exception:
                pass
            undoInfo.append(float(token))

            _edit.delete_selected_eps(shape, cv_indices=indices)
            return True
        except Exception:
            sys.stderr.write("[RetopoGuide deleteComponents]\n")
            import traceback
            traceback.print_exc()
            return False

    def undeleteComponents(self, componentList, undoInfo):
        try:
            from Aru_RetopoTool.editor.curvenet import curve_net_edit as _edit
            if undoInfo.length() < 1:
                return False
            snap = _peek_delete_snapshot(int(undoInfo[0]))
            if snap is None:
                return False
            return bool(_edit.restore_curvenet(snap))
        except Exception:
            sys.stderr.write("[RetopoGuide undeleteComponents]\n")
            import traceback
            traceback.print_exc()
            return False

    def getComponentSelectionMask(self):
        # kSelectCVs: VP2 矩形選択で kMesh データと干渉しないためのメインマスク
        # kSelectMeshVerts: select -r transform.vtx[N] が matchComponent に
        #   ルーティングされるために必要 (Component Editor / skinCluster 互換)
        mask = om1.MSelectionMask(om1.MSelectionMask.kSelectCVs)
        mask.addMask(om1.MSelectionMask.kSelectMeshVerts)
        return mask

    def getShapeSelectionMask(self):
        return om1.MSelectionMask(om1.MSelectionMask.kSelectMeshes)

    # -----------------------------------------------------------------
    # Geometry helpers
    # -----------------------------------------------------------------
    def _getNetData(self):
        """netData 属性から RetopoGuideData を取得する (API 1.0)。読み取り専用の共有インスタンス。"""
        try:
            fn = om1.MFnDependencyNode(self.thisMObject())
            raw = fn.findPlug("netData", False).asString()
            if not raw:
                return RetopoGuideData()
            return RetopoGuideData.from_json_cached(raw)
        except Exception:
            return RetopoGuideData()

    def _getEPHandleMap(self):
        """EP index → [handle indices] のマッピングを返す。

        各スプライン (ep0, h0, h1, ep1) について:
          ep0 → h0, ep1 → h1 を登録。
        ハンドル自身が明示的に動かされた場合は追従しないので、
        呼び出し側で moved_indices と照合する。
        """
        ep_to_handles = {}
        cn = self._getNetData()
        for sp in cn.splines:
            if len(sp) >= 4:
                ep_to_handles.setdefault(sp[0], []).append(sp[1])
                ep_to_handles.setdefault(sp[3], []).append(sp[2])
        return ep_to_handles

    def _getEPIndices(self):
        """netData からエンドポイント (EP) インデックスのみを返す。"""
        return sorted(self._getNetData().ep_indices)

    def _getPositionCount(self):
        return len(self._getNetData().positions)

    def _getBasePositions(self):
        return [list(p) for p in self._getNetData().positions]

    def _getSplines(self):
        return list(self._getNetData().splines)

    def _getFinalPositions(self):
        # Lightweight cache: reuse result if called again within 50ms
        # (prevents freeze from repeated calls during marking-menu build)
        import time
        now = time.monotonic()
        if (hasattr(self, '_fp_cache_time')
                and (now - self._fp_cache_time) < 0.05
                and hasattr(self, '_fp_cache_result')
                and self._fp_cache_result is not None):
            return self._fp_cache_result

        result = self._computeFinalPositions()
        self._fp_cache_result = result
        self._fp_cache_time = now
        return result

    def _computeFinalPositions(self):
        cn = self._getNetData()
        positions = [list(p) for p in cn.positions]
        if not positions:
            return []
        base_rest = [list(p) for p in positions]  # rest 保存 (envelope 計算用)
        try:
            fn = om1.MFnDependencyNode(self.thisMObject())

            # ハンドル/EP インデックスとスプラインを特定
            handle_set = cn.handle_indices
            ep_set_fp = cn.ep_indices
            splines_fp = cn.splines

            # ==============================================================
            # Path 1: サーフェス追従 (driverMesh + surfaceBindData)
            # ==============================================================
            _has_surface_bind = False
            try:
                sbd_str = fn.findPlug("surfaceBindData", False).asString()
                dm_plug = fn.findPlug("driverMesh", False)
                if sbd_str and dm_plug.isDestination():
                    dm_obj = dm_plug.asMObject()
                    if not dm_obj.isNull():
                        dm_fn = om1.MFnMesh(dm_obj)
                        dm_pts = om1.MPointArray()
                        dm_fn.getPoints(dm_pts, om1.MSpace.kWorld)
                        if dm_pts.length() > 0:
                            driver_verts = [
                                [dm_pts[i].x, dm_pts[i].y, dm_pts[i].z]
                                for i in range(dm_pts.length())]
                            bind_data = _json.loads(sbd_str)
                            positions = RetopoGuideNode._computeSurfaceWarp(
                                base_rest, bind_data, driver_verts)
                            _has_surface_bind = True
            except Exception:
                pass

            # ==============================================================
            # Path 2: デフォーマチェーン (inSurface — skinCluster 後方互換)
            # ==============================================================
            _has_deformer = False
            if not _has_surface_bind:
                inPlug = fn.findPlug("inSurface", False)
                if inPlug.isDestination():
                    inObj = inPlug.asMObject()
                    if not inObj.isNull():
                        meshFn = om1.MFnMesh(inObj)
                        pts = om1.MPointArray()
                        meshFn.getPoints(pts, om1.MSpace.kObject)
                        if pts.length() > 0:
                            _has_deformer = True
                            for i in range(min(pts.length(), len(positions))):
                                positions[i] = [pts[i].x, pts[i].y, pts[i].z]

            # --- controlPoints: pose-dependent sculpt ---
            # サーフェスバインド → CP を直接適用 (ワープ後のデルタ)
            # デフォーマあり → 全 CP を envelope スケール (VP2描画と統一)
            # デフォーマなし → ハンドル CP は handle_user_offsets に記録
            all_deltas = {}
            handle_user_offsets = {}
            cp_plug = fn.findPlug("controlPoints", False)
            if cp_plug.isArray():
                cp_deltas = {}
                for pi in range(cp_plug.evaluateNumElements()):
                    elem = cp_plug.elementByPhysicalIndex(pi)
                    idx = elem.logicalIndex()
                    if idx < len(positions):
                        dx = elem.child(0).asDouble()
                        dy = elem.child(1).asDouble()
                        dz = elem.child(2).asDouble()
                        if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                            cp_deltas[idx] = (dx, dy, dz)
                _target_map = _read_sculpt_targets(fn)
                if cp_deltas or _target_map:
                    if _has_surface_bind:
                        # サーフェスバインド: ハンドルも重心座標でワープ済み
                        # 全 CP を直接加算
                        for idx, (dx, dy, dz) in cp_deltas.items():
                            positions[idx][0] += dx
                            positions[idx][1] += dy
                            positions[idx][2] += dz
                    elif _has_deformer:
                        pose_map = _read_sculpt_pose_map(fn)
                        offsets = _apply_sculpt(
                            base_rest, positions, splines_fp,
                            cp_deltas, pose_map,
                            _plug_double(fn, "poseFalloff",
                                         _sp.POSE_FALLOFF_DEFAULT),
                            _plug_double(fn, "sculptFalloff",
                                         SCULPT_FALLOFF_FRACTION),
                            _target_map)
                        ep_cp_deltas = {}
                        for idx, (ex, ey, ez) in offsets.items():
                            positions[idx][0] += ex
                            positions[idx][1] += ey
                            positions[idx][2] += ez
                            all_deltas[idx] = [ex, ey, ez]
                            if idx in ep_set_fp:
                                ep_cp_deltas[idx] = [ex, ey, ez]
                        # EP の CP 移動分をハンドルに平行移動で伝播
                        if ep_cp_deltas:
                            _translate_handles_by_ep_cp(
                                positions, splines_fp, ep_set_fp,
                                ep_cp_deltas)
                    else:
                        for idx, (dx, dy, dz) in cp_deltas.items():
                            if idx in handle_set:
                                handle_user_offsets[idx] = [dx, dy, dz]
                            else:
                                positions[idx][0] += dx
                                positions[idx][1] += dy
                                positions[idx][2] += dz

            # --- EP → ハンドル追従 (回転推定) ---
            # サーフェスバインド: ハンドルも重心座標でワープ済み → 不要
            # deformer なし: _propagate_handles で EP 回転推定からハンドルを計算
            # deformer あり: skinCluster がハンドル回転を既に適用済み → 不要
            if not _has_surface_bind and not _has_deformer and cn.splines:
                try:
                    splines = cn.splines
                    rest_positions = [list(p) for p in cn.positions]
                    ep_set = cn.ep_indices

                    for ei in ep_set:
                        if ei < len(positions) and ei < len(rest_positions):
                            dx = positions[ei][0] - rest_positions[ei][0]
                            dy = positions[ei][1] - rest_positions[ei][1]
                            dz = positions[ei][2] - rest_positions[ei][2]
                            if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                                all_deltas[ei] = [dx, dy, dz]

                    if all_deltas:
                        _propagate_handles(positions, rest_positions, splines,
                                           ep_set, all_deltas,
                                           handle_user_offsets=handle_user_offsets)
                    elif handle_user_offsets:
                        for idx, uo in handle_user_offsets.items():
                            if idx < len(positions):
                                positions[idx][0] += uo[0]
                                positions[idx][1] += uo[1]
                                positions[idx][2] += uo[2]
                except Exception:
                    pass
        except Exception:
            pass

        return positions

    # -----------------------------------------------------------------
    # Bounding box
    # -----------------------------------------------------------------
    def isBounded(self):
        return True

    def boundingBox(self):
        positions = self._getFinalPositions()
        if not positions:
            return om1.MBoundingBox(
                om1.MPoint(-1, -1, -1), om1.MPoint(1, 1, 1))
        min_pt = [1e30, 1e30, 1e30]
        max_pt = [-1e30, -1e30, -1e30]
        for p in positions:
            for k in range(3):
                if p[k] < min_pt[k]:
                    min_pt[k] = p[k]
                if p[k] > max_pt[k]:
                    max_pt[k] = p[k]
        pad = 0.5
        return om1.MBoundingBox(
            om1.MPoint(min_pt[0] - pad, min_pt[1] - pad, min_pt[2] - pad),
            om1.MPoint(max_pt[0] + pad, max_pt[1] + pad, max_pt[2] + pad))


# ======================================================================
# RetopoGuideShapeUI — MPxSurfaceShapeUI (API 1.0)
# ======================================================================

class RetopoGuideShapeUI(ompx.MPxSurfaceShapeUI):
    """RetopoGuideNode の VP2 選択 (コンポーネントピッキング)。"""

    def __init__(self):
        super(RetopoGuideShapeUI, self).__init__()

    @staticmethod
    def creator():
        return ompx.asMPxPtr(RetopoGuideShapeUI())

    def select(self, selectInfo, selectionList, worldSpaceSelectPts):
        dagPath = om1.MDagPath()
        selectInfo.selectPath(dagPath)
        node_obj = dagPath.node()
        if node_obj.isNull():
            return False

        try:
            dep = om1.MFnDependencyNode(node_obj)
            raw = dep.findPlug("netData", False).asString()
        except Exception:
            return False
        if not raw:
            return False
        try:
            cn = RetopoGuideData.from_json(raw)
        except Exception:
            return False
        if not cn.positions:
            return False
        base_positions = [list(p) for p in cn.positions]
        positions = [list(p) for p in cn.positions]

        # ハンドルインデックスを特定
        splines = cn.splines
        handle_set_sel = cn.handle_indices
        ep_set = cn.ep_indices

        # --- Deformer chains via inSurface ---
        # skinCluster はハンドルにタンジェント回転を適用済みなので
        # 全頂点 (ハンドル含む) の変形位置を取得する。
        _has_deformer = False
        try:
            inPlug = dep.findPlug("inSurface", False)
            if inPlug.isDestination:
                inObj = inPlug.asMObject()
                if not inObj.isNull():
                    meshFn = om1.MFnMesh(inObj)
                    pts = om1.MPointArray()
                    meshFn.getPoints(pts, om1.MSpace.kObject)
                    if pts.length() > 0:
                        _has_deformer = True
                        for i in range(min(pts.length(), len(positions))):
                            positions[i] = [pts[i].x, pts[i].y, pts[i].z]
        except Exception:
            pass

        # controlPoints delta 適用
        # deformer あり → 全 CP を envelope スケール (VP2描画と統一)
        # deformer なし → ハンドル CP は handle_user_offsets に記録
        all_deltas = {}
        handle_user_offsets = {}
        try:
            cp_plug = dep.findPlug("controlPoints", False)
            if cp_plug.isArray():
                cp_deltas = {}
                for pi in range(cp_plug.evaluateNumElements()):
                    elem = cp_plug.elementByPhysicalIndex(pi)
                    idx = elem.logicalIndex()
                    if idx < len(positions):
                        dx = elem.child(0).asDouble()
                        dy = elem.child(1).asDouble()
                        dz = elem.child(2).asDouble()
                        if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                            cp_deltas[idx] = (dx, dy, dz)
                _target_map = _read_sculpt_targets(dep)
                if cp_deltas or _target_map:
                    if _has_deformer:
                        pose_map = _read_sculpt_pose_map(dep)
                        offsets = _apply_sculpt(
                            base_positions, positions, splines,
                            cp_deltas, pose_map,
                            _plug_double(dep, "poseFalloff",
                                         _sp.POSE_FALLOFF_DEFAULT),
                            _plug_double(dep, "sculptFalloff",
                                         SCULPT_FALLOFF_FRACTION),
                            _target_map)
                        ep_cp_deltas = {}
                        for idx, (ex, ey, ez) in offsets.items():
                            positions[idx] = [
                                positions[idx][0] + ex,
                                positions[idx][1] + ey,
                                positions[idx][2] + ez,
                            ]
                            if idx in ep_set:
                                ep_cp_deltas[idx] = [ex, ey, ez]
                        # EP の CP 移動分をハンドルに平行移動で伝播
                        if ep_cp_deltas:
                            _translate_handles_by_ep_cp(
                                positions, splines, ep_set, ep_cp_deltas)
                    else:
                        for idx, (dx, dy, dz) in cp_deltas.items():
                            if idx in handle_set_sel:
                                handle_user_offsets[idx] = [dx, dy, dz]
                            else:
                                positions[idx] = [
                                    positions[idx][0] + dx,
                                    positions[idx][1] + dy,
                                    positions[idx][2] + dz,
                                ]
        except Exception:
            pass

        # EP → ハンドル追従 (回転推定)
        # deformer なし (skinCluster なし) の場合のみ _propagate_handles で
        # EP の回転推定からハンドルを計算する。
        if not _has_deformer:
            for ei in ep_set:
                if ei < len(positions) and ei < len(base_positions):
                    dx = positions[ei][0] - base_positions[ei][0]
                    dy = positions[ei][1] - base_positions[ei][1]
                    dz = positions[ei][2] - base_positions[ei][2]
                    if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                        all_deltas[ei] = [dx, dy, dz]

            if all_deltas:
                _propagate_handles(positions, base_positions, splines,
                                   ep_set, all_deltas,
                                   handle_user_offsets=handle_user_offsets)
            elif handle_user_offsets:
                for idx, uo in handle_user_offsets.items():
                    if idx < len(positions):
                        positions[idx][0] += uo[0]
                        positions[idx][1] += uo[1]
                        positions[idx][2] += uo[2]

        status = selectInfo.displayStatus()
        isHilite = (status == omui1.M3dView.kHilite)

        if isHilite:
            return self._selectComponents(
                selectInfo, selectionList, worldSpaceSelectPts,
                dagPath, positions, splines)
        else:
            return self._selectObject(
                selectInfo, selectionList, worldSpaceSelectPts,
                dagPath, positions)

    def _selectObject(self, selectInfo, selectionList,
                      worldSpaceSelectPts, dagPath, positions):
        alignMatrix = dagPath.inclusiveMatrix()
        for p in positions:
            worldPt = om1.MPoint(p[0], p[1], p[2]) * alignMatrix
            xPt = om1.MPoint()
            if selectInfo.selectClosest(worldPt, xPt):
                item = om1.MSelectionList()
                item.add(dagPath)
                selectInfo.addSelection(
                    item, worldPt, selectionList,
                    worldSpaceSelectPts,
                    om1.MSelectionMask(om1.MSelectionMask.kSelectMeshes),
                    False)
                return True
        return False

    def _selectComponents(self, selectInfo, selectionList,
                          worldSpaceSelectPts, dagPath, positions, splines):
        found = False
        comp_fn = om1.MFnSingleIndexedComponent()
        comp_obj = comp_fn.create(om1.MFn.kMeshVertComponent)
        closestPt = om1.MPoint()
        closestDist = float("inf")
        alignMatrix = dagPath.inclusiveMatrix()
        single = selectInfo.singleSelection()
        view = selectInfo.view()

        # _component_mode に応じてピック対象を絞る。
        # "all" / None でも EP とハンドルに限定する。cn.positions には
        # 参照の外れた孤立 CV が残っていることがあり、それらは描画されない
        # ので選択できてしまうと混乱の元になる。
        component_mode = _ctx._component_mode
        ep_set = set()
        handle_set = set()
        for sp in splines:
            if len(sp) >= 4:
                ep_set.add(sp[0])
                ep_set.add(sp[3])
                handle_set.add(sp[1])
                handle_set.add(sp[2])
        if component_mode == "ep":
            allowed = ep_set
        elif component_mode == "handle":
            allowed = handle_set
        else:
            allowed = ep_set | handle_set

        for idx, p in enumerate(positions):
            if idx not in allowed:
                continue
            worldPt = om1.MPoint(p[0], p[1], p[2]) * alignMatrix
            xPt = om1.MPoint()
            if selectInfo.selectClosest(worldPt, xPt):
                if single:
                    try:
                        util_x = om1.MScriptUtil()
                        util_x.createFromInt(0)
                        ptr_x = util_x.asShortPtr()
                        util_y = om1.MScriptUtil()
                        util_y.createFromInt(0)
                        ptr_y = util_y.asShortPtr()
                        view.worldToView(worldPt, ptr_x, ptr_y)
                        sx = om1.MScriptUtil.getShort(ptr_x)
                        sy = om1.MScriptUtil.getShort(ptr_y)
                        dist = float(sx * sx + sy * sy)
                    except Exception:
                        dist = 0.0
                    if dist < closestDist:
                        closestDist = dist
                        closestPt = worldPt
                        comp_obj = comp_fn.create(
                            om1.MFn.kMeshVertComponent)
                        comp_fn.addElement(idx)
                        found = True
                else:
                    comp_fn.addElement(idx)
                    closestPt = worldPt
                    found = True

        if found:
            item = om1.MSelectionList()
            item.add(dagPath, comp_obj)
            selectInfo.addSelection(
                item, closestPt, selectionList,
                worldSpaceSelectPts,
                om1.MSelectionMask(om1.MSelectionMask.kSelectCVs),
                True)
        return found


# ======================================================================
# API 1.0 → API 2.0 MObject 変換ヘルパー
# ======================================================================

def _thisMObject_to_om2(mobj_v1):
    """API 1.0 の MObject をノード名経由で API 2.0 MObject に変換する。"""
    try:
        fn = om1.MFnDependencyNode(mobj_v1)
        name = fn.name()
        sel = om2.MSelectionList()
        sel.add(name)
        return sel.getDependNode(0)
    except Exception:
        return None


