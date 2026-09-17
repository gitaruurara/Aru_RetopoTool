"""
プロファイルカーブリグ  -  セットアップユーティリティ
======================================================
参考論文:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)
--------
- 全バインドデータはデフォーマの ``poissonBindData`` / ``restFrameData`` /
  ``restIsectData`` 属性内に JSON としてシリアライズされるため、
  余分なファイルなしでシーンの保存/読み込みに対応する。
"""

from __future__ import annotations

import os
import json
from typing import Optional

import maya.api.OpenMaya as om
import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.curve_net_data import closest_point_on_bezier


def _isect_tol(verts) -> float:
    """Return a scale-relative endpoint matching tolerance."""
    if len(verts) == 0:
        return 1e-7
    extent = verts.max(axis=0) - verts.min(axis=0)
    return max(float((extent * extent).sum() ** 0.5) * 1e-4, 1e-7)



# ===========================================================================
# 内部ヘルパー関数
# ===========================================================================

def _dag_path(name: str) -> om.MDagPath:
    sel = om.MSelectionList()
    sel.add(name)
    return sel.getDagPath(0)


def _shape_dag(name: str, node_type: str) -> om.MDagPath:
    """*name* 以下にある *node_type* の最初のシェイプの MDagPath を返す。"""
    # name が既にシェイプである場合
    try:
        dag = _dag_path(name)
        dag.extendToShape()
        if cmds.nodeType(dag.fullPathName()) == node_type:
            return dag
    except Exception:
        pass
    # 子ノードを検索
    shapes = cmds.listRelatives(name, shapes=True, type=node_type, fullPath=True) or []
    if not shapes:
        raise ValueError(f"'{name}' の下に '{node_type}' シェイプが見つかりません")
    sel = om.MSelectionList()
    sel.add(shapes[0])
    return sel.getDagPath(0)


def _resolve_curvenet_shape(cn_node_name: str) -> str:
    if cmds.nodeType(cn_node_name) != "retopoGuideNode":
        shapes = cmds.listRelatives(
            cn_node_name, shapes=True, type="retopoGuideNode",
            fullPath=True) or []
        return shapes[0] if shapes else cn_node_name
    return cn_node_name


def cpp_bind_available() -> bool:
    """C++ プラグインの ``aruRetopoGuideBind`` コマンドが使えるか。"""
    try:
        if not cmds.pluginInfo("curve_profile_deformer", q=True, loaded=True):
            return False
        cmds_list = cmds.pluginInfo(
            "curve_profile_deformer", q=True, command=True) or []
        return "aruRetopoGuideBind" in cmds_list
    except Exception:
        return False


def deformer_rest_mesh(deformer: str) -> str:
    """デフォーマの入力 (レスト) メッシュシェイプ名を返す。

    通常は ``*Orig`` の intermediate シェイプ。見つからなければ出力側を返す。
    """
    hist = cmds.listHistory(deformer, pruneDagObjects=False) or []
    for n in hist:
        if n == deformer:
            continue
        if cmds.nodeType(n) == "mesh" and cmds.getAttr(n + ".intermediateObject"):
            return n
    outs = cmds.deformer(deformer, q=True, geometry=True) or []
    return outs[0] if outs else ""


def deformer_output_mesh(deformer: str) -> str:
    outs = cmds.deformer(deformer, q=True, geometry=True) or []
    return outs[0] if outs else ""


# ===========================================================================
# メインクラス
# ===========================================================================

class ProfileCurveRig:
    """メッシュ上にプロファイルカーブリグを作成・管理するクラス。"""

    def compute_bind_data(
        self,
        mesh_name: str,
        cn_node_name: str,
        n_per_spline: int = 5,
        net_str: Optional[str] = None,
        use_cpp: Optional[bool] = None,
    ) -> tuple[str, str, str]:
        """バインドデータ 3 本 (poissonBindData, restFrameData, restIsectData) を計算する。

        デフォーマは作らない。C++ プラグインが読まれていれば
        ``aruRetopoGuideBind`` を使い、無ければ Python 実装で計算する。

        ``net_str`` を省くと ``outNetData`` (無ければ ``netData``) を使う。
        その場でのリバインドにはレスト形状である ``netData`` を渡すこと。
        """
        cn_shape = _resolve_curvenet_shape(cn_node_name)
        if net_str is None:
            net_str = cmds.getAttr(f"{cn_shape}.outNetData") or ""
            if not net_str:
                net_str = cmds.getAttr(f"{cn_shape}.netData") or ""
        if not net_str:
            raise RuntimeError(f"No netData on '{cn_shape}'.")

        if use_cpp is None:
            use_cpp = cpp_bind_available()
        if use_cpp:
            mesh_shape = _shape_dag(mesh_name, "mesh").fullPathName()
            res = cmds.aruRetopoGuideBind(
                mesh=mesh_shape, netData=net_str, nPerSpline=int(n_per_spline))
            if not res or len(res) != 3:
                raise RuntimeError("aruRetopoGuideBind failed")
            return str(res[0]), str(res[1]), str(res[2])
        return self._compute_bind_data_py(mesh_name, net_str, n_per_spline)

    def rebind_in_place(
        self,
        deformer: str,
        cn_node_name: str = "",
        n_per_spline: Optional[int] = None,
        use_cpp: Optional[bool] = None,
    ) -> bool:
        """既存デフォーマを残したままバインドデータだけ作り直す。

        レストメッシュはデフォーマの入力 (``*Orig``)、レストカーブネットは
        ``netData`` を使うので、ポーズ中に呼んでも結果は変わらない。
        接続・envelope・falloff・ピン重みはそのまま残る。
        """
        if not cn_node_name:
            srcs = cmds.listConnections(
                deformer + ".retopoGuideData", source=True, destination=False,
                plugs=False) or []
            if not srcs:
                raise RuntimeError(f"'{deformer}' に retopoGuideNode が接続されていません")
            cn_node_name = srcs[0]
        cn_shape = _resolve_curvenet_shape(cn_node_name)
        rest_mesh = deformer_rest_mesh(deformer)
        if not rest_mesh:
            raise RuntimeError(f"'{deformer}' のレストメッシュが見つかりません")
        net_str = cmds.getAttr(f"{cn_shape}.netData") or ""
        if not net_str:
            return False
        if n_per_spline is None:
            n_per_spline = 5
            try:
                old = json.loads(cmds.getAttr(f"{deformer}.restIsectData") or "{}")
                n_per_spline = int(old.get("n_per_spline", 5))
            except Exception:
                pass
        bind_s, frames_s, isect_s = self.compute_bind_data(
            rest_mesh, cn_shape, n_per_spline=n_per_spline,
            net_str=net_str, use_cpp=use_cpp)
        cmds.setAttr(f"{deformer}.poissonBindData", bind_s, type="string")
        cmds.setAttr(f"{deformer}.restFrameData", frames_s, type="string")
        cmds.setAttr(f"{deformer}.restIsectData", isect_s, type="string")
        return True

    def create_from_curvenet(
        self,
        mesh_name: str,
        cn_node_name: str,
        n_per_spline: int = 5,
        falloff_mode: int = None,
        use_cpp: Optional[bool] = None,
    ) -> str:
        """Poisson ソルブ (§4) を用いた profileCurveDeformer を作成する。

        ``retopoGuideNode.outNetData`` → ``deformer.retopoGuideData`` を接続し、
        Poisson バインドデータとレストポーズのカーブネットフレームを
        事前計算する。

        パラメータ
        ----------
        mesh_name     : Maya のメッシュトランスフォームまたはシェイプ。
        cn_node_name  : retopoGuideNode のシェイプまたはトランスフォーム。
        n_per_spline  : カーブネットフレーム用のスプラインセグメントあたりのサンプル数。
        falloff_mode  : カーブネットの効果範囲プリセット
                        (:mod:`poisson_solve` の ``FALLOFF_MODE_*``)。
                        省略時は「標準」。
        use_cpp       : None で自動 (C++ プラグインがあればそれを使う)。

        戻り値
        ------
        デフォーマノード名。
        """
        cn_shape = _resolve_curvenet_shape(cn_node_name)
        bind_s, frames_s, isect_s = self.compute_bind_data(
            mesh_name, cn_shape, n_per_spline=n_per_spline, use_cpp=use_cpp)

        deformer = cmds.deformer(mesh_name, type="profileCurveDeformer",
                                 name="profileCurveDeformer1")[0]
        print(f"[ProfileCurveRig] デフォーマ作成: {deformer}")

        cmds.connectAttr(f"{cn_shape}.outNetData",
                         f"{deformer}.retopoGuideData", force=True)
        print(f"[ProfileCurveRig] 接続: {cn_shape}.outNetData → "
              f"{deformer}.retopoGuideData")

        cmds.setAttr(f"{deformer}.poissonBindData", bind_s, type="string")
        cmds.setAttr(f"{deformer}.restFrameData", frames_s, type="string")
        cmds.setAttr(f"{deformer}.restIsectData", isect_s, type="string")

        # 以後の netData 変更 (Undo 含む) で自動リバインドできるように監視を張る
        try:
            from Aru_RetopoTool.editor.curvenet import curve_net_rebind
            curve_net_rebind.ensure_watch(cn_shape)
        except Exception:
            pass

        # カーブネットの効果範囲。バインド時に決めておくと、以後は
        # プルダウンで即座に切り替えられる。
        from Aru_RetopoTool.editor.deformer import poisson_solve as _ps
        mode = (_ps.FALLOFF_MODE_NORMAL if falloff_mode is None
                else int(falloff_mode))
        if cmds.objExists(f"{deformer}.falloffMode"):
            cmds.setAttr(f"{deformer}.falloffMode", mode)
            try:
                bd_d = json.loads(bind_s)
                import numpy as _np
                rv = _np.asarray(bd_d.get("rest_verts") or [[0, 0, 0]], dtype=float)
                rest_size = float(_np.linalg.norm(rv.max(axis=0) - rv.min(axis=0)))
                print("[ProfileCurveRig] 効果範囲: %s (%.3f)"
                      % (_ps.FALLOFF_MODE_LABELS.get(mode, mode),
                         _ps.falloff_from_mode(mode, rest_size)))
            except Exception:
                pass
        return deformer

    def _compute_bind_data_py(
        self,
        mesh_name: str,
        net_str: str,
        n_per_spline: int = 5,
    ) -> tuple[str, str, str]:
        """Python (numpy/scipy) 実装のバインド計算。C++ 版のリファレンス。"""
        import numpy as np

        # レストは「バインドした瞬間のカーブネットの形」でなければならない。
        # デフォーマは実行時に outNetData (CP 編集・スキン・blendShape を
        # 含む最終形状) を読むので、レストに netData (編集を含まない生の
        # 形) を使うと、その差分がそのままメッシュの変形として出てしまう。
        # skinCluster と同じく「バインド時の姿勢がレスト」という契約。
        cn = json.loads(net_str)
        positions = np.array(cn["positions"], dtype=float)
        splines = [tuple(sp) for sp in cn["splines"]]
        if not splines:
            raise RuntimeError("RetopoGuide has no splines.")

        # ---- カーブチェーンを再構築 ------------------------------------
        from Aru_RetopoTool.editor.curvenet.curvenet_frames import (
            sample_curves, detect_intersections,
            compute_corner_frames, compute_all_frames,
            build_curve_chains,
        )

        # 論文 §3: 交点 (3 本以上) / アンカー (1 本) を端とするチェーンに
        # スプラインをグループ化する。2 本を繋ぐだけの端点 (node) で
        # カーブを切ってはならない。
        curves = build_curve_chains(splines)

        # ---- Get mesh data (§3: avg_edge_length for adaptive sampling) -
        mesh_dag = _shape_dag(mesh_name, "mesh")
        mesh_fn = om.MFnMesh(mesh_dag)
        rest_verts = np.array(
            [[p.x, p.y, p.z] for p in mesh_fn.getPoints(om.MSpace.kWorld)])

        # フェースリストを構築
        face_counts, face_verts = mesh_fn.getVertices()
        faces = []
        offset = 0
        for fc in face_counts:
            faces.append([int(face_verts[offset + k]) for k in range(fc)])
            offset += fc

        # 論文 §3: 適応的サンプリング用の平均エッジ長を事前計算
        _edge_set = set()
        for f in faces:
            nf = len(f)
            for li in range(nf):
                va, vb = f[li], f[(li + 1) % nf]
                _edge_set.add((min(va, vb), max(va, vb)))
        if _edge_set:
            avg_edge_length = float(np.mean([
                np.linalg.norm(rest_verts[a] - rest_verts[b])
                for a, b in _edge_set]))
        else:
            avg_edge_length = 1.0

        # ---- レストポーズのカーブネットフレームを計算 (§3) ------------------
        # §3: 交点の CCW ソートとアンカー端点の法線には
        # ニュートラルポーズのサーフェス法線を使う。
        def surface_normal_fn(pos):
            point = om.MPoint(float(pos[0]), float(pos[1]),
                              float(pos[2]))
            # MFnMesh.getClosestPointAndNormal は (点, 法線, フェイスID) を返す。
            result = mesh_fn.getClosestPointAndNormal(
                point, om.MSpace.kWorld)
            normal = result[1]
            n = np.array([normal.x, normal.y, normal.z], dtype=float)
            ln = float(np.linalg.norm(n))
            return n / ln if ln > 1e-12 else np.array([0.0, 1.0, 0.0])

        rest_cd = sample_curves(
            positions,
            splines,
            curves,
            n_per_spline=n_per_spline,
            avg_edge_length=avg_edge_length,
        )

        isect = detect_intersections(rest_cd, tol=_isect_tol(rest_verts))
        corner, _rest_sorted_orders, _rest_tangs_at_isect = compute_corner_frames(
            isect["intersections"], rest_cd,
            surface_normal_fn=surface_normal_fn)
        rest_frames = compute_all_frames(
            rest_cd, isect, corner,
            surface_normal_fn=surface_normal_fn)

        # ---- Poisson 事前計算 (§4) ---------------------------------
        from Aru_RetopoTool.editor.deformer.poisson_solve import precompute as poisson_precompute
        bd = poisson_precompute(
            rest_verts, faces, rest_frames,
            n_trace_oversample=5)

        # ---- レストフレームのシリアライズ -----------------------------------
        rest_frames_json = []
        for rf in rest_frames:
            if rf is None:
                rest_frames_json.append(None)
            else:
                d = {}
                for k, v in rf.items():
                    d[k] = v.tolist() if hasattr(v, 'tolist') else v
                rest_frames_json.append(d)

        bind_json = bd.to_json()
        frames_json = json.dumps(rest_frames_json)

        # レスト交差点トポロジーをシリアライズ (論文 §3: posed では rest のトポロジーを再利用)
        # corner frames もシリアライズ (min-rotation で posed 法線を安定化)
        corner_json = {}
        for (ci_k, side_k), cf_v in corner.items():
            key_str = f"{ci_k},{side_k}"
            corner_json[key_str] = {
                'n_plus': cf_v['n_plus'].tolist(),
                'n_minus': cf_v['n_minus'].tolist(),
                'w_plus': float(cf_v['w_plus']),
                'w_minus': float(cf_v['w_minus']),
            }
        isect_json = {
            'intersections': [
                {'pos': item['pos'].tolist(),
                 'members': [[m[0], m[1], m[2].tolist()] for m in item['members']]}
                for item in isect['intersections']
            ],
            'ep_type': {f"{k[0]},{k[1]}": v for k, v in isect['ep_type'].items()},
            'ep_isect': {f"{k[0]},{k[1]}": v for k, v in isect['ep_isect'].items()},
            'sorted_orders': _rest_sorted_orders,
            'tangents_at_isect': [t.tolist() for t in _rest_tangs_at_isect],
            'rest_positions_pool': positions.tolist(),
            'corner_frames': corner_json,
            'n_per_spline': int(n_per_spline),
            # §3: ニュートラルメッシュの法線を保存し、
            # 評価時にも同じ参照法線を使えるようにする。
            'surface_normal_refs': {
                'intersections': [
                    surface_normal_fn(item['pos']).tolist()
                    for item in isect['intersections']
                ],
                'endpoints': [
                    None if cd is None else [
                        surface_normal_fn(cd['positions'][0]).tolist(),
                        surface_normal_fn(cd['positions'][-1]).tolist(),
                    ]
                    for cd in rest_cd
                ],
            },
        }

        print("[ProfileCurveRig] Poisson バインド完了 (python) - "
              "%d unknowns, %d constraints, "
              "%d cut-faces, %d curve(s)." % (
                  bd.n_v, bd.n_c, len(bd.face_loops), len(rest_frames)))

        return bind_json, frames_json, json.dumps(isect_json)
