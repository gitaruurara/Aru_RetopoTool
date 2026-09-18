"""
RetopoGuide Edit — インタラクション・コマンド・ヘルパー
====================================================
draggerContext コールバック、MEL コマンド、メッシュユーティリティ、
ロケーター同期、スプライン操作などの編集機能を定義する。
"""

from __future__ import annotations

import math
import traceback
from typing import Optional

import maya.OpenMaya as om
import maya.OpenMayaMPx as ompx
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om2
import maya.api.OpenMayaRender as omr2
import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.curve_net_data import closest_point_on_bezier

# 定数と共有状態は aru_retopo_guide_plugin から参照
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import (
    kPluginNodeName,
    kEPNodeName, kHandleNodeName,
    kCmdCreate, kCmdAddPoint, kCmdRebuild,
    _DRAGGER_CTX, _LOC_GRP_SUFFIX,
    _nd_sj_map, _orphaned_loc_groups,
)


def _dirty_shape_view():
    """現在の retopoGuideNode シェイプを VP2 dirty にして再描画する。

    draggerContext のコールバック内では Maya が自動で再描画しないので、
    ここで同期的に refresh する (間引くとドラッグ中に 1 フレーム前の状態と
    交互に描かれて震える)。currentView だけで十分。
    """
    node = cmds.optionVar(q="retopoGuideContext_node") if cmds.optionVar(exists="retopoGuideContext_node") else ""
    if node and cmds.objExists(node):
        try:
            sel = om2.MSelectionList()
            sel.add(node)
            obj = sel.getDependNode(0)
            omr2.MRenderer.setGeometryDrawDirty(obj)
        except Exception:
            pass
    if cmds.about(batch=True):
        return
    cmds.refresh(currentView=True)


def _request_rebind(node: str) -> None:
    """netData が変わったので、繋がるデフォーマの遅延リバインドを予約する。"""
    try:
        from Aru_RetopoTool.editor.curvenet import curve_net_rebind
        curve_net_rebind.request(node)
    except Exception:
        pass


# ===========================================================================
# Maya API 1 ユーティリティ
# ===========================================================================

def _get_mesh_fn(mesh_name: str):
    """mesh_name から MFnMesh を返す（API 1 版）。"""
    sel = om.MSelectionList()
    sel.add(mesh_name)
    dag = om.MDagPath()
    sel.getDagPath(0, dag)
    dag.extendToShape()
    return om.MFnMesh(dag), dag


# ---------------------------------------------------------------------------
# 最近接点の八分木アクセラレータ
# ---------------------------------------------------------------------------
#
# MFnMesh.getClosestPoint は全面総当たりで、1 回のコストがメッシュの面数に
# 比例する (実測: 768 面 0.029ms → 30000 面 1.15ms)。カーブ 1 本を張るのに
# 数百回呼ぶので、密なメッシュではこれだけで数百 ms 掛かっていた。
#
# MMeshIntersector は八分木を 1 度作れば以降ほぼ一定時間で引ける
# (実測: 30000 面で 82 倍速)。八分木の構築は 30000 面で 21ms なので、
# メッシュごとにキャッシュして使い回す。
#
# メッシュが変形したら作り直さないと嘘の位置を返すため、シェイプの
# dirty コールバックでキャッシュを捨てる。
_ISECT_CACHE = {}


class _MeshAccel(object):
    """メッシュ 1 つぶんの八分木とワールド変換。"""

    __slots__ = ("isect", "mat", "inv", "cb_ids", "valid", "handle")

    def __init__(self, dag):
        self.isect = om.MMeshIntersector()
        self.mat = dag.inclusiveMatrix()
        self.inv = dag.inclusiveMatrixInverse()
        # 八分木はオブジェクト空間で作る。create() にワールド行列を渡すと
        # 二重に掛かった結果を返してくるので、問い合わせ側で変換する。
        self.isect.create(dag.node())
        self.cb_ids = []
        self.valid = True
        # 元のノードが消えた八分木を引くと Maya ごと落ちる。
        # シーンを開き直すと同名の別ノードが出来るので名前では守れない。
        self.handle = om.MObjectHandle(dag.node())

    def alive(self):
        return (self.valid and self.handle.isValid()
                and self.handle.isAlive())

    def kill(self):
        self.valid = False
        self.isect = None
        for cb in self.cb_ids:
            try:
                om.MMessage.removeCallback(cb)
            except Exception:
                pass
        self.cb_ids = []


def _invalidate_mesh_accel(mesh_name=None):
    """八分木キャッシュを捨てる。*mesh_name* 省略で全部。"""
    import sys
    bulk = sys.modules.get(__package__ + '.maya_projector')
    if bulk is not None: bulk.clear(mesh_name)
    names = ([mesh_name] if mesh_name is not None
             else list(_ISECT_CACHE.keys()))
    for nm in names:
        acc = _ISECT_CACHE.pop(nm, None)
        if acc is not None:
            acc.kill()


def _get_mesh_accel(mesh_name, dag):
    """*mesh_name* の八分木を返す。作れなければ None。"""
    acc = _ISECT_CACHE.get(mesh_name)
    if acc is not None:
        if acc.alive():
            return acc
        _invalidate_mesh_accel(mesh_name)
    try:
        acc = _MeshAccel(dag)
    except Exception:
        return None

    # メッシュが変形 / 再構築されたら捨てる
    def _on_dirty(*_a):
        a = _ISECT_CACHE.pop(mesh_name, None)
        if a is not None:
            a.valid = False

    try:
        node = dag.node()
        acc.cb_ids.append(
            om.MNodeMessage.addNodeDirtyCallback(node, _on_dirty))
        # ワールド行列が変わっても八分木の座標系がずれる
        tr = om.MDagPath(dag)
        tr.pop()
        acc.cb_ids.append(
            om.MNodeMessage.addNodeDirtyCallback(tr.node(), _on_dirty))
    except Exception:
        pass

    _ISECT_CACHE[mesh_name] = acc
    return acc


def _accel_for(mesh_fn, mesh_dag=None):
    """MFnMesh から八分木を引く。キャッシュヒット時は DAG を作らない。"""
    try:
        name = mesh_fn.fullPathName()
    except Exception:
        return None
    if not name:
        return None
    acc = _ISECT_CACHE.get(name)
    if acc is not None:
        if acc.alive():
            return acc
        _invalidate_mesh_accel(name)
    if mesh_dag is None:
        try:
            sel = om.MSelectionList()
            sel.add(name)
            mesh_dag = om.MDagPath()
            sel.getDagPath(0, mesh_dag)
            mesh_dag.extendToShape()
        except Exception:
            return None
    return _get_mesh_accel(name, mesh_dag)


def _accel_closest(acc, world_pt):
    """八分木でワールド座標の最近接点を引く。

    Returns
    -------
    tuple
        ``(world_pos, face_idx)``。
    """
    p = om.MPoint(world_pt[0], world_pt[1], world_pt[2]) * acc.inv
    pom = om.MPointOnMesh()
    acc.isect.getClosestPoint(p, pom)
    q = pom.getPoint()
    # MPointOnMesh はオブジェクト空間で返るのでワールドへ戻す
    w = om.MPoint(q.x, q.y, q.z) * acc.mat
    return [w.x, w.y, w.z], pom.faceIndex()


def _accel_closest_normal(acc, world_pt):
    """八分木でワールド座標の最近接点の法線を引く。"""
    p = om.MPoint(world_pt[0], world_pt[1], world_pt[2]) * acc.inv
    pom = om.MPointOnMesh()
    acc.isect.getClosestPoint(p, pom)
    n = pom.getNormal()
    # 法線は逆転置行列で変換する
    v = om.MVector(n.x, n.y, n.z).transformAsNormal(acc.mat)
    if v.length() > 1.0e-12:
        v.normalize()
    return [v.x, v.y, v.z]


def _closest_point_on_mesh(mesh_fn, mesh_dag, world_pt):
    """
    ワールド空間の点 world_pt をメッシュ面に投影し、
    (closest_world_pt, face_idx, bary_u, bary_v) を返す。
    """
    pt_in  = om.MPoint(world_pt[0], world_pt[1], world_pt[2])
    pt_out = om.MPoint()

    acc = _accel_for(mesh_fn, mesh_dag)
    if acc is not None:
        pos, face_idx = _accel_closest(acc, world_pt)
    else:
        face = om.MScriptUtil()
        face.createFromInt(0)
        face_ptr = face.asIntPtr()
        mesh_fn.getClosestPoint(pt_in, pt_out, om.MSpace.kWorld, face_ptr)
        face_idx = om.MScriptUtil.getInt(face_ptr)
        pos = [pt_out.x, pt_out.y, pt_out.z]

    # 最近接三角形で bary を計算
    #
    # ここで以前 getTriangles() を呼んでいたが、その結果は使われておらず
    # (bary は下の getPolygonVertices から作る)、しかもメッシュ全体の
    # 三角形リストを毎回コピーするため 1 回の投影が O(面数) になっていた。
    bary = _closest_bary_on_face(pos, mesh_fn, face_idx)
    return pos, face_idx, bary


def _closest_point_pos_only(mesh_fn, world_pt):
    """メッシュ上の最近点の座標だけを返す (face/bary は求めない)。

    測地線の緩和やフィッティングの誤差評価では座標しか使わないのに、
    ``_closest_point_on_mesh`` は毎回 getPolygonVertices と頂点数ぶんの
    getPoint を呼んで重心座標を組み立てていた。この関数はそれを省く。
    """
    acc = _accel_for(mesh_fn)
    if acc is not None:
        return _accel_closest(acc, world_pt)[0]
    pt_in = om.MPoint(world_pt[0], world_pt[1], world_pt[2])
    pt_out = om.MPoint()
    mesh_fn.getClosestPoint(pt_in, pt_out, om.MSpace.kWorld)
    return [pt_out.x, pt_out.y, pt_out.z]


def _get_normal_at_point(mesh_fn, world_pt):
    """メッシュ上の最近点での面法線を返す (API 1)。"""
    acc = _accel_for(mesh_fn)
    if acc is not None:
        return _accel_closest_normal(acc, world_pt)
    pt_in = om.MPoint(world_pt[0], world_pt[1], world_pt[2])
    normal = om.MVector()
    pt_out = om.MPoint()
    face   = om.MScriptUtil()
    face.createFromInt(0)
    face_ptr = face.asIntPtr()
    mesh_fn.getClosestPointAndNormal(
        pt_in, pt_out, normal, om.MSpace.kWorld, face_ptr)
    return [normal.x, normal.y, normal.z]

def _closest_bary_on_face(proj_pt, mesh_fn, face_idx):
    """
    face の多角形を fan 三角分割し、proj_pt の重心座標を返す。
    Returns list of (vertex_idx, weight) summing to 1.0.
    """
    vtx_ids = om.MIntArray()
    mesh_fn.getPolygonVertices(face_idx, vtx_ids)
    n = vtx_ids.length()
    if n < 3:
        return [(vtx_ids[0], 1.0)]

    pts = []
    for i in range(n):
        p = om.MPoint()
        mesh_fn.getPoint(vtx_ids[i], p, om.MSpace.kWorld)
        pts.append([p.x, p.y, p.z])

    px, py, pz = proj_pt

    def _bary3(p, a, b, c):
        from Aru_RetopoTool.editor.curvenet.curve_net_data import _v3_sub, _v3_cross, _v3_len, _v3_dot
        v0 = _v3_sub(b, a); v1 = _v3_sub(c, a); v2 = _v3_sub(p, a)
        d00 = _v3_dot(v0, v0); d01 = _v3_dot(v0, v1); d11 = _v3_dot(v1, v1)
        d20 = _v3_dot(v2, v0); d21 = _v3_dot(v2, v1)
        D   = d00 * d11 - d01 * d01
        if abs(D) < 1e-14:
            return None
        v = (d11 * d20 - d01 * d21) / D
        w = (d00 * d21 - d01 * d20) / D
        u = 1.0 - v - w
        if u >= -0.05 and v >= -0.05 and w >= -0.05:
            return u, v, w
        return None

    best = None
    best_score = -1.0
    root = pts[0]
    for i in range(1, n - 1):
        b_tri = _bary3(proj_pt, root, pts[i], pts[i+1])
        if b_tri is not None:
            score = min(b_tri)
            if score > best_score:
                best_score = score
                best = (vtx_ids[0], b_tri[0],
                        vtx_ids[i], b_tri[1],
                        vtx_ids[i+1], b_tri[2])

    if best is None:
        # fallback: 最近傍頂点に重み 1
        min_d = 1e30
        best_v = vtx_ids[0]
        for i, p in enumerate(pts):
            d = math.sqrt((p[0]-px)**2 + (p[1]-py)**2 + (p[2]-pz)**2)
            if d < min_d:
                min_d = d
                best_v = vtx_ids[i]
        return [(int(best_v), 1.0)]

    v0, w0, v1, w1, v2, w2 = best
    return [(int(v0), w0), (int(v1), w1), (int(v2), w2)]


# ===========================================================================
# ユーティリティ (context / menu 等から参照される共有ヘルパー)
# ===========================================================================

def _find_shape_node(node_or_xf):
    """トランスフォームまたはシェイプ名から retopoGuideNode シェイプ名を返す。"""
    if cmds.objectType(node_or_xf) == kPluginNodeName:
        return node_or_xf
    shapes = cmds.listRelatives(node_or_xf, shapes=True,
                                type=kPluginNodeName) or []
    return shapes[0] if shapes else None


def _world_to_screen(world_pt):
    """ワールド座標 → スクリーン座標 (sx, sy) を返す。失敗時は None。"""
    try:
        view = omui.M3dView.active3dView()
        pt = om.MPoint(world_pt[0], world_pt[1], world_pt[2])
        x_util = om.MScriptUtil()
        y_util = om.MScriptUtil()
        x_ptr = x_util.asShortPtr()
        y_ptr = y_util.asShortPtr()
        view.worldToView(pt, x_ptr, y_ptr)
        return (x_util.getShort(x_ptr), y_util.getShort(y_ptr))
    except Exception:
        return None


def _world_to_screen_many(world_points):
    from .maya_screen import project
    result=project(world_points)
    return _world_to_screen_many_python(world_points) if result is None else result


def _world_to_screen_many_python(world_points):
    """Project a brush event using Maya's exact short-pixel conversion.

    The view and output pointers live only for this call, so subsequent events
    always observe the current camera. Keep owners alive while pointers are used.
    """
    try:
        view = omui.M3dView.active3dView()
        x_util = om.MScriptUtil(); y_util = om.MScriptUtil()
        x_ptr = x_util.asShortPtr(); y_ptr = y_util.asShortPtr()
    except Exception:
        return [_world_to_screen(p) for p in world_points]
    result = []
    for p in world_points:
        try:
            # Match the scalar function even when worldToView returns False.
            view.worldToView(om.MPoint(p[0], p[1], p[2]), x_ptr, y_ptr)
            result.append((x_util.getShort(x_ptr), y_util.getShort(y_ptr)))
        except Exception:
            result.append(None)
    return result


def _get_net_data_positions(shape_node):
    """shape_node から最終位置リストと RetopoGuideData を返す。"""
    cn = RetopoGuideAccessor(shape_node).read()
    if not cn.positions:
        return [], cn
    positions = [list(p) for p in cn.positions]
    try:
        n = len(positions)
        for i in range(n):
            try:
                dx = cmds.getAttr("{}.controlPoints[{}].xValue".format(
                    shape_node, i))
                dy = cmds.getAttr("{}.controlPoints[{}].yValue".format(
                    shape_node, i))
                dz = cmds.getAttr("{}.controlPoints[{}].zValue".format(
                    shape_node, i))
                if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
                    positions[i] = [positions[i][0] + dx,
                                    positions[i][1] + dy,
                                    positions[i][2] + dz]
            except Exception:
                pass
    except Exception:
        pass
    return positions, cn


# ===========================================================================
# スプライン操作ヘルパー
# ===========================================================================

# ===========================================================================

def _get_net_transform(node_name: str) -> str:
    """retopoGuideNode シェイプの親トランスフォーム名を返す。"""
    if cmds.objectType(node_name) == kPluginNodeName:
        parents = cmds.listRelatives(node_name, parent=True) or []
        if parents:
            return parents[0]
    return node_name


def _get_loc_group(parent_xf: str) -> str:
    """旧ロケーターグループを取得する (後方互換)。"""
    grp_name = parent_xf + _LOC_GRP_SUFFIX
    if cmds.objExists(grp_name):
        return grp_name
    return ""


def is_pose_driven(node: str) -> bool:
    """カーブネットがデフォーマ (skinCluster 等) で駆動されているか。

    駆動されている場合 ``controlPoints`` は **ポーズ空間の補正 (PSD)** で
    あり、レスト形状 (``netData``) へ焼き込んではならない。焼き込むと
    補正がレストの一部になり、バインドポーズでも常に効いてしまう。
    """
    try:
        shape = _find_shape_node(node) or node
        if not cmds.objExists(shape):
            return False
        return bool(cmds.listConnections(
            "{}.inSurface".format(shape), source=True, destination=False))
    except Exception:
        return False


def _reset_control_points(node: str, n: int) -> None:
    """Reset only nonzero tweaks, batching adjacent elements (caller owns Undo)."""
    if n<=0:return
    try:
        selection=om2.MSelectionList();selection.add(node)
        plug=om2.MFnDependencyNode(selection.getDependNode(0)).findPlug('controlPoints',False)
        existing=[i for i in plug.getExistingArrayAttributeIndices() if i<n]
        if len(existing)<n/4:
            indices=[i for i in existing if any(v!=0. for v in cmds.getAttr("{}.controlPoints[{}]".format(node,i))[0])]
        else:
            values=cmds.getAttr("{}.controlPoints[0:{}]".format(node,n-1))
            if values is None or len(values)!=n:raise ValueError('Unexpected tweak array size')
            indices=[i for i,value in enumerate(values) if any(component!=0. for component in value)]
    except (RuntimeError,ValueError,TypeError):
        indices=list(range(n))
    ranges=[]
    for i in indices:
        if ranges and ranges[-1][1]+1==i:ranges[-1][1]=i
        else:ranges.append([i,i])
    for first,last in ranges:
        try:
            cmds.setAttr("{}.controlPoints[{}:{}]".format(node,first,last),
                         *([0.]*((last-first+1)*3)),type='double3')
            continue
        except RuntimeError:
            pass
        # Preserve partial reset behavior on locked/connected components.
        for i in range(first,last+1):
            try:
                cmds.setAttr("{}.controlPoints[{}].xValue".format(node,i),0.)
                cmds.setAttr("{}.controlPoints[{}].yValue".format(node,i),0.)
                cmds.setAttr("{}.controlPoints[{}].zValue".format(node,i),0.)
            except Exception:
                pass


def bake_control_points(node_name: str = "") -> bool:
    """controlPoints デルタを netData に焼き込み、CP を 0 にする (パブリック API)。

    スキンクラスターバインド前や、CP の数値を 0 に揃えたいときに使用する。
    位置は netData に保持されるため見た目は変わらない。

    Parameters
    ----------
    node_name : retopoGuideNode のシェイプ名またはトランスフォーム名。
                省略時は optionVar / アクティブ選択から自動取得。

    Returns
    -------
    bool : 変更があれば True。
    """
    shape = ""
    if node_name:
        shape = _find_shape_node(node_name) or node_name
    else:
        # optionVar → 選択 の順で探す
        ov_node = cmds.optionVar(q="retopoGuideContext_node") or ""
        if ov_node:
            shape = _find_shape_node(ov_node) or ov_node
        if not shape or not cmds.objExists(shape):
            for n in (cmds.ls(selection=True) or []):
                candidate = _find_shape_node(n) or n
                if cmds.objExists(candidate) and cmds.nodeType(candidate) == "retopoGuideNode":
                    shape = candidate
                    break

    if not shape or not cmds.objExists(shape):
        om.MGlobal.displayWarning("[RetopoGuide] bake_control_points: ノードが見つかりません。")
        return False

    cmds.undoInfo(openChunk=True, chunkName="BakeRetopoGuideCPs")
    try:
        from Aru_RetopoTool.editor.curvenet.curve_net_context import _sync_ep_positions_back
        changed = _sync_ep_positions_back(shape)
    finally:
        cmds.undoInfo(closeChunk=True)

    if changed:
        om.MGlobal.displayInfo(
            "[RetopoGuide] '{}' の CP を netData にベイクしました。".format(shape))
    else:
        om.MGlobal.displayInfo(
            "[RetopoGuide] '{}' の CP は 0 のためベイク不要でした。".format(shape))
    return changed


# ---------------------------------------------------------------------------
# スプラインをメッシュにフィット
# ---------------------------------------------------------------------------

def fit_splines_to_mesh(node_name="", n_iterations=3, handle_weight=0.5):
    """全スプラインのカーブをメッシュ表面にフィットさせる。

    論文: 「タンジェントハンドルをサーフェス法線に垂直に初期化する」
    ハンドルを EP の接平面に拘束し、接平面内での方向と長さを最適化して
    カーブがメッシュ面に沿うようにする。

    アルゴリズム:
        1. EP をメッシュに投影、法線を取得
        2. 各スプラインを密サンプリング → メッシュ投影
        3. ハンドル方向を EP の接平面に拘束
        4. 接平面内で方向・長さを最適化（1D 最小二乗）
        5. 反復的に収束（サンプル→投影→最適化）

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択/optionVar から取得。
    n_iterations : int
        フィッティング反復回数 (多いほど精密)。
    handle_weight : float
        ハンドル調整のブレンド強さ (0.0-1.0)。

    Returns
    -------
    bool : 変更があった場合 True。
    """
    import numpy as np

    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        om.MGlobal.displayWarning(
            "[RetopoGuide] retopoGuideNode が見つかりません")
        return False

    mesh_name = cmds.getAttr("{}.meshName".format(shape)) or ""
    if not mesh_name or not cmds.objExists(mesh_name):
        om.MGlobal.displayWarning(
            "[RetopoGuide] メッシュが設定されていません")
        return False

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()
    if not cn.positions or not cn.splines:
        return False

    mesh_fn, mesh_dag = _get_mesh_fn(mesh_name)

    def _project(pt):
        """ワールド座標をメッシュに投影して (位置, 法線) を返す。"""
        proj, face_idx, bary = _closest_point_on_mesh(mesh_fn, mesh_dag, pt)
        normal = _get_normal_at_point(mesh_fn, proj)
        return np.array(proj), np.array(normal)

    def _tangent_plane_project(vec, normal):
        """ベクトルを法線の接平面に投影して正規化。"""
        n = np.array(normal)
        v = np.array(vec) - np.dot(vec, n) * n
        vlen = float(np.linalg.norm(v))
        if vlen < 1e-12:
            return None
        return v / vlen

    # --- EP をメッシュに投影、法線をキャッシュ ---
    ep_set = cn.ep_indices
    ep_normals = {}  # ep_idx -> normal (unit)
    for ep_idx in ep_set:
        proj_pos, proj_n = _project(cn.positions[ep_idx])
        cn.positions[ep_idx] = proj_pos.tolist()
        nlen = float(np.linalg.norm(proj_n))
        ep_normals[ep_idx] = proj_n / nlen if nlen > 1e-12 else np.array([0., 1., 0.])

    # --- 反復フィッティング ---
    N_SAMPLE = 40  # 密サンプリングで精度を上げる
    for _it in range(n_iterations):
        for si, sp in enumerate(cn.splines):
            if len(sp) < 4:
                continue
            if cn.spline_has_manual_handle(si):
                continue
            ep0_idx, h0_idx, h1_idx, ep1_idx = sp[0], sp[1], sp[2], sp[3]
            p0 = np.array(cn.positions[ep0_idx], dtype=float)
            p1 = np.array(cn.positions[h0_idx], dtype=float)
            p2 = np.array(cn.positions[h1_idx], dtype=float)
            p3 = np.array(cn.positions[ep1_idx], dtype=float)
            n0 = ep_normals.get(ep0_idx, np.array([0., 1., 0.]))
            n3 = ep_normals.get(ep1_idx, np.array([0., 1., 0.]))

            # EP間の方向ベクトル
            seg = p3 - p0
            seg_len = float(np.linalg.norm(seg))
            if seg_len < 1e-12:
                continue

            # --- 測地線的タンジェント推定 ---
            # 弦方向の接平面投影ではなく、EP 近傍のメッシュ投影点から
            # 実際の曲面沿い方向を推定する。
            # EP0 近傍 (t≈0.1) とEP1 近傍 (t≈0.9) の点をメッシュに投影し、
            # EP→投影点の方向を接平面に投影してタンジェントにする。
            _t_near = 0.1
            _u_near = 1.0 - _t_near
            pt_near0 = (_u_near**3 * p0 + 3 * _u_near**2 * _t_near * p1
                        + 3 * _u_near * _t_near**2 * p2
                        + _t_near**3 * p3)
            proj_near0, _ = _project(pt_near0.tolist())

            _t_far = 0.9
            _u_far = 1.0 - _t_far
            pt_near3 = (_u_far**3 * p0 + 3 * _u_far**2 * _t_far * p1
                        + 3 * _u_far * _t_far**2 * p2
                        + _t_far**3 * p3)
            proj_near3, _ = _project(pt_near3.tolist())

            # EP0 → 近傍投影点の方向を接平面に投影
            dir0 = proj_near0 - p0
            tang0 = _tangent_plane_project(dir0, n0)
            if tang0 is None:
                # フォールバック: 弦方向の接平面投影
                tang0 = _tangent_plane_project(seg, n0)
            if tang0 is None:
                tang0 = seg / seg_len

            # EP1 → 近傍投影点の方向を接平面に投影
            dir3 = proj_near3 - p3
            tang3 = _tangent_plane_project(dir3, n3)
            if tang3 is None:
                tang3 = _tangent_plane_project(-seg, n3)
            if tang3 is None:
                tang3 = -seg / seg_len

            # 現在のハンドル長を取得（接線方向成分を保持）
            cur_d0 = float(np.dot(p1 - p0, tang0))
            cur_d3 = float(np.dot(p2 - p3, tang3))
            d_default = seg_len / 3.0
            if cur_d0 < 1e-6:
                cur_d0 = d_default
            if cur_d3 < 1e-6:
                cur_d3 = d_default

            # ハンドル長の上下限
            d_min = seg_len * 0.05
            d_max = seg_len * 0.8

            # --- スプラインをサンプリングしてメッシュに投影 ---
            projected = []
            params = []
            for k in range(1, N_SAMPLE):
                t = k / N_SAMPLE
                u = 1.0 - t
                pt = (u**3 * p0 + 3 * u**2 * t * (p0 + cur_d0 * tang0)
                      + 3 * u * t**2 * (p3 + cur_d3 * tang3)
                      + t**3 * p3)
                proj_pt, _ = _project(pt.tolist())
                projected.append(proj_pt)
                params.append(t)

            # --- 接平面内でハンドル長 (d0, d3) を最適化 ---
            # B(t) = (1-t)^3 P0 + 3(1-t)^2 t [P0 + d0*tang0]
            #       + 3(1-t) t^2 [P3 + d3*tang3] + t^3 P3
            # 残差 = proj_k - B(t_k) を d0, d3 について線形化:
            #   ∂B/∂d0 = 3(1-t)^2 t * tang0
            #   ∂B/∂d3 = 3(1-t) t^2 * tang3
            A = np.zeros((len(params) * 3, 2))
            b_rhs = np.zeros(len(params) * 3)
            for k, t in enumerate(params):
                u = 1.0 - t
                # 現在のカーブ点（d0, d3 = cur_d0, cur_d3）
                B_k = (u**3 * p0 + 3 * u**2 * t * (p0 + cur_d0 * tang0)
                       + 3 * u * t**2 * (p3 + cur_d3 * tang3)
                       + t**3 * p3)
                residual = projected[k] - B_k
                for ax in range(3):
                    row = k * 3 + ax
                    A[row, 0] = 3.0 * u * u * t * tang0[ax]
                    A[row, 1] = 3.0 * u * t * t * tang3[ax]
                    b_rhs[row] = residual[ax]

            AtA = A.T @ A
            det = AtA[0, 0] * AtA[1, 1] - AtA[0, 1] * AtA[1, 0]
            if abs(det) < 1e-12:
                continue
            Atb = A.T @ b_rhs
            dd0 = (AtA[1, 1] * Atb[0] - AtA[0, 1] * Atb[1]) / det
            dd1 = (AtA[0, 0] * Atb[1] - AtA[1, 0] * Atb[0]) / det

            new_d0 = np.clip(cur_d0 + handle_weight * dd0, d_min, d_max)
            new_d3 = np.clip(cur_d3 + handle_weight * dd1, d_min, d_max)

            # ハンドルを接平面拘束位置に設定
            new_p1 = p0 + new_d0 * tang0
            new_p2 = p3 + new_d3 * tang3

            # ハンドルをメッシュに最終投影
            proj1, _ = _project(new_p1.tolist())
            proj2, _ = _project(new_p2.tolist())
            cn.positions[h0_idx] = proj1.tolist()
            cn.positions[h1_idx] = proj2.tolist()

            # 次の反復用にハンドル長を更新
            cur_d0 = new_d0
            cur_d3 = new_d3

    _commit_net_data(shape, cn)
    _dirty_shape_view()
    om.MGlobal.displayInfo(
        "[RetopoGuide] {} スプラインをメッシュにフィットしました。".format(
            len(cn.splines)))
    return True


# ---------------------------------------------------------------------------
# スキンウェイト編集ヘルパー
# ---------------------------------------------------------------------------
# Maya の Component Editor (Smooth Skins タブ) は retopoGuideNode では
# 「選択している CV だけを表示する」ことができず、常に全 CV が行として
# 並んでしまう。
#
# 計測 (mayabatch) で判明した内訳:
#   * 選択自体は正常     — ls(sl) は transform1.vtx[1:2] 等を正しく返す
#   * skinPercent も正常 — シェイプ名/トランスフォーム名どちらでも動く
#   * MFnSkinCluster.getWeights(dagPath, component) も正常
#   * MItGeometry(dagPath) だけが kPluginShape を受け付けず
#     (kInvalidParameter「入力したパスは無効です」)、
#     acceptsGeometryIterator() が呼ばれる前に Maya 内部で弾かれる
#
# Component Editor は選択コンポーネント → ウェイト行の対応付けに
# MItGeometry を使うため、対応付けに失敗して skinCluster.weightList の
# 全インデックス (= 全 CV) を列挙してしまう。これは Maya 側の制約であり
# プラグインからは回避できない。
#
# 代替として以下のヘルパーと専用 UI (ui/skin_weight_ui.py) を使用する。

def get_selected_cv_indices(node_name=""):
    """選択中のコンポーネントから retopoGuide の CV インデックスを取り出す。

    Returns
    -------
    (shape, list[int])
        shape が解決できない場合は ("", [])。
    """
    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        return "", []

    names = {shape, shape.split("|")[-1]}
    for tr in (cmds.listRelatives(shape, parent=True, fullPath=True) or []):
        names.add(tr)
        names.add(tr.split("|")[-1])

    n_cvs = _get_cv_count(shape)
    out = []
    for c in (cmds.ls(selection=True, flatten=True) or []):
        if "[" not in c:
            continue
        obj, _, rest = c.partition(".")
        if obj not in names:
            continue
        attr = rest.split("[")[0]
        if attr not in ("vtx", "cv", "controlPoints", "pt"):
            continue
        try:
            idx = int(rest.split("[")[1].rstrip("]"))
        except (IndexError, ValueError):
            continue
        if 0 <= idx < n_cvs:
            out.append(idx)
    return shape, sorted(set(out))


def get_skin_weights(node_name="", cv_indices=None):
    """選択中 or 指定の retopoGuideNode に接続された skinCluster のウェイトを返す。

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択/optionVar から取得。
    cv_indices : list[int] or None
        取得対象の CV。None なら全 CV。

    Returns
    -------
    dict or None
        {cv_index: {joint_name: weight, ...}, ...}
        skinCluster が見つからない場合は None。
    """
    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return None

    sc = _find_skincluster(shape)
    if not sc:
        om.MGlobal.displayWarning(
            "[RetopoGuide] skinCluster が接続されていません: {}".format(shape))
        return None

    influences = cmds.skinCluster(sc, q=True, inf=True) or []
    n_cvs = _get_cv_count(shape)
    if n_cvs == 0:
        return {}

    if cv_indices is None:
        cv_indices = range(n_cvs)

    # skinPercent を CV ごとに呼ぶと 400 点で 2 秒かかる。プラグ直読みなら数 ms。
    table, inf_names = _bulk_skin_weights(shape, sc)
    if table is not None:
        result = {}
        for i in cv_indices:
            if not (0 <= i < n_cvs):
                continue
            w = {}
            for li, v in (table.get(i) or {}).items():
                name = inf_names.get(li)
                if name is not None and abs(v) > 1e-9:
                    w[name] = v
            result[i] = w
        return result

    result = {}
    for i in cv_indices:
        if not (0 <= i < n_cvs):
            continue
        # シェイプ名で直接アドレス → matchComponent() が解決する
        comp = "{}.vtx[{}]".format(shape, i)
        vals = cmds.skinPercent(sc, comp, q=True, v=True) or []
        w = {}
        for ji, v in enumerate(vals):
            if ji < len(influences) and abs(v) > 1e-9:
                w[influences[ji]] = v
        result[i] = w
    return result


def _skin_fn_and_path(shape, sc):
    import maya.api.OpenMaya as _om2
    import maya.api.OpenMayaAnim as _oma
    sel = _om2.MSelectionList()
    sel.add(sc)
    fn = _oma.MFnSkinCluster(sel.getDependNode(0))
    dsel = _om2.MSelectionList()
    dsel.add(shape)
    return fn, dsel.getDagPath(0)


def _bulk_skin_weights(shape, sc):
    """weightList を直接読んで ``({cv: {inf_logical: w}}, {inf_logical: name})`` を返す。

    ``MFnSkinCluster.getWeights`` はプラグインシェイプで追加直後の CV を 0 で
    返すので使わない。失敗は (None, {})。
    """
    try:
        fn, _path = _skin_fn_and_path(shape, sc)
        inf_names = {}
        for p in fn.influenceObjects():
            inf_names[int(fn.indexForInfluenceObject(p))] = p.partialPathName()
        wl = fn.findPlug("weightList", False)
        table = {}
        for pi in range(wl.evaluateNumElements()):
            e = wl.elementByPhysicalIndex(pi)
            wts = e.child(0)
            row = {}
            for pj in range(wts.evaluateNumElements()):
                w = wts.elementByPhysicalIndex(pj)
                v = w.asDouble()
                if abs(v) > 1e-12:
                    row[w.logicalIndex()] = v
            table[e.logicalIndex()] = row
        return table, inf_names
    except Exception:
        return None, {}


def set_skin_weights_bulk(shape, weights, sc=None, normalize=True, allow_zero=False):
    """``{cv: {joint: w}}`` を一括で skinCluster に書き込む。書いた CV 数を返す。

    指定の無い CV は現在値のまま。skinPercent を CV ごとに呼ぶより数百倍速い。
    *allow_zero* なら空 dict の CV は全ゼロ行として書く (Undo での復元用)。
    """
    import maya.api.OpenMaya as _om2
    if not weights:
        return 0
    sc = sc or _find_skincluster(shape)
    if not sc:
        return 0
    table, inf_names = _bulk_skin_weights(shape, sc)
    if table is None or not inf_names:
        # フォールバック: 従来の skinPercent
        n = 0
        for i, w in weights.items():
            tv = [(j, v) for j, v in w.items() if abs(v) > 1e-9]
            if not tv:
                continue
            try:
                cmds.skinPercent(sc, "{}.vtx[{}]".format(shape, int(i)),
                                 transformValue=tv, normalize=normalize)
                n += 1
            except Exception:
                pass
        return n
    inf_index = {}
    for li, name in inf_names.items():
        inf_index[name] = li
        inf_index[name.split("|")[-1]] = li
    n_cv = _get_cv_count(shape)
    n_set = 0
    changed = {}
    for i, w in weights.items():
        i = int(i)
        if not (0 <= i < n_cv) or (not w and not allow_zero):
            continue
        row = {}
        for j, v in (w or {}).items():
            li = inf_index.get(j)
            if li is None:
                li = inf_index.get(str(j).split("|")[-1])
            if li is not None:
                row[li] = row.get(li, 0.0) + float(v)
        tot = sum(row.values())
        if normalize and tot > 1e-12:
            row = {li: v / tot for li, v in row.items()}
        changed[i] = row
        n_set += 1
    if not n_set:
        return 0
    try:
        fn, path = _skin_fn_and_path(shape, sc)
        # setWeights の influenceIndices は「influenceObjects() の並びの物理番号」。
        # weightList のキー (matrix の論理番号) は疎で 82 本なら 151 まで飛ぶことがあり、
        # そのまま渡すと kInvalidParameter になる。
        phys_of_logical = {}
        for k, p in enumerate(fn.influenceObjects()):
            phys_of_logical[int(fn.indexForInfluenceObject(p))] = k
        phys_ids = sorted(phys_of_logical[li] for li in inf_names if li in phys_of_logical)
        col = {pi: k for k, pi in enumerate(phys_ids)}
        cvs = sorted(changed)
        flat = [0.0] * (len(cvs) * len(phys_ids))
        for r, i in enumerate(cvs):
            for li, v in changed[i].items():
                pi = phys_of_logical.get(li)
                if pi is not None:
                    flat[r * len(phys_ids) + col[pi]] = v
        comp_fn = _om2.MFnSingleIndexedComponent()
        comp = comp_fn.create(_om2.MFn.kMeshVertComponent)
        comp_fn.addElements(cvs)
        fn.setWeights(path, comp, _om2.MIntArray(phys_ids),
                      _om2.MDoubleArray(flat), False)
    except Exception as exc:
        om.MGlobal.displayWarning("[RetopoGuide] setWeights failed: %s" % exc)
        return 0
    return n_set


def set_skin_weight(cv_indices, joint, weight, node_name="", normalize=True):
    """指定 CV のスキンウェイトを設定する。

    Parameters
    ----------
    cv_indices : int or list[int]
        対象 CV インデックス。
    joint : str
        ジョイント名。
    weight : float
        設定するウェイト値 (0.0–1.0)。
    node_name : str
        retopoGuideNode 名。空なら選択/optionVar から取得。
    normalize : bool
        True の場合、他ジョイントとの合計が 1.0 になるよう正規化。
    """
    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return

    sc = _find_skincluster(shape)
    if not sc:
        om.MGlobal.displayWarning(
            "[RetopoGuide] skinCluster が接続されていません: {}".format(shape))
        return

    if isinstance(cv_indices, int):
        cv_indices = [cv_indices]

    comps = ["{}.vtx[{}]".format(shape, i) for i in cv_indices]
    nw = 1 if normalize else 0
    cmds.skinPercent(sc, *comps, tv=(joint, weight), nrm=nw)
    om.MGlobal.displayInfo(
        "[RetopoGuide] skinWeight: cv{} → {} = {:.4f}".format(
            cv_indices, joint, weight))


def print_skin_weights(node_name=""):
    """選択中の retopoGuideNode のスキンウェイトをスクリプトエディタに出力する。"""
    weights = get_skin_weights(node_name)
    if weights is None:
        return
    for idx in sorted(weights.keys()):
        w = weights[idx]
        if w:
            parts = ["{}={:.4f}".format(j, v) for j, v in sorted(w.items())]
            print("  cv[{}]: {}".format(idx, "  ".join(parts)))


# ---------------------------------------------------------------------------
# 新規 CV のスキンウェイト継承
# ---------------------------------------------------------------------------

def fill_missing_skin_weights(shape, cn=None, quiet=True):
    """ウェイトを持たない CV (追加直後の点) に周りからウェイトを継承させる。

    * EP: スプラインで繋がる既知の EP から距離の逆数でブレンド。
      隣がすべて新規なら最も近い既知 EP をコピー。
    * ハンドル: 自分の EP をコピー (retopoGuideSkinCluster の epMap と同じ契約)。

    ウェイトはインデックスではなく「空かどうか」で判定するので、再採番の後でも安全。
    設定した CV 数を返す。
    """
    sc = _find_skincluster(shape)
    if not sc:
        return 0
    if cn is None:
        cn = RetopoGuideAccessor(shape).read()
    n = len(cn.positions)
    if n == 0:
        return 0
    # skinPercent は skinCluster が今見ている点数でコンポーネントを検証するので、
    # Orig の新しい netData を入力に一度評価させておく。
    try:
        cmds.dgeval(sc + ".outputGeometry[0]")
    except Exception:
        pass
    weights = get_skin_weights(shape) or {}

    def _has(i):
        w = weights.get(i)
        return bool(w) and sum(abs(v) for v in w.values()) > 1e-6

    missing = [i for i in range(n) if not _has(i)]
    if not missing:
        return 0

    handle_ep = {}
    adj = {}
    for sp in cn.splines:
        handle_ep[sp[1]] = sp[0]
        handle_ep[sp[2]] = sp[3]
        adj.setdefault(sp[0], set()).add(sp[3])
        adj.setdefault(sp[3], set()).add(sp[0])
    known_eps = [i for i in adj if _has(i)]

    def _dist(a, b):
        pa, pb = cn.positions[a], cn.positions[b]
        return math.sqrt(sum((pa[k] - pb[k]) ** 2 for k in range(3)))

    def _blend(srcs):
        acc = {}
        tot = 0.0
        for j, wgt in srcs:
            for jt, v in weights[j].items():
                acc[jt] = acc.get(jt, 0.0) + v * wgt
            tot += wgt
        if tot <= 0.0:
            return {}
        return {jt: v / tot for jt, v in acc.items() if abs(v / tot) > 1e-9}

    filled = {}
    # EP を先に埋める
    for i in missing:
        if i in handle_ep or i not in adj:
            continue
        nbrs = [j for j in adj.get(i, ()) if _has(j)]
        if nbrs:
            filled[i] = _blend([(j, 1.0 / max(_dist(i, j), 1e-9)) for j in nbrs])
        elif known_eps:
            j = min(known_eps, key=lambda k: _dist(i, k))
            filled[i] = dict(weights[j])
    for i, w in filled.items():
        weights[i] = w
    # ハンドルは自分の EP をコピー
    for i in missing:
        ep = handle_ep.get(i)
        if ep is not None and _has(ep):
            filled[i] = dict(weights[ep])
    # どこにも繋がらない孤立点は最近傍の既知 EP
    for i in missing:
        if i in filled or not known_eps:
            continue
        j = min(known_eps, key=lambda k: _dist(i, k))
        filled[i] = dict(weights[j])

    n_set = set_skin_weights_bulk(shape, filled, sc=sc, normalize=True)
    if n_set and not quiet:
        om.MGlobal.displayInfo(
            "[RetopoGuide] %d 個の新規 CV にスキンウェイトを継承させました" % n_set)
    return n_set


# ---------------------------------------------------------------------------
# 孤立 CV の掃除
# ---------------------------------------------------------------------------

def count_orphan_cvs(node_name=""):
    """孤立 CV (どのスプラインからも参照されていない CV) の数を返す。"""
    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        return 0
    cn = RetopoGuideAccessor(shape).read()
    return len(cn.orphan_cv_indices())


def _trim_multi(plug, keep_count):
    """multi プラグの keep_count 以上の論理インデックスを削除する。"""
    try:
        idxs = cmds.getAttr(plug, multiIndices=True) or []
    except Exception:
        return
    for i in idxs:
        if i >= keep_count:
            try:
                cmds.removeMultiInstance("{}[{}]".format(plug, i), b=True)
            except Exception:
                pass


def cleanup_orphan_cvs(node_name="", quiet=False):
    """孤立 CV を削除して CV インデックスを詰める。

    ``_remove_ep`` / ``_merge_two_eps`` はスプラインだけを削除して
    ``positions`` を詰めないため、EP 削除やマージを繰り返すと
    どこからも参照されない CV が溜まる。孤立 CV は描画されないのに
    ``controlPoints`` / ``weightList`` の要素数を増やし続けるので、
    ここでまとめて掃除する。

    スキンウェイトと controlPoints は新しいインデックスに移し替える。

    Returns
    -------
    int
        削除した CV 数。
    """
    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return 0

    cn = RetopoGuideAccessor(shape).read()
    n_before = len(cn.positions)
    if not cn.orphan_cv_indices():
        if not quiet:
            om.MGlobal.displayInfo("[RetopoGuide] 孤立 CV はありません")
        return 0

    cmds.undoInfo(openChunk=True, chunkName="retopoGuideCleanupOrphanCVs")
    try:
        n_removed, _ = prune_orphan_cvs_and_write(shape, cn)
    finally:
        cmds.undoInfo(closeChunk=True)

    if not quiet:
        om.MGlobal.displayInfo(
            "[RetopoGuide] 孤立 CV を {} 個削除しました ({} → {})".format(
                n_removed, n_before, len(cn.positions)))
    return n_removed


def _influence_index_map(sc):
    """skinCluster のインフルエンス名 → matrix 論理インデックスの写像。

    ``weightList[cv].weights[i]`` の ``i`` は ``matrix[i]`` に対応する。
    ``skinCluster(q=True, inf=True)`` の並び順とは一致しないので、
    接続から引き直す。
    """
    out = {}
    conns = cmds.listConnections(
        "{}.matrix".format(sc), source=True, destination=False,
        plugs=True, connections=True) or []
    for k in range(0, len(conns) - 1, 2):
        dest, src = conns[k], conns[k + 1]
        try:
            idx = int(dest.split("[")[1].rstrip("]"))
        except (IndexError, ValueError):
            continue
        out[src.split(".")[0]] = idx
    return out


def _set_cv_weights_direct(sc, cv, weights, inf_map=None):
    """CV 1 点のスキンウェイトを weightList に直接書く。

    ``skinPercent`` は retopoGuideNode のようなプラグインシェイプに対して
    エラーを出さないまま何も書かないことがある (実測で確認)。
    ブレークで増えた CV にウェイトを配るにはこちらを使う。

    Parameters
    ----------
    sc : str
        skinCluster 名。
    cv : int
        CV インデックス。
    weights : dict[str, float]
        {インフルエンス名: ウェイト}。合計が 1 になるよう正規化して書く。
    inf_map : dict[str, int] or None
        :func:`_influence_index_map` の結果。省略時は都度取得する。
    """
    if inf_map is None:
        inf_map = _influence_index_map(sc)
    if not inf_map:
        return False

    vals = {}
    for name, w in (weights or {}).items():
        idx = inf_map.get(name)
        if idx is None:
            idx = inf_map.get(name.split("|")[-1])
        if idx is not None:
            vals[idx] = vals.get(idx, 0.0) + float(w)

    total = sum(vals.values())
    if total <= 1e-9:
        return False

    ok = False
    for idx in inf_map.values():
        try:
            cmds.setAttr("{}.weightList[{}].weights[{}]".format(sc, cv, idx),
                         vals.get(idx, 0.0) / total)
            ok = True
        except Exception:
            pass
    return ok


def break_selected_eps(node_name="", cv_indices=None):
    """選択中の EP を分離する (論文 §3「制御点のブレーク」)。

    ウェルドの逆操作。1 つの CV に集まっているスプラインを別々の CV へ
    切り離す。新しい CV は元と同じ位置に作られるので実行直後の見た目は
    変わらない。分離後にコンポーネントモードで引き離すと、交点だった
    場所を独立した端点にできる。

    元 EP のスキンウェイトは新しい CV へコピーする。これをしないと
    分離した点だけがバインドから外れて原点に飛ぶ。

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択 / optionVar から解決する。
    cv_indices : list[int] or None
        分離する CV。None なら選択中のコンポーネントを使う。

    Returns
    -------
    int
        新しく作られた CV の数。
    """
    if cv_indices is None:
        shape, cv_indices = get_selected_cv_indices(node_name)
    else:
        shape = _resolve_curvenet_shape(node_name)

    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return 0
    if not cv_indices:
        om.MGlobal.displayWarning(
            "[RetopoGuide] 分離する制御点を選択してください")
        return 0

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()

    # 分離できるのは 2 本以上のスプラインを共有している EP だけ
    targets = [i for i in cv_indices
               if 0 <= i < len(cn.positions)
               and len(cn.splines_at_ep(i)) >= 2]
    if not targets:
        om.MGlobal.displayWarning(
            "[RetopoGuide] 選択した制御点は共有されていないので分離できません")
        return 0

    # 元 EP のウェイトを先に読む (書き込み後はインデックスが変わりうる)
    sc = _find_skincluster(shape)
    src_weights = {}
    if sc:
        src_weights = get_skin_weights(shape, targets) or {}

    cmds.undoInfo(openChunk=True, chunkName="retopoGuideBreakEP")
    try:
        new_by_src = {}
        for cv in targets:
            new_cvs = cn.break_ep(cv)
            if new_cvs:
                new_by_src[cv] = new_cvs

        if not new_by_src:
            return 0

        remap = _commit_net_data(shape, cn)

        # スキンウェイトを元 EP から複製する
        if sc and src_weights:
            inf_map = _influence_index_map(sc)
            for src, new_cvs in new_by_src.items():
                w = src_weights.get(src) or {}
                if not any(abs(v) > 1e-9 for v in w.values()):
                    continue
                for new_cv in new_cvs:
                    idx = remap.get(new_cv, new_cv) if remap else new_cv
                    _set_cv_weights_direct(sc, idx, w, inf_map)
    finally:
        cmds.undoInfo(closeChunk=True)

    n_new = sum(len(v) for v in new_by_src.values())
    om.MGlobal.displayInfo(
        "[RetopoGuide] 制御点を分離しました ({} 点 → 新規 {} 点)。"
        "カーブの繋がりが変わるので Poisson デフォーマは再バインドが"
        "必要です".format(len(new_by_src), n_new))
    return n_new


def snapshot_curvenet(shape):
    """*shape* の編集状態を丸ごと控える (undo 用)。

    ``netData`` だけでは足りない。孤立 CV の掃除で CV が詰められると
    ``controlPoints`` と skinCluster ウェイトも張り替わるので、
    3 つまとめて控えないと undo で戻し切れない。
    """
    snap = {
        "shape": shape,
        "netData": "",
        "controlPoints": {},
        "weights": {},
        "skinCluster": "",
    }
    if not shape or not cmds.objExists(shape):
        return snap
    snap["netData"] = RetopoGuideAccessor(shape).read_raw_json()
    try:
        for i in (cmds.getAttr("{}.controlPoints".format(shape),
                               multiIndices=True) or []):
            v = cmds.getAttr("{}.controlPoints[{}]".format(shape, i))[0]
            if any(abs(c) > 1e-12 for c in v):
                snap["controlPoints"][i] = list(v)
    except Exception:
        pass
    sc = _find_skincluster(shape)
    if sc:
        snap["skinCluster"] = sc
        snap["weights"] = get_skin_weights(shape) or {}
    return snap


def restore_curvenet(snap):
    """``snapshot_curvenet`` で控えた状態へ戻す。"""
    if not snap:
        return False
    shape = snap.get("shape") or ""
    if not shape or not cmds.objExists(shape):
        return False

    acc = RetopoGuideAccessor(shape)
    cn = RetopoGuideData.from_json(snap.get("netData") or "")
    acc.write(cn)

    n_cv = len(cn.positions)
    for i, v in (snap.get("controlPoints") or {}).items():
        if not (0 <= int(i) < n_cv):
            continue
        try:
            cmds.setAttr("{}.controlPoints[{}]".format(shape, int(i)),
                         v[0], v[1], v[2], type="double3")
        except Exception:
            pass

    sc = snap.get("skinCluster") or ""
    if sc and cmds.objExists(sc):
        set_skin_weights_bulk(
            shape, {int(i): w for i, w in (snap.get("weights") or {}).items()
                    if 0 <= int(i) < n_cv and w},
            sc=sc, normalize=True)

    _trim_multi("{}.controlPoints".format(shape), n_cv)
    if sc and cmds.objExists(sc):
        _trim_multi("{}.weightList".format(sc), n_cv)

    # 編集コンテキストが憶えている CV 番号は復元後の並びと合わないので捨てる
    try:
        from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx
        for _n in ("sel_ep", "drag_ep", "merge_target", "drag_mirror_ep"):
            setattr(_ctx, _n, None)
    except Exception:
        pass

    _dirty_shape_view()
    return True


def delete_selected_eps(node_name="", cv_indices=None, mirror=True,
                        quiet=False):
    """選択した制御点を削除する (コンポーネントモードの Delete)。

    次数 2 の通過点を消した場合は両隣のカーブを 1 本に繋ぎ直す。
    それ以外は、その点に繋がるカーブをすべて消す。編集コンテキストの
    Ctrl クリック削除とまったく同じ挙動。

    ハンドルは単体では消せない (カーブの形を決めるものであって、
    ネットの構成要素ではないため)。選択に混ざっていても無視する。

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択 / optionVar から解決する。
    cv_indices : list[int] or None
        削除する CV。None なら選択中のコンポーネントを使う。
    mirror : bool
        対称化が有効なら反対側の点も一緒に消す。
    quiet : bool
        メッセージを出さない (Delete キー経由など、Maya 側が
        既に文脈を持っている場合に使う)。

    Returns
    -------
    int
        削除した制御点の数。
    """
    from Aru_RetopoTool.editor.curvenet import curve_net_context as _cnc
    from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym

    if cv_indices is None:
        shape, cv_indices = get_selected_cv_indices(node_name)
    else:
        shape = _resolve_curvenet_shape(node_name)

    if not shape:
        if not quiet:
            om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return 0
    if not cv_indices:
        if not quiet:
            om.MGlobal.displayWarning(
                "[RetopoGuide] 削除する制御点を選択してください")
        return 0

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()
    mesh_name = acc.mesh_name

    eps = cn.endpoint_indices()
    targets = [i for i in sorted(set(cv_indices))
               if 0 <= i < len(cn.positions) and i in eps]
    if not targets:
        if not quiet:
            om.MGlobal.displayWarning(
                "[RetopoGuide] ハンドルは単体では削除できません。"
                "制御点 (ポイント) を選んでください")
        return 0

    # 対称側は先に全部集めておく。_remove_ep でスプラインが消えると
    # その点は EP として認識されなくなり、探せなくなるため。
    if mirror and _sym.is_enabled():
        tol = _cnc._mirror_tol(mesh_name)
        extra = []
        for ep in targets:
            m = _sym.find_mirror_ep(cn, mesh_name, ep, tol)
            if m is not None and m != ep and m not in targets:
                extra.append(m)
        targets = sorted(set(targets) | set(extra))

    for ep in targets:
        _cnc._remove_ep(cn, ep, mesh_name)
        # 線を持たない単独ポイントも消す。印を外すだけだと
        # positions に残ったままになる。
        cn.unmark_standalone(ep)

    _commit_net_data(shape, cn)
    # 孤立 CV の掃除で CV 番号が詰まるため、編集コンテキストが憶えている
    # CV 番号は別の点を指してしまう。捨てておく。
    try:
        from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx
        for _n in ("sel_ep", "drag_ep", "merge_target", "drag_mirror_ep"):
            setattr(_ctx, _n, None)
    except Exception:
        pass
    if not quiet:
        om.MGlobal.displayInfo(
            "[RetopoGuide] 制御点を {} 個削除しました".format(len(targets)))
    return len(targets)


def _plane_crossing_t(cn, sp_idx, mesh_name, axis, space):
    """スプラインが対称面を横切る t を返す。横切らなければ None。

    32 分割で符号が変わる区間を探し、そこを二分法で詰める。
    """
    from Aru_RetopoTool.editor.curvenet import curve_net_context as _cnc
    from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym

    sp = cn.splines[sp_idx]
    p0, p1, p2, p3 = [cn.positions[i] for i in sp]

    def f(t):
        bp = _cnc._bezier_point(p0, p1, p2, p3, t)
        c = _sym.plane_coord(bp, mesh_name, axis=axis, space=space)
        return 0.0 if c is None else c

    N = 32
    prev_t, prev_v = 0.0, f(0.0)
    lo = hi = None
    for k in range(1, N + 1):
        t = k / float(N)
        v = f(t)
        if prev_v * v < 0.0:
            lo, hi = prev_t, t
            break
        prev_t, prev_v = t, v
    if lo is None:
        return None

    v_lo = f(lo)
    for _ in range(40):
        mid = (lo + hi) * 0.5
        v_mid = f(mid)
        if v_lo * v_mid <= 0.0:
            hi = mid
        else:
            lo, v_lo = mid, v_mid
    return (lo + hi) * 0.5


def _split_splines_at_plane(cn, mesh_name, axis, space, plane_tol):
    """対称面を跨いでいるスプラインを面の上で 2 本に分ける。

    片側だけを写すには、面を跨いだままのカーブがあると
    「どちら側のものか」が決められない。メッシュミラーが対称面で
    ジオメトリを切るのと同じことをする。

    Returns
    -------
    int
        分割した本数。
    """
    from Aru_RetopoTool.editor.curvenet import curve_net_context as _cnc
    from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym

    def side_of(cv):
        c = _sym.plane_coord(cn.positions[cv], mesh_name,
                             axis=axis, space=space)
        if c is None or abs(c) <= plane_tol:
            return 0
        return 1 if c > 0.0 else -1

    n = 0
    si = 0
    # split_spline は末尾に右半分を足すので len() は増える。
    # 分割後の 2 本はどちらも面を跨がないため、素直に前へ進めてよい。
    while si < len(cn.splines):
        sp = cn.splines[si]
        if any(i >= len(cn.positions) for i in sp):
            si += 1
            continue
        if side_of(sp[0]) * side_of(sp[3]) >= 0:
            si += 1
            continue
        t = _plane_crossing_t(cn, si, mesh_name, axis, space)
        if t is None or t <= 1e-4 or t >= 1.0 - 1e-4:
            si += 1
            continue
        new_ep, _sp0, _sp1 = cn.split_spline(si, t)
        # 分割点はベジエ上の点なので面からわずかにずれる。面へ載せ直す。
        pos, face_idx, bary = _cnc._snap_pos_to_plane(mesh_name,
                                                      cn.positions[new_ep])
        cn.move_cv(new_ep, pos)
        if face_idx >= 0:
            cn.surface_binding[new_ep] = (face_idx, bary)
        n += 1
        si += 1
    if n:
        cn.classify_endpoints()
    return n


def mirror_curvenet(node_name="", axis=None, space=None, mode=None,
                    direction=None, quiet=False):
    """カーブネットを左右反転して作る。

    ツール設定の「対称化」で選んだ軸と空間をそのまま対称面に使う。
    メッシュのミラーと同じように、対称面を跨いでいるカーブは面の上で
    2 本に切ってから処理する。

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択 / optionVar から解決する。
    axis : str or None
        "x" / "y" / "z"。None ならツール設定の対称化の軸を使う。
    space : str or None
        "object" / "world"。None ならツール設定の対称空間を使う。
    mode : str or None
        "replace" なら反転先の側を消してから作り直す。
        "add" なら今あるものは残して足りないぶんだけ足す。
        None ならツール設定の値を使う。
    direction : str or None
        "positive" なら + 側を反転元にする。"negative" ならその逆。
        None ならツール設定の値を使う。
    quiet : bool
        メッセージを出さない。

    Returns
    -------
    int
        新しく作ったカーブの本数。
    """
    from Aru_RetopoTool.editor.curvenet import curve_net_context as _cnc
    from Aru_RetopoTool.editor.curvenet import curve_net_symmetry as _sym

    shape = _resolve_curvenet_shape(node_name)
    if not shape:
        if not quiet:
            om.MGlobal.displayWarning(
                "[RetopoGuide] retopoGuideNode が見つかりません")
        return 0

    axis = _sym.get_axis() if axis is None else str(axis or "").lower()
    if axis not in ("x", "y", "z"):
        if not quiet:
            om.MGlobal.displayWarning(
                "[RetopoGuide] 反転する軸が決まっていません。"
                "ツール設定の「対称化」で X / Y / Z を選んでください")
        return 0

    space = _sym.get_space() if space is None else space
    mode = _sym.get_mirror_mode() if mode is None else mode
    direction = (_sym.get_mirror_direction() if direction is None
                 else direction)
    src_sign = 1 if str(direction).lower() != "negative" else -1
    tgt_sign = -src_sign

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()
    mesh_name = acc.mesh_name

    tol = _cnc._mirror_tol(mesh_name)
    plane_tol = tol * 0.5

    def side_of(cv):
        """CV が対称面のどちら側にいるか (+1 / 0 / -1)。0 は面の上。"""
        if cv >= len(cn.positions):
            return 0
        c = _sym.plane_coord(cn.positions[cv], mesh_name,
                             axis=axis, space=space)
        if c is None or abs(c) <= plane_tol:
            return 0
        return 1 if c > 0.0 else -1

    def spline_side(sp):
        """スプラインがどちら側のものか。面の上に寝ているなら 0。"""
        a = side_of(sp[0])
        return a if a != 0 else side_of(sp[3])

    cmds.undoInfo(openChunk=True, chunkName="retopoGuideMirror")
    try:
        # --- 1. 対称面を跨いでいるカーブを面の上で切る -----------------
        n_split = _split_splines_at_plane(cn, mesh_name, axis, space,
                                          plane_tol)

        # --- 2. 反転元があるか確かめる --------------------------------
        src_splines = [tuple(sp) for sp in cn.splines
                       if spline_side(sp) == src_sign]
        src_alone = [c for c in sorted(cn.standalone_eps)
                     if c < len(cn.positions) and side_of(c) == src_sign]
        if not src_splines and not src_alone:
            if not quiet:
                om.MGlobal.displayWarning(
                    "[RetopoGuide] 反転元の側にカーブがありません。"
                    "ツール設定の「反転の向き」を逆にしてみてください")
            return 0

        # --- 3. 作り直すなら反転先の側を消す ---------------------------
        n_removed = 0
        if str(mode).lower() != "add":
            kept = [sp for sp in cn.splines if spline_side(sp) != tgt_sign]
            n_removed = len(cn.splines) - len(kept)
            cn.splines = kept
            cn.standalone_eps = {c for c in cn.standalone_eps
                                 if c < len(cn.positions)
                                 and side_of(c) != tgt_sign}
            cn.classify_endpoints()
            src_splines = [tuple(sp) for sp in cn.splines
                           if spline_side(sp) == src_sign]

        # --- 4. 反転先の CV を用意する --------------------------------
        # 既存 EP の再利用は「今ある EP」だけを対象にする。
        # 反転で足した EP を拾うと自分自身に繋ぎ直してしまう。
        eps_before = cn.endpoint_indices()
        mirror_of = {}

        def mirror_cv(cv, is_ep):
            if cv in mirror_of:
                return mirror_of[cv]
            if is_ep and side_of(cv) == 0:
                # 面の上の点は自分自身が反転先
                mirror_of[cv] = cv
                return cv
            mpos = _sym.mirror_point(cn.positions[cv], mesh_name,
                                     axis=axis, space=space)
            if not is_ep:
                new = cn.add_cv(mpos)
                mirror_of[cv] = new
                return new
            found = cn.find_nearest_cv(mpos, tol, exclude=cv)
            if found is not None and found in eps_before:
                mirror_of[cv] = found
                return found
            # EP はメッシュの上に載っていないといけない
            mpos, face_idx, bary = _cnc._project_on_mesh(mesh_name, mpos)
            new = cn.add_cv(mpos,
                            surface=(face_idx, bary) if face_idx >= 0 else None)
            mirror_of[cv] = new
            return new

        # --- 5. カーブを反転して作る ----------------------------------
        n_new = 0
        for i0, i1, i2, i3 in src_splines:
            m0 = mirror_cv(i0, True)
            m3 = mirror_cv(i3, True)
            if m0 == m3:
                continue
            if _cnc._spline_exists(cn, m0, m3):
                continue
            # ハンドルもそのまま反転する。メッシュに合わせ直すより
            # 左右がぴったり揃う。
            m1 = mirror_cv(i1, False)
            m2 = mirror_cv(i2, False)
            cn.add_spline(m0, m1, m2, m3)
            n_new += 1

        # --- 6. 線を持たない単独ポイントも反転する ---------------------
        for cv in src_alone:
            m = mirror_cv(cv, True)
            if m != cv:
                cn.mark_standalone(m)

        cn.sync_standalone()
        cn.classify_endpoints()

        # --- 7. スキンウェイトを反転元から複製する ---------------------
        # ウェイトが空のままだと、その点だけ原点へ飛んでしまう。
        # 左右のインフルエンスの入れ替えまではやらない (下のメッセージ参照)。
        sc = _find_skincluster(shape)
        src_weights = {}
        pairs = []
        if sc:
            srcs = [c for c, m in mirror_of.items() if m != c]
            if srcs:
                src_weights = get_skin_weights(shape, srcs) or {}
                pairs = [(c, mirror_of[c]) for c in srcs]

        remap = _commit_net_data(shape, cn)

        if sc and src_weights:
            inf_map = _influence_index_map(sc)
            for src_cv, dst_cv in pairs:
                w = src_weights.get(src_cv) or {}
                if not any(abs(v) > 1e-9 for v in w.values()):
                    continue
                idx = remap.get(dst_cv, dst_cv) if remap else dst_cv
                _set_cv_weights_direct(sc, idx, w, inf_map)
    finally:
        cmds.undoInfo(closeChunk=True)

    # 掃除で CV 番号が詰まるので、編集コンテキストの憶えている番号は捨てる
    try:
        from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx
        for _n in ("sel_ep", "drag_ep", "merge_target", "drag_mirror_ep"):
            setattr(_ctx, _n, None)
    except Exception:
        pass

    if not quiet:
        msg = "[RetopoGuide] 左右反転しました (カーブ {} 本を作成".format(n_new)
        if n_removed:
            msg += " / 反対側 {} 本を削除".format(n_removed)
        if n_split:
            msg += " / 対称面で {} 本を分割".format(n_split)
        msg += ")"
        om.MGlobal.displayInfo(msg)
        if sc and n_new:
            om.MGlobal.displayInfo(
                "[RetopoGuide] スキンウェイトは反転元をそのまま複製しました。"
                "左右で別のジョイントに入れたい場合は"
                "「メッシュからウェイトコピー」をかけ直してください")
    return n_new


def reset_manual_handles(node_name="", cv_indices=None):
    """手で動かしたハンドルの固定を解除して自動フィットに戻す。

    編集コンテキストで MMB ドラッグしたハンドル (暖色表示) は、以降自動
    フィットで上書きされない。これを外して測地線フィットを掛け直す。

    Parameters
    ----------
    cv_indices : list[int] or None
        対象の CV。EP を含む場合はその EP に付くハンドルも対象。
        None なら選択中、選択が無ければ全部。

    Returns
    -------
    int
        解除したハンドルの数。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_context import (
        _recompute_handles_for_ep)

    if cv_indices is None:
        shape, cv_indices = get_selected_cv_indices(node_name)
    else:
        shape = _resolve_curvenet_shape(node_name)
    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return 0

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()
    if not cn.manual_handles:
        om.MGlobal.displayInfo("[RetopoGuide] 手動ハンドルはありません")
        return 0

    if cv_indices:
        sel = set(int(c) for c in cv_indices)
        targets = set()
        for sp in cn.splines:
            if sp[0] in sel or sp[1] in sel:
                targets.add(sp[1])
            if sp[3] in sel or sp[2] in sel:
                targets.add(sp[2])
        targets &= cn.manual_handles
    else:
        targets = set(cn.manual_handles)
    if not targets:
        return 0

    cn.clear_manual_handles(targets)
    cmds.undoInfo(openChunk=True, chunkName="ResetManualHandles")
    try:
        # 手で曲げたカーブを種にすると測地線の緩和が戻り切らないので、
        # 接平面の既定初期化からフィットし直す (EP 単位で張り直す)
        eps = set()
        for sp in cn.splines:
            if sp[1] in targets:
                eps.add(sp[0])
            if sp[2] in targets:
                eps.add(sp[3])
        for ep in eps:
            _recompute_handles_for_ep(cn, ep, acc.mesh_name)
        _commit_net_data(shape, cn)
    finally:
        cmds.undoInfo(closeChunk=True)
    om.MGlobal.displayInfo(
        "[RetopoGuide] {} 個のハンドルを自動フィットに戻しました".format(len(targets)))
    return len(targets)


def flatten_tangents(node_name="", cv_indices=None):
    """タンジェントハンドルをサーフェスの接平面へ寝かせる (論文 §3)。

    ハンドルベクトル ``v = handle - ep`` からメッシュ法線方向の成分を
    抜く。``v' = v - (v・n) n``。長さは正規化しない (法線から倒れて
    いた分だけ自然に短くなるのが正しい挙動)。

    メッシュから浮いてしまったカーブを表面に沿わせ直すのに使う。
    EP そのものは動かさない。

    Parameters
    ----------
    node_name : str
        retopoGuideNode 名。空なら選択 / optionVar から解決する。
    cv_indices : list[int] or None
        対象のハンドル CV。EP を指定した場合はその EP に付く全ハンドルを
        対象にする。None なら選択中のコンポーネント、選択が無ければ全体。

    Returns
    -------
    int
        寝かせたハンドルの数。
    """
    from Aru_RetopoTool.editor.curvenet.curve_net_data import (
        _v3_sub, _v3_add, _v3_dot, _v3_len, _v3_scale, _v3_normalize)

    if cv_indices is None:
        shape, cv_indices = get_selected_cv_indices(node_name)
    else:
        shape = _resolve_curvenet_shape(node_name)

    if not shape:
        om.MGlobal.displayWarning("[RetopoGuide] retopoGuideNode が見つかりません")
        return 0

    acc = RetopoGuideAccessor(shape)
    cn = acc.read()
    mesh_name = acc.mesh_name
    if not mesh_name or not cmds.objExists(mesh_name):
        om.MGlobal.displayWarning(
            "[RetopoGuide] メッシュが解決できないので法線を取得できません")
        return 0
    mesh_fn, _ = _get_mesh_fn(mesh_name)

    sel = set(cv_indices or [])

    # (handle_cv, ep_cv) の組を集める
    pairs = []
    for sp in cn.splines:
        i0, i1, i2, i3 = sp
        for h_cv, ep_cv in ((i1, i0), (i2, i3)):
            if sel and h_cv not in sel and ep_cv not in sel:
                continue
            pairs.append((h_cv, ep_cv))

    if not pairs:
        om.MGlobal.displayWarning(
            "[RetopoGuide] 対象のハンドルがありません")
        return 0

    n_done = 0
    n_skip = 0
    cmds.undoInfo(openChunk=True, chunkName="retopoGuideFlattenTangents")
    try:
        for h_cv, ep_cv in pairs:
            p = cn.positions[ep_cv]
            h = cn.positions[h_cv]
            v = _v3_sub(h, p)
            v_len = _v3_len(v)
            if v_len < 1e-9:
                continue
            n = _get_normal_at_point(mesh_fn, p)
            if n is None:
                continue
            n = _v3_normalize(n)
            if _v3_len(n) < 0.5:
                continue
            flat = _v3_sub(v, _v3_scale(n, _v3_dot(v, n)))
            # ハンドルがほぼ法線を向いていると投影が潰れて
            # 退化スプラインになるので触らない
            if _v3_len(flat) < v_len * 0.05:
                n_skip += 1
                continue
            cn.positions[h_cv] = _v3_add(p, flat)
            n_done += 1

        if n_done:
            _commit_net_data(shape, cn)
    finally:
        cmds.undoInfo(closeChunk=True)

    msg = "[RetopoGuide] ハンドルを {} 本フラット化しました".format(n_done)
    if n_skip:
        msg += " ({} 本は法線方向を向いていたのでスキップ)".format(n_skip)
    om.MGlobal.displayInfo(msg)
    return n_done


def prune_orphan_cvs_and_write(shape, cn):
    """*cn* から孤立 CV を取り除いて *shape* に書き込む。

    書き込み前に skinCluster ウェイトと controlPoints を退避し、
    新しい CV インデックスへ移し替える。孤立 CV が無い場合は
    通常の write と等価。

    Parameters
    ----------
    shape : str
        retopoGuideNode のシェイプ名。
    cn : RetopoGuideData
        書き込む (まだノードに反映していない) データ。破壊的に更新される。

    Returns
    -------
    tuple[int, dict[int, int] | None]
        (削除した CV 数, 旧→新インデックス写像)。
        孤立が無かった場合は ``(0, None)``。
    """
    acc = RetopoGuideAccessor(shape)
    # 線が繋がった単独ポイントの印は落としておく。残したままだと、その EP に
    # 繋がるスプラインを後で全部消しても残骸として掃除されなくなる。
    cn.sync_standalone()
    orphans = cn.orphan_cv_indices()
    if not orphans:
        acc.write(cn)
        return 0, None

    # --- 掃除前の状態を退避 (ノードはまだ旧インデックス) ---------------
    sc = _find_skincluster(shape)
    influences = []
    old_weights = {}
    if sc:
        influences = cmds.skinCluster(sc, q=True, inf=True) or []
        old_weights = get_skin_weights(shape) or {}

    old_cp = {}
    try:
        for i in (cmds.getAttr("{}.controlPoints".format(shape),
                               multiIndices=True) or []):
            v = cmds.getAttr("{}.controlPoints[{}]".format(shape, i))[0]
            if any(abs(c) > 1e-12 for c in v):
                old_cp[i] = v
    except Exception:
        old_cp = {}

    remap = cn.compact_cvs()
    # Restore CP/skin indices before showing the committed geometry.
    acc.write(cn, refresh=False)

    # controlPoints を貼り直す (write() でゼロリセット済み)
    for old, v in old_cp.items():
        new = remap.get(old)
        if new is None:
            continue
        try:
            cmds.setAttr("{}.controlPoints[{}]".format(shape, new),
                         v[0], v[1], v[2], type="double3")
        except Exception:
            pass

    # スキンウェイトを貼り直す
    if sc and influences:
        remapped = {}
        for old, w in old_weights.items():
            new = remap.get(old)
            if new is None or not w:
                continue
            remapped[new] = w
        set_skin_weights_bulk(shape, remapped, sc=sc, normalize=True)

    # 余った multi 要素を落とす。放置すると weightList / controlPoints の
    # 要素数が CV 数より多いままになり、Component Editor の行数などが
    # 実際より多く見える。
    n_new = len(cn.positions)
    _trim_multi("{}.controlPoints".format(shape), n_new)
    if sc:
        _trim_multi("{}.weightList".format(sc), n_new)
        # 再採番で貼り直した後も、同じコミットで追加された点は空のままなので埋める
        try:
            fill_missing_skin_weights(shape, cn)
        except Exception:
            pass

    _dirty_shape_view()
    return len(orphans), remap


def copy_skin_weights_from_mesh(source_mesh="", target_curvenet=""):
    """メッシュの skinCluster ウェイトを RetopoGuide にコピーする。

    各 RetopoGuide 制御点の位置に最も近いメッシュ頂点のウェイトを転写する。
    RetopoGuide 側に skinCluster が未接続の場合、ソースと同じジョイントで
    自動的にバインドする。

    Parameters
    ----------
    source_mesh : str
        ソースメッシュのトランスフォーム名またはシェイプ名。
        省略時は選択から自動取得（メッシュ → RetopoGuide の順）。
    target_curvenet : str
        ターゲット retopoGuideNode 名。省略時は選択/optionVar から自動取得。

    Returns
    -------
    bool : 成功なら True。
    """
    import json as _json

    # --- ソース / ターゲット解決 ---
    if not source_mesh or not target_curvenet:
        sel = cmds.ls(selection=True, long=True) or []
        meshes = []
        cnets = []
        for s in sel:
            shapes = cmds.listRelatives(s, shapes=True, fullPath=True) or [s]
            for sh in shapes:
                nt = cmds.nodeType(sh)
                if nt == "mesh":
                    meshes.append(sh)
                elif nt == "retopoGuideNode":
                    cnets.append(sh)
        if not source_mesh:
            if not meshes:
                om.MGlobal.displayError(
                    "[RetopoGuide] コピー元メッシュが見つかりません。"
                    "メッシュと RetopoGuide を選択してください。")
                return False
            source_mesh = meshes[0]
        if not target_curvenet:
            if cnets:
                target_curvenet = cnets[0]

    # ソースメッシュシェイプ解決
    src_shape = source_mesh
    if cmds.nodeType(source_mesh) == "transform":
        shapes = cmds.listRelatives(source_mesh, shapes=True,
                                    type="mesh", fullPath=True) or []
        if shapes:
            src_shape = shapes[0]
    if not cmds.objExists(src_shape) or cmds.nodeType(src_shape) != "mesh":
        om.MGlobal.displayError(
            "[RetopoGuide] ソースがメッシュではありません: {}".format(source_mesh))
        return False

    # ターゲット RetopoGuide 解決
    tgt_shape = _resolve_curvenet_shape(target_curvenet)
    if not tgt_shape:
        om.MGlobal.displayError(
            "[RetopoGuide] ターゲット retopoGuideNode が見つかりません")
        return False

    # --- ソース skinCluster ---
    src_sc = _find_skincluster(src_shape)
    if not src_sc:
        om.MGlobal.displayError(
            "[RetopoGuide] ソースメッシュに skinCluster がありません: {}".format(
                src_shape))
        return False

    src_joints = cmds.skinCluster(src_sc, q=True, inf=True) or []
    if not src_joints:
        om.MGlobal.displayError("[RetopoGuide] ソースにインフルエンスがありません")
        return False

    # --- RetopoGuide の位置取得 ---
    acc = RetopoGuideAccessor(tgt_shape)
    raw = acc.read_raw_json()
    if not raw:
        om.MGlobal.displayError("[RetopoGuide] netData が空です")
        return False
    d = _json.loads(raw)
    positions = d.get("positions", [])
    if not positions:
        om.MGlobal.displayError("[RetopoGuide] 制御点がありません")
        return False

    # controlPoints デルタを加算して最終位置を得る
    try:
        cp_plug_name = "{}.controlPoints".format(tgt_shape)
        cp_indices = cmds.getAttr(cp_plug_name, multiIndices=True) or []
        for idx in cp_indices:
            if idx < len(positions):
                val = cmds.getAttr("{}[{}]".format(cp_plug_name, idx))[0]
                positions[idx] = [
                    positions[idx][0] + val[0],
                    positions[idx][1] + val[1],
                    positions[idx][2] + val[2],
                ]
    except Exception:
        pass

    # --- MFnMesh で最近接頂点検索 ---
    sel_list = om.MSelectionList()
    sel_list.add(src_shape)
    src_dag = om.MDagPath()
    sel_list.getDagPath(0, src_dag)
    mesh_fn = om.MFnMesh(src_dag)

    # 全メッシュ頂点位置を取得
    mesh_pts = om.MPointArray()
    mesh_fn.getPoints(mesh_pts, om.MSpace.kWorld)

    # RetopoGuide トランスフォームのワールド行列
    tgt_xform = cmds.listRelatives(tgt_shape, parent=True, fullPath=True)
    if tgt_xform:
        tgt_xform = tgt_xform[0]
        wm = cmds.xform(tgt_xform, q=True, ws=True, matrix=True)
    else:
        wm = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    mat = om.MMatrix()
    om.MScriptUtil.createMatrixFromList(wm, mat)

    # 各 CV に最も近いメッシュ頂点を見つけてウェイトをマップ
    cv_to_weights = {}
    for cv_idx, pos in enumerate(positions):
        # ローカル位置 → ワールド位置
        local_pt = om.MPoint(pos[0], pos[1], pos[2])
        world_pt = local_pt * mat

        # 最近接頂点を線形探索
        best_dist = float("inf")
        best_vtx = 0
        for vi in range(mesh_pts.length()):
            mp = mesh_pts[vi]
            dx = world_pt.x - mp.x
            dy = world_pt.y - mp.y
            dz = world_pt.z - mp.z
            dist_sq = dx * dx + dy * dy + dz * dz
            if dist_sq < best_dist:
                best_dist = dist_sq
                best_vtx = vi
        cv_to_weights[cv_idx] = best_vtx

    # --- ソースメッシュのウェイト取得 ---
    needed_vtx = set(cv_to_weights.values())
    src_weights = {}  # {mesh_vtx: [(joint, weight), ...]}
    for vi in needed_vtx:
        comp = "{}.vtx[{}]".format(src_shape, vi)
        vals = cmds.skinPercent(src_sc, comp, q=True, v=True) or []
        pairs = []
        for ji, v in enumerate(vals):
            if ji < len(src_joints) and abs(v) > 1e-9:
                pairs.append((src_joints[ji], v))
        src_weights[vi] = pairs

    # --- ターゲットに skinCluster がなければ自動バインド ---
    tgt_sc = _find_skincluster(tgt_shape)
    if tgt_sc:
        # 既存の skinCluster があればジョイントだけ追加して再利用
        existing_joints = set(
            cmds.skinCluster(tgt_sc, q=True, influence=True) or [])
        for j in src_joints:
            if j not in existing_joints:
                cmds.skinCluster(tgt_sc, e=True, addInfluence=j,
                                 weight=0.0)
        om.MGlobal.displayInfo(
            "[RetopoGuide] 既存の skinCluster '{}' を再利用します".format(tgt_sc))
    else:
        # CP をベイクしてからバインド
        bake_control_points(tgt_shape)

        tgt_xform_short = cmds.listRelatives(
            tgt_shape, parent=True) or [tgt_shape]
        tgt_sc = cmds.skinCluster(
            src_joints, tgt_xform_short[0],
            toSelectedBones=True, bindMethod=0,
            normalizeWeights=1, weightDistribution=0,
            name="retopoGuide_skinCluster#")[0]
        om.MGlobal.displayInfo(
            "[RetopoGuide] skinCluster '{}' を自動作成しました".format(tgt_sc))

    # --- ウェイト転写 ---
    cmds.undoInfo(openChunk=True, chunkName="CopySkinWeightsToRetopoGuide")
    try:
        for cv_idx in range(len(positions)):
            mesh_vtx = cv_to_weights[cv_idx]
            pairs = src_weights.get(mesh_vtx, [])
            if not pairs:
                continue
            comp = "{}.vtx[{}]".format(tgt_shape, cv_idx)
            tv_args = []
            for joint, w in pairs:
                tv_args.extend([joint, w])
            # skinPercent -tv j1 w1 -tv j2 w2 ...
            tv_list = [(pairs[i][0], pairs[i][1]) for i in range(len(pairs))]
            cmds.skinPercent(tgt_sc, comp,
                             transformValue=tv_list, normalize=True)
    finally:
        cmds.undoInfo(closeChunk=True)

    om.MGlobal.displayInfo(
        "[RetopoGuide] {} 頂点のウェイトを '{}' → '{}' にコピーしました".format(
            len(positions), src_shape.split("|")[-1],
            tgt_shape.split("|")[-1]))
    return True


def _resolve_curvenet_shape(node_name=""):
    """retopoGuideNode のシェイプ名を解決する。"""
    if node_name:
        shape = _find_shape_node(node_name) or node_name
        if cmds.objExists(shape) and cmds.nodeType(shape) == "retopoGuideNode":
            return shape
    ov = cmds.optionVar(q="retopoGuideContext_node") or ""
    if ov:
        shape = _find_shape_node(ov) or ov
        if cmds.objExists(shape) and cmds.nodeType(shape) == "retopoGuideNode":
            return shape
    for n in (cmds.ls(selection=True) or []):
        shape = _find_shape_node(n) or n
        if cmds.objExists(shape) and cmds.nodeType(shape) == "retopoGuideNode":
            return shape
    return ""


def _find_skincluster(shape):
    """シェイプに接続された skinCluster を返す。"""
    try:
        hist = cmds.listHistory(shape, pdo=True) or []
        for h in hist:
            if cmds.nodeType(h) in ("skinCluster", "retopoGuideSkinCluster"):
                return h
    except Exception:
        pass
    return None


def _get_cv_count(shape):
    """retopoGuideNode の CV 数を返す。"""
    try:
        raw = cmds.getAttr("{}.netData".format(shape)) or ""
        if not raw:
            return 0
        return len(RetopoGuideData.from_json_cached(raw).positions)
    except Exception:
        pass
    return 0


def _sync_ep_locators(node_name: str,
                      cn: Optional[RetopoGuideData] = None) -> None:
    """旧ロケーター同期 (コンポーネント化で不要 — no-op)。"""
    pass


def _sync_ep_locators_impl(node_name: str,
                           cn: Optional[RetopoGuideData] = None) -> None:
    """旧ロケーター同期実装 (コンポーネント化で不要 — no-op)。"""
    pass


def _sync_handle_locators(node_name: str,
                          cn: Optional[RetopoGuideData] = None) -> None:
    """旧ハンドルロケーター同期 (コンポーネント化で不要 — no-op)。"""
    pass


def _sync_handle_locators_impl(node_name: str,
                               cn: Optional[RetopoGuideData] = None) -> None:
    """旧ハンドルロケーター同期実装 (コンポーネント化で不要 — no-op)。"""
    pass


def _commit_net_data(node: str, cn: RetopoGuideData):
    """netData 変更をノードに書き込み、controlPoints をリセットして再描画する。

    書き込み前に孤立 CV (どのスプラインからも参照されない CV) を取り除く。
    EP 削除・マージ・スプライン削除はスプラインだけを消すため、そのまま
    書くと孤立 CV が溜まり続け、``controlPoints`` / ``weightList`` の
    要素数が実際の CV 数より多くなってしまう。

    Returns
    -------
    dict[int, int] | None
        旧→新 CV インデックス写像。孤立が無く再採番しなかった場合は None。
        呼び出し側がキャッシュしている CV インデックスの張り替えに使う。
    """
    _, remap = prune_orphan_cvs_and_write(node, cn)
    return remap


# ===========================================================================
# RetopoGuideAccessor — Maya retopoGuideNode I/O helper
# ===========================================================================

class RetopoGuideAccessor:
    """Maya retopoGuideNode との読み書きを一元管理するヘルパー。

    使い方::

        acc = RetopoGuideAccessor("retopoGuideNode1")
        cn = acc.read()           # netData -> RetopoGuideData
        ep = cn.ep_at(0)
        ep.position = [1, 2, 3]
        acc.write(cn)             # RetopoGuideData -> netData + CP reset + redraw
    """

    def __init__(self, node: str):
        self._node = node

    # -- properties --------------------------------------------------------

    @property
    def node(self) -> str:
        return self._node

    @property
    def exists(self) -> bool:
        return bool(self._node) and cmds.objExists(self._node)

    @property
    def mesh_name(self) -> str:
        if not self.exists:
            return ""
        return cmds.getAttr("{}.meshName".format(self._node)) or ""

    @mesh_name.setter
    def mesh_name(self, value: str) -> None:
        if self.exists:
            cmds.setAttr("{}.meshName".format(self._node),
                         value, type="string")

    # -- read / write ------------------------------------------------------

    def read(self) -> RetopoGuideData:
        """netData 属性から RetopoGuideData を取得する。"""
        if not self.exists:
            return RetopoGuideData()
        raw = cmds.getAttr("{}.netData".format(self._node)) or ""
        return RetopoGuideData.from_json(raw) if raw else RetopoGuideData()

    def write(self, cn: RetopoGuideData, *, refresh=True) -> None:
        """RetopoGuideData をノードに書き込み、CP リセット + VP2 再描画する。"""
        if not self.exists:
            return
        cn.classify_endpoints()
        from Aru_RetopoTool.patch_transfer import prepare
        patch_updates=prepare(self._node,cn)
        n_old = _get_cv_count(self._node)
        json_str = cn.to_json()
        cmds.setAttr("{}.netData".format(self._node),
                     json_str, type="string")
        self._sync_orig_net_data(json_str)
        import json
        for generator,keys in patch_updates:
            cmds.setAttr(generator+".selectedPatches",json.dumps(sorted(keys)),type="string")
        if hasattr(cn,"_retopo_parents"):del cn._retopo_parents

        # controlPoints をゼロにリセット (ベース位置は netData に反映済み)。
        # ただしデフォーマ駆動時は CP が
        # ポーズ空間の補正 (PSD) なので消さない。
        if not is_pose_driven(self._node):
            _reset_control_points(self._node, len(cn.positions))

        # CV が増えたときは、新しい点にスキンウェイトを継承させる
        # (ゼロのままだとポーズでその点だけレストに取り残される)。
        if len(cn.positions) > n_old:
            try:
                fill_missing_skin_weights(self._node, cn)
            except Exception:
                pass

        # netData → outNetData → deformer.outputGeometry は attributeAffects で
        # 自然に dirty になる。dgdirty -allPlugs はメッシュ側で VP2 の全再構築を
        # 引き起こし 1 フレーム ~400 ms 食うので使わない。
        if refresh:
            _dirty_shape_view()
        _request_rebind(self._node)

    def read_raw_json(self) -> str:
        """netData の生 JSON 文字列を返す。"""
        if not self.exists:
            return ""
        return cmds.getAttr("{}.netData".format(self._node)) or ""

    def write_raw_json(self, json_str: str) -> None:
        """生 JSON 文字列を直接書き込む。"""
        if not self.exists:
            return
        cmds.setAttr("{}.netData".format(self._node),
                     json_str, type="string")
        self._sync_orig_net_data(json_str)
        _request_rebind(self._node)

    # -- helpers -----------------------------------------------------------

    def orig_shapes(self) -> list:
        """同じトランスフォーム下の中間 (Orig) retopoGuideNode を返す。"""
        if not self.exists:
            return []
        parents = cmds.listRelatives(self._node, parent=True, fullPath=True) or []
        if not parents:
            return []
        out = []
        for sh in (cmds.listRelatives(parents[0], shapes=True, fullPath=True,
                                      type=kPluginNodeName) or []):
            if sh.split("|")[-1] == self._node.split("|")[-1]:
                continue
            try:
                if cmds.getAttr(sh + ".intermediateObject"):
                    out.append(sh)
            except Exception:
                pass
        return out

    def _sync_orig_net_data(self, json_str: str) -> None:
        """スキンクラスタの入力である Orig にも同じレスト形状を持たせる。

        Orig の cachedSurface は netData から作り直されるので、CV を追加・削除しても
        skinCluster が新しい点数で評価される。
        """
        for sh in self.orig_shapes():
            try:
                cmds.setAttr(sh + ".netData", json_str, type="string")
            except Exception:
                pass


# Poisson デフォーマ ヘルパー
# ---------------------------------------------------------------------------


def create_poisson_deformer(cn_node="", mesh="", falloff_mode=None):
    """retopoGuideNode + メッシュから profileCurveDeformer をワンクリック作成する。

    引数省略時は retopoGuideNode の meshName 属性 → 選択から自動解決する。
    ``falloff_mode`` でカーブネットの効果範囲プリセットを指定できる
    (省略時は「標準」)。
    """
    import os as _os

    # --- retopoGuideNode 解決 ---
    if not cn_node:
        cn_node = cmds.optionVar(q="retopoGuideContext_node") or ""
    if not cn_node:
        sel = cmds.ls(selection=True, long=True) or []
        for s in sel:
            if cmds.nodeType(s) == "retopoGuideNode":
                cn_node = s
                break
            shapes = cmds.listRelatives(
                s, shapes=True, type="retopoGuideNode", fullPath=True) or []
            if shapes:
                cn_node = shapes[0]
                break
    if not cn_node or not cmds.objExists(cn_node):
        cmds.warning("[Poisson] retopoGuideNode が見つかりません。")
        return

    # --- メッシュ解決 ---
    if not mesh:
        try:
            mesh = cmds.getAttr("{}.meshName".format(cn_node)) or ""
        except Exception:
            mesh = ""
    if not mesh or not cmds.objExists(mesh):
        sel = cmds.ls(selection=True, long=True) or []
        for s in sel:
            shapes = cmds.listRelatives(
                s, shapes=True, type="mesh", fullPath=True) or []
            if shapes:
                mesh = s.split("|")[-1]
                break
    if not mesh or not cmds.objExists(mesh):
        cmds.warning("[Poisson] ターゲットメッシュが見つかりません。")
        return

    # --- numpy/scipy チェック ---
    try:
        import numpy   # noqa: F401
        import scipy   # noqa: F401
    except ImportError as e:
        cmds.error("[Poisson] numpy/scipy が必要です: {}".format(e))
        return

    # --- プラグインロード (C++ ビルドがあればそれを使う) ---
    from Aru_RetopoTool.editor import launch as _launch
    plugin_path = _launch._deformer_plugin_path()
    try:
        if not cmds.pluginInfo(
                "curve_profile_deformer", query=True, loaded=True):
            cmds.loadPlugin(plugin_path)
    except Exception:
        cmds.loadPlugin(plugin_path)

    # --- デフォーマ作成 ---
    from Aru_RetopoTool.editor.deformer.curve_profile_rig import ProfileCurveRig
    deformer = ProfileCurveRig().create_from_curvenet(
        mesh_name=mesh, cn_node_name=cn_node, falloff_mode=falloff_mode)
    cmds.inViewMessage(
        amg="<hl>Poisson デフォーマ</hl> '{}' を作成しました".format(deformer),
        pos="topCenter", fade=True)
    return deformer


def show_poisson_ui():
    """Poisson デフォーマ UI を表示する。"""
    from Aru_RetopoTool.editor.ui import poisson_ui
    poisson_ui.show()


def show_skin_weight_ui():
    """RetopoGuide スキンウェイトエディタを表示する。"""
    from Aru_RetopoTool.editor.ui import skin_weight_ui
    skin_weight_ui.show()


def show_psd_ui():
    """RetopoGuide ポーズ補正 (PSD) エディタを表示する。"""
    from Aru_RetopoTool.editor.ui import psd_ui
    psd_ui.show()


# ===========================================================================
# レイキャスト ユーティリティ  (screen coords → mesh hit)
# ===========================================================================

def _raycast_from_screen(sx: int, sy: int, mesh_name: str) -> Optional[list[float]]:
    """スクリーン座標 (sx, sy) からメッシュにレイキャストしてワールド座標を返す。"""
    try:
        view = omui.M3dView.active3dView()
        origin    = om.MPoint()
        direction = om.MVector()
        view.viewToWorld(sx, sy, origin, direction)

        if not mesh_name or not cmds.objExists(mesh_name):
            # メッシュなし → y=0 面との交点
            if abs(direction.y) > 1e-8:
                t = -origin.y / direction.y
                return [origin.x + t * direction.x, 0.0,
                        origin.z + t * direction.z]
            return None

        mesh_fn, _ = _get_mesh_fn(mesh_name)
        ray_src  = om.MFloatPoint(origin.x, origin.y, origin.z)
        ray_dir  = om.MFloatVector(direction.x, direction.y, direction.z)
        hit_pt   = om.MFloatPoint()
        hit_face = om.MScriptUtil()
        hit_face.createFromInt(0)

        hit = mesh_fn.closestIntersection(
            ray_src, ray_dir, None, None, False,
            om.MSpace.kWorld, 1e9, False,
            None, hit_pt, None, hit_face.asIntPtr(), None, None, None, 1e-6
        )
        if hit:
            return [hit_pt.x, hit_pt.y, hit_pt.z]

        # 交差なし → メッシュ最近傍点へフォールバック
        far_pt = om.MPoint(origin.x + direction.x * 1000,
                           origin.y + direction.y * 1000,
                           origin.z + direction.z * 1000)
        cl_pt  = om.MPoint()
        cl_face = om.MScriptUtil()
        cl_face.createFromInt(0)
        mesh_fn.getClosestPoint(far_pt, cl_pt, om.MSpace.kWorld, cl_face.asIntPtr())
        return [cl_pt.x, cl_pt.y, cl_pt.z]

    except Exception:
        om.MGlobal.displayError("[RetopoGuide] raycast error:\n" + traceback.format_exc())
        return None


def _camera_view_info():
    """アクティブビューのカメラ位置・視線方向・平行投影かを返す。

    取得できなければ None。
    """
    try:
        view = omui.M3dView.active3dView()
        cam = om.MDagPath()
        view.getCamera(cam)
        fn = om.MFnCamera(cam)
        eye = fn.eyePoint(om.MSpace.kWorld)
        vd = fn.viewDirection(om.MSpace.kWorld)
        return ([eye.x, eye.y, eye.z], [vd.x, vd.y, vd.z], bool(fn.isOrtho()))
    except Exception:
        return None


def make_visibility_test(mesh_name: str, occlusion: bool = True,
                         view_info=None, use_acceleration=True):
    """カメラから見えている点だけを通す判定関数を返す。

    カーブネットはメッシュ表面に張り付くので、画面上では裏側のカーブも
    手前のカーブと同じピクセルに重なる。スナップ先を画面距離だけで
    選ぶと、見えていない裏側のカーブを掴んで、まったく違う場所に
    交点ができてしまう。

    判定は 2 段構え。

    1. **表裏** — その点のメッシュ法線がカメラを向いているか。
       レイキャストと違い、カーブがポリゴンにわずかに埋もれていても
       誤判定しないので、これを主判定にする。
    2. **遮蔽** — 手前に別のパーツ (腕が胴体を隠す等) が無いか。
       点から法線方向に少し浮かせてカメラへレイを飛ばす。
       浮かせないとカーブが埋もれている分だけ自分のメッシュに当たる。

    Parameters
    ----------
    mesh_name : str
        判定に使うメッシュ。
    occlusion : bool
        手前の別パーツによる遮蔽も見るか。
    view_info : tuple | None
        ``(eye, view_dir, is_ortho)``。省略時はアクティブビューから取る。
        バッチにはビューが無いのでテストから差し込めるようにしてある。

    Returns
    -------
    callable | None
        ``f(world_pt) -> bool``。判定できない状況では None
        (呼び出し側はフィルタなしで従来どおり動く)。
    """
    if not mesh_name or not cmds.objExists(mesh_name):
        return None
    info = view_info if view_info is not None else _camera_view_info()
    if info is None:
        return None
    eye, vdir, ortho = info
    try:
        mesh_fn, _dag = _get_mesh_fn(mesh_name)
    except Exception:
        return None

    # 浮かせ量と遮蔽の許容距離。カーブのめり込みは実測でメッシュ
    # サイズの 0.3% 程度なので、その数倍を取っておけば十分。
    lift = _snap_radius(mesh_name) * 0.5
    if lift <= 0.0:
        lift = 1.0e-3

    # Maya owns and invalidates the mesh intersection grid. Reuse it for the
    # whole brush event instead of scanning mesh triangles for every EP ray.
    accel_params = None
    if use_acceleration and occlusion:
        try:
            accel_params = mesh_fn.autoUniformGridParams()
        except Exception:
            pass

    def _visible(world_pt, normal=None):
        try:
            n = _get_normal_at_point(mesh_fn, world_pt) if normal is None else normal
        except Exception:
            return True
        if ortho:
            to_eye = (-vdir[0], -vdir[1], -vdir[2])
        else:
            to_eye = (eye[0] - world_pt[0],
                      eye[1] - world_pt[1],
                      eye[2] - world_pt[2])
        if (n[0] * to_eye[0] + n[1] * to_eye[1] + n[2] * to_eye[2]) <= 0.0:
            return False
        if not occlusion:
            return True

        # 法線方向に浮かせてからカメラへ飛ばす
        src = om.MFloatPoint(world_pt[0] + n[0] * lift,
                             world_pt[1] + n[1] * lift,
                             world_pt[2] + n[2] * lift)
        if ortho:
            d = om.MFloatVector(-vdir[0], -vdir[1], -vdir[2])
            max_d = 1.0e9
        else:
            dv = om.MVector(to_eye[0], to_eye[1], to_eye[2])
            max_d = dv.length()
            if max_d < 1.0e-9:
                return True
            dv.normalize()
            d = om.MFloatVector(dv.x, dv.y, dv.z)
        hit_pt = om.MFloatPoint()
        try:
            hit = mesh_fn.closestIntersection(
                src, d, None, None, False, om.MSpace.kWorld,
                float(max_d), False, accel_params, hit_pt, None, None, None, None,
                None, 1.0e-6)
        except Exception:
            return True
        return not hit

    def _many(points):
        if not points:return []
        from .maya_projector import normals_array
        from .maya_visibility import native_many
        normals=normals_array(mesh_fn,points)
        return native_many(mesh_fn,points,normals,eye,vdir,ortho,occlusion,lift,use_acceleration)
    _visible.many = _many
    return _visible


def _snap_radius(mesh_name: str) -> float:
    """スナップ判定半径をメッシュ AABB の 4% で推定。"""
    try:
        if mesh_name and cmds.objExists(mesh_name):
            bb   = cmds.exactWorldBoundingBox(mesh_name)
            diag = math.sqrt((bb[3]-bb[0])**2 + (bb[4]-bb[1])**2 + (bb[5]-bb[2])**2)
            return diag * 0.04
    except Exception:
        pass
    return 0.1


# ===========================================================================
# MPxCommand (API 2)
