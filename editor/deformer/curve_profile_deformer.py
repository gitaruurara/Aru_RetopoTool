"""
Profile Curve Deformer  -  Maya Python Plugin
==============================================
Based on:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)

Uses the two-stage Poisson solve (§4, Eq. 4/5) for smooth,
detail-preserving surface deformation driven by a retopoGuideNode.

Attributes
----------
- ``retopoGuideData``    : string — connected to retopoGuideNode.outNetData
- ``poissonBindData`` : string — Poisson precompute (JSON, set at bind)
- ``restFrameData``   : string — rest-pose curvenet frames (JSON, set at bind)
- ``restIsectData``   : string — rest-pose intersection topology (JSON, set at bind)
- ``falloffMode``     : enum   — カーブネットの効果範囲プリセット
- ``restFalloff``     : double — falloffMode が「カスタム」のときの距離

Node type : profileCurveDeformer  (deformer)
Plugin ID  : 0x00131AB0
"""

import maya.OpenMaya as om
import maya.OpenMayaMPx as ompx
import json
import hashlib

from Aru_RetopoTool.editor.logger import get_logger

_log = get_logger("PCDeformer")

kPluginNodeName = "profileCurveDeformer"
kPluginNodeId   = om.MTypeId(0x00131AB0)


# ---------------------------------------------------------------------------
# Deformer node  (old API — MPxDeformerNode)
# ---------------------------------------------------------------------------

class ProfileCurveDeformer(ompx.MPxDeformerNode):

    aRetopoGuideData    = om.MObject()
    aPoissonBindData = om.MObject()
    aRestFrameData   = om.MObject()
    aRestIsectData   = om.MObject()
    aPinWeights      = om.MObject()
    aUseInputAsRest  = om.MObject()
    aRestFalloff     = om.MObject()
    aFalloffMode     = om.MObject()

    def __init__(self):
        ompx.MPxDeformerNode.__init__(self)
        # --- Poisson cache ---
        self._bind_hash = ""
        self._bind = None             # PoissonBindData
        self._solver_inst = None      # PoissonSolver (cached)
        self._rest_hash = ""
        self._rest_frames = None      # list[dict|None]
        self._isect_hash = ""
        self._rest_isect = None       # dict (isect_info)
        self._solve_hash = ""
        self._new_verts = None        # np.ndarray (N, 3)
        # レストポーズでソルブしたときの残差 (ソルブ結果 - レスト頂点)。
        # カーブネットの外側 (外挿領域) では Poisson 解がレスト形状に
        # 厳密一致しないため、バインド直後でもメッシュが動いてしまう。
        # 一度だけ計算してキャッシュし、以降の解から差し引く。
        self._rest_residual = None    # np.ndarray (N, 3)
        # §5 点単位ソフト拘束の設定ハッシュ
        self._pin_hash = None
        # §5 プロジェクション対レストのキャッシュ
        self._rest_pose_hash = None
        self._rest_frames_warped = None
        self._warp_warned = False

    # ------------------------------------------------------------------
    # dirty propagation
    # ------------------------------------------------------------------
    def setDependentsDirty(self, plug, plugArray):
        attr = plug.attribute()
        dirty_attrs = (
            ProfileCurveDeformer.aRetopoGuideData,
            ProfileCurveDeformer.aPoissonBindData,
            ProfileCurveDeformer.aRestFrameData,
            ProfileCurveDeformer.aRestIsectData,
            ProfileCurveDeformer.aPinWeights,
            ProfileCurveDeformer.aUseInputAsRest,
            ProfileCurveDeformer.aRestFalloff,
            ProfileCurveDeformer.aFalloffMode,
        )
        if attr in dirty_attrs:
            try:
                thisNode = self.thisMObject()
                try:
                    geomAttr = ompx.cvar.MPxGeometryFilter_outputGeom
                except (AttributeError, Exception):
                    fnDep = om.MFnDependencyNode(thisNode)
                    geomAttr = fnDep.attribute("outputGeometry")
                plugArray.append(om.MPlug(thisNode, geomAttr))
            except Exception:
                pass
        return ompx.MPxDeformerNode.setDependentsDirty(self, plug, plugArray)

    # ------------------------------------------------------------------
    # JSON key restoration
    # ------------------------------------------------------------------
    @staticmethod
    def _restore_tuple_keys(d):
        """JSON で文字列化された ``"ci,side"`` キーをタプルに戻す。

        ``ep_type`` / ``ep_isect`` / ``corner_frames`` は
        ``(curve_idx, side)`` のタプルをキーに持つが、JSON の
        オブジェクトキーは文字列しか扱えないため保存時に
        ``"0,1"`` のような文字列に潰れる。これを戻さないと
        ``compute_corner_frames`` などのタプル参照が全て失敗し、
        レスト法線による符号合わせが無効化されてしまう。
        """
        if not isinstance(d, dict):
            return d
        out = {}
        for k, v in d.items():
            if isinstance(k, str) and ',' in k:
                try:
                    parts = k.split(',')
                    out[tuple(int(p) for p in parts)] = v
                    continue
                except ValueError:
                    pass
            out[k] = v
        return out

    # ------------------------------------------------------------------
    # Surface normal reference (§3)
    # ------------------------------------------------------------------
    @staticmethod
    def _make_surface_normal_fn(rest_isect, isect, posed_cd):
        """バインド時のサーフェス法線を返す関数を作る。

        §3 の交点 CCW ソートとアンカー端点法線はニュートラル
        ポーズのサーフェス法線を基準にする。評価時にメッシュを
        再参照できないため、バインド時の値をトポロジー対応で引く。
        参照がない場合は None を返し、従来のフォールバックに戻る。
        """
        import numpy as np

        refs = rest_isect.get('surface_normal_refs') or {}
        ref_pos = []
        ref_vec = []
        isect_list = isect.get('intersections', [])
        for ii, normal in enumerate(refs.get('intersections', [])):
            if ii < len(isect_list):
                ref_pos.append(np.asarray(isect_list[ii]['pos'],
                                          dtype=float))
                ref_vec.append(np.asarray(normal, dtype=float))
        for ci_ref, normals in enumerate(refs.get('endpoints', [])):
            if (not normals or ci_ref >= len(posed_cd)
                    or posed_cd[ci_ref] is None):
                continue
            pts = posed_cd[ci_ref]['positions']
            ref_pos.extend([np.asarray(pts[0], dtype=float),
                            np.asarray(pts[-1], dtype=float)])
            ref_vec.extend([np.asarray(normals[0], dtype=float),
                            np.asarray(normals[1], dtype=float)])
        if not ref_pos:
            return None

        ref_pos_arr = np.asarray(ref_pos)
        ref_vec_arr = np.asarray(ref_vec)

        def _surface_normal(pos):
            delta = ref_pos_arr - np.asarray(pos, dtype=float)
            k = int(np.argmin(np.einsum('ij,ij->i', delta, delta)))
            return ref_vec_arr[k]

        return _surface_normal

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _get_bind(self, json_str):
        h = hashlib.md5(json_str.encode("utf-8")).hexdigest()
        if h != self._bind_hash:
            try:
                from Aru_RetopoTool.editor.deformer.poisson_solve import PoissonBindData
                self._bind = PoissonBindData.from_json(json_str)
                self._bind_hash = h
                self._solver_inst = None   # invalidate cached solver
                self._rest_residual = None  # バインドが変われば残差も無効
                self._pin_hash = None       # 新しい bd にピンを貼り直す
                self._rest_pose_hash = None
                self._rest_frames_warped = None
                self._warp_warned = False
            except Exception as e:
                _log.error("bind parse: %s", e)
                self._bind = None
        return self._bind

    def _get_rest_frames(self, json_str):
        h = hashlib.md5(json_str.encode("utf-8")).hexdigest()
        if h != self._rest_hash:
            try:
                import numpy as np
                data = json.loads(json_str)
                frames = []
                for fd in data:
                    if fd is None:
                        frames.append(None)
                    else:
                        frames.append({k: np.array(v) for k, v in fd.items()})
                # 旧バインド fallback: theta_plus/theta_minus が無い場合は
                # rest frame の法線データから復元する。
                # θ = arctan2(y, x) where PT(n0) vs n_end at endpoint.
                for rf in frames:
                    if rf is None:
                        continue
                    if 'theta_plus' not in rf or 'theta_minus' not in rf:
                        self._recover_rest_theta(rf, np)
                self._rest_frames = frames
                self._rest_hash = h
                self._rest_residual = None  # レストが変われば残差も無効
            except Exception as e:
                _log.error("rest frame parse: %s", e)
                self._rest_frames = None
        return self._rest_frames

    @staticmethod
    def _recover_rest_theta(rf, np):
        """旧バインドの rest frame から theta を逆算する。

        rest frame の n_plus は torsion-corrected 済み。
        PT(n0) を再計算し、n_end との角度差から θ を復元する。
        """
        tangs = rf['tangents']
        M = len(tangs)
        if M < 2:
            rf['theta_plus'] = np.float64(0.0)
            rf['theta_minus'] = np.float64(0.0)
            return

        for side, key_n in [('plus', 'n_plus'), ('minus', 'n_minus')]:
            n_all = rf[key_n]
            n0 = n_all[0]
            # 再 PT: n0 を tangent 沿いに平行輸送 (torsion 補正なし)
            n_curr = n0.copy()
            # _perp_to 相当: n_curr から tangs[0] 方向成分を除去
            n_curr = n_curr - np.dot(n_curr, tangs[0]) * tangs[0]
            nlen = float(np.linalg.norm(n_curr))
            if nlen > 1e-10:
                n_curr = n_curr / nlen
            for i in range(M - 1):
                t0, t1 = tangs[i], tangs[i + 1]
                axis = np.cross(t0, t1)
                sin_a = float(np.linalg.norm(axis))
                cos_a = float(np.clip(np.dot(t0, t1), -1., 1.))
                if sin_a > 1e-10:
                    ax = axis / sin_a
                    ang = float(np.arctan2(sin_a, cos_a))
                    cos_r = np.cos(ang)
                    sin_r = np.sin(ang)
                    n_curr = (n_curr * cos_r
                              + np.cross(ax, n_curr) * sin_r
                              + ax * np.dot(ax, n_curr) * (1 - cos_r))
            # endpoint の torsion-corrected normal
            n_end = n_all[-1]
            n_tgt = n_end - np.dot(n_end, tangs[-1]) * tangs[-1]
            n_tgt_len = float(np.linalg.norm(n_tgt))
            if n_tgt_len > 1e-10:
                n_tgt = n_tgt / n_tgt_len
                cross_v = np.cross(n_tgt, tangs[-1])
                y = float(np.dot(n_curr, cross_v))
                x = float(np.dot(n_curr, n_tgt))
                theta = float(np.arctan2(y, x))
            else:
                theta = 0.0
            rf['theta_' + side] = np.float64(theta)

    def _get_rest_isect(self, json_str):
        """Parse & cache rest intersection topology."""
        h = hashlib.md5(json_str.encode("utf-8")).hexdigest()
        if h != self._isect_hash:
            try:
                import numpy as np
                d = json.loads(json_str)
                isects = []
                for item in d['intersections']:
                    isects.append({
                        'pos': np.array(item['pos']),
                        'members': [(m[0], m[1], np.array(m[2]))
                                    for m in item['members']],
                    })
                ep_type = {}
                for key_str, val in d['ep_type'].items():
                    ci, side = map(int, key_str.split(','))
                    ep_type[(ci, side)] = val
                ep_isect = {}
                for key_str, val in d['ep_isect'].items():
                    ci, side = map(int, key_str.split(','))
                    ep_isect[(ci, side)] = val
                # CCW sort order from bind time (may be absent in old scenes)
                sorted_orders = d.get('sorted_orders', None)
                # Tangent vectors at intersections from bind time
                raw_tangs = d.get('tangents_at_isect', None)
                if raw_tangs is not None:
                    tangents_at_isect = [np.array(t) for t in raw_tangs]
                else:
                    tangents_at_isect = None
                # Rest-pose CP positions for adaptive nk (論文 §3)
                raw_rest_pool = d.get('rest_positions_pool', None)
                rest_positions_pool = (np.array(raw_rest_pool, dtype=float)
                                       if raw_rest_pool is not None
                                       else None)
                # Corner frames from bind time (may be absent in old scenes)
                raw_cf = d.get('corner_frames', None)
                corner_frames = None
                if raw_cf is not None:
                    corner_frames = {}
                    for key_str, cf_v in raw_cf.items():
                        ci_k, side_k = map(int, key_str.split(','))
                        corner_frames[(ci_k, side_k)] = {
                            'n_plus': np.array(cf_v['n_plus']),
                            'n_minus': np.array(cf_v['n_minus']),
                            'w_plus': float(cf_v['w_plus']),
                            'w_minus': float(cf_v['w_minus']),
                        }
                self._rest_isect = {
                    'intersections': isects,
                    'ep_type': ep_type,
                    'ep_isect': ep_isect,
                    'sorted_orders': sorted_orders,
                    'tangents_at_isect': tangents_at_isect,
                    'rest_positions_pool': rest_positions_pool,
                    'corner_frames': corner_frames,
                    # バインド時のサンプル数とサーフェス法線参照。
                    # ここに載せ忘れると deform 側で既定値 5 に
                    # フォールバックし、法線参照も失われる。
                    'n_per_spline': d.get('n_per_spline', 5),
                    'surface_normal_refs': d.get('surface_normal_refs'),
                }
                self._isect_hash = h
            except Exception as e:
                _log.error("isect parse: %s", e)
                self._rest_isect = None
        return self._rest_isect

    # ------------------------------------------------------------------
    # Curve-chain reconstruction (for curvenet_frames.sample_curves)
    # ------------------------------------------------------------------
    @staticmethod
    def _rebuild_curves(splines):
        """論文 §3 のカーブグループ化。

        バインド時 (``curve_profile_rig.create_from_curvenet``) と完全に
        同一のチェーンが得られる必要があるため、共通実装に委譲する。
        ここが食い違うとサンプル数 M と f_c のインデックスが rest と
        ずれ、変形が破綻する。
        """
        from Aru_RetopoTool.editor.curvenet.curvenet_frames import (
            build_curve_chains,
        )
        return build_curve_chains(splines)

    # ------------------------------------------------------------------
    # deform  — two-stage Poisson solve (§4)
    # ------------------------------------------------------------------
    def _apply_pin_weights(self, bd, pin_str):
        """§5 の点単位ソフト拘束を ``bd`` に適用し、キャッシュキーを返す。

        ``pin_str`` は ``{"頂点index": 重み}`` の JSON。空なら
        ピン無し (従来どおりの論文そのままの Eq.6) になる。

        Parameters
        ----------
        bd : PoissonBindData
            バインドデータ。``pin_weights`` が書き換えられる。
        pin_str : str
            pinWeights 属性の値。

        Returns
        -------
        str
            ピン設定のハッシュ。ソルブキャッシュのキーに使う。
        """
        import numpy as np

        pin_hash = hashlib.md5((pin_str or "").encode("utf-8")).hexdigest()
        if pin_hash == self._pin_hash:
            return pin_hash

        w = None
        if pin_str:
            try:
                d = json.loads(pin_str)
                if d:
                    w = np.zeros(bd.n_verts)
                    for k, v in d.items():
                        vi = int(k)
                        if 0 <= vi < bd.n_verts:
                            w[vi] = float(v)
                    if not np.any(w > 0.0):
                        w = None
            except Exception as e:
                _log.warning("pinWeights parse failed: %s", e)
                w = None

        bd.pin_weights = w
        self._pin_hash = pin_hash
        # ピンはレストポーズの解も変えるので残差キャッシュを無効化する
        self._rest_residual = None
        return pin_hash

    def _input_mesh(self, dataBlock, multiIndex):
        """デフォーマ入力のメッシュ MObject を返す (§5)。

        ``geoIter`` はデフォーマセットに含まれる頂点しか回せず、トポロジーも
        取れないので、データブロックから入力ジオメトリそのものを取り出す。
        """
        try:
            inputAttr = ompx.cvar.MPxGeometryFilter_input
            inputGeomAttr = ompx.cvar.MPxGeometryFilter_inputGeom
        except Exception:
            fn = om.MFnDependencyNode(self.thisMObject())
            inputAttr = fn.attribute("input")
            inputGeomAttr = fn.attribute("inputGeometry")
        hInput = dataBlock.outputArrayValue(inputAttr)
        hInput.jumpToElement(multiIndex)
        obj = hInput.outputValue().child(inputGeomAttr).asMesh()
        if obj.isNull():
            return None
        return obj

    def _read_input_world(self, bd, dataBlock, multiIndex, geoIter, matrix):
        """入力ジオメトリのワールド頂点と (必要なら) 面を返す (§5)。

        Returns
        -------
        tuple
            ``(verts | None, faces | None)``
        """
        import numpy as np

        obj = None
        try:
            obj = self._input_mesh(dataBlock, multiIndex)
        except Exception as e:
            _log.debug("入力メッシュの取得に失敗: %s", e)

        if obj is not None:
            fnMesh = om.MFnMesh(obj)
            pts = om.MPointArray()
            fnMesh.getPoints(pts, om.MSpace.kObject)
            n = pts.length()
            verts = np.empty((n, 3))
            for i in range(n):
                p = pts[i] * matrix
                verts[i] = (p.x, p.y, p.z)

            faces = None
            if not bd.can_warp():
                counts = om.MIntArray()
                conn = om.MIntArray()
                fnMesh.getVertices(counts, conn)
                faces = []
                k = 0
                for c in counts:
                    faces.append([conn[k + j] for j in range(c)])
                    k += c
            return verts, faces

        # フォールバック: geoIter から読む (デフォーマセットが部分的なら
        # 含まれない頂点はプロジェクションポーズで埋める)
        base = (bd._proj_snapshot[0] if bd._proj_snapshot is not None
                else bd.rest_verts)
        verts = np.array(base, dtype=float, copy=True)
        n = verts.shape[0]
        geoIter.reset()
        seen = 0
        while not geoIter.isDone():
            vi = geoIter.index()
            if 0 <= vi < n:
                p = geoIter.position(om.MSpace.kObject) * matrix
                verts[vi] = (p.x, p.y, p.z)
                seen += 1
            geoIter.next()
        geoIter.reset()
        return (verts, None) if seen else (None, None)

    def _apply_rest_pose(self, bd, dataBlock, multiIndex, geoIter, matrix,
                         enabled):
        """入力ジオメトリをレストポーズとして ``bd`` に適用する (§5)。

        論文 §5「プロジェクション対レスト」。カットメッシュと
        ``V^T L_h V`` の分解はバインド時のプロジェクションポーズのまま
        再利用し、静止ポリゴンとカーブネットサンプルだけをレスト形状に
        ワープする。これにより skinCluster や blendShape といった上流の
        変形の上にカーブネットのアーティキュレーションを重ねられる。

        Returns
        -------
        tuple
            ``(ワープされたレストサンプル位置 | None, キャッシュキー)``。
        """
        import numpy as np

        if not enabled:
            if bd.rest_override is not None and bd.restore_projection_pose():
                self._rest_pose_hash = None
                self._rest_frames_warped = None
                self._rest_residual = None
                _log.info("レストポーズをプロジェクションポーズに戻した (§5)")
            return None, "off"

        try:
            verts, faces = self._read_input_world(
                bd, dataBlock, multiIndex, geoIter, matrix)
        except Exception as e:
            _log.warning("入力ジオメトリの読み取りに失敗: %s", e)
            return None, "off"
        if verts is None:
            return None, "off"

        if verts.shape[0] != bd.n_verts:
            _log.warning("入力頂点数がバインドと違う (%d vs %d)",
                         verts.shape[0], bd.n_verts)
            return None, "off"

        # Phase2 より前のバインドには cv_warp が無い。その場でも復元できる
        # ので、リバインドを強いずに作り直す。
        if not bd.can_warp() and not bd.ensure_warp(faces):
            if not self._warp_warned:
                self._warp_warned = True
                _log.warning(
                    "このバインドはプロジェクション対レストに対応していない。"
                    "上流の変形を反映するにはリバインドが必要")
            return None, "off"

        # プロジェクションポーズと同じなら何もしない (従来動作と完全一致)
        base = (bd._proj_snapshot[0] if bd._proj_snapshot is not None
                else bd.rest_verts)
        if base.shape == verts.shape and np.abs(base - verts).max() < 1e-9:
            if bd.rest_override is not None and bd.restore_projection_pose():
                self._rest_frames_warped = None
                self._rest_residual = None
            self._rest_pose_hash = None
            return None, "proj"

        key = "%.9g" % float(np.abs(verts).sum())
        if key == self._rest_pose_hash and bd._warped_samples is not None:
            return bd._warped_samples, key

        warped = bd.apply_rest_pose(verts)
        self._rest_pose_hash = key
        self._rest_residual = None      # レストが変われば残差も無効
        self._rest_frames_warped = None
        _log.info("レストポーズを入力ジオメトリに差し替え (§5)")
        return warped, key

    def _warp_rest_frames(self, bd, rest_frames, rest_isect, warped_samples):
        """ワープされたレストカーブネットからスケールドフレームを取り直す。

        論文 §5::

            これらのワープされたポーズを用いて、サンプリングされたカーブネットに
            沿ったスケールドフレームと変形されていないカットフェイスポリゴンの
            レストポーズ値を評価し、それらをサーフェス最適化で使用する。

        Returns
        -------
        list[dict | None]
            ワープ後のレストフレーム。失敗時は元の *rest_frames*。
        """
        import numpy as np

        if warped_samples is None:
            return rest_frames
        if self._rest_frames_warped is not None:
            return self._rest_frames_warped

        try:
            from Aru_RetopoTool.editor.curvenet.curvenet_frames import (
                compute_corner_frames, compute_all_frames,
            )

            warped_cd = []
            for ci, rf in enumerate(rest_frames):
                if rf is None or ci >= len(warped_samples):
                    warped_cd.append(None)
                    continue
                pts = np.asarray(warped_samples[ci], dtype=float)
                old = np.asarray(rf['positions'], dtype=float)
                if pts.shape != old.shape or len(pts) < 2:
                    warped_cd.append(None)
                    continue
                warped_cd.append(_curve_data_from_positions(pts))

            if all(c is None for c in warped_cd):
                return rest_frames

            # 交点位置もワープ後の端点で取り直す
            isect = {
                'ep_type': rest_isect['ep_type'],
                'ep_isect': rest_isect['ep_isect'],
                'intersections': [],
            }
            for item in rest_isect['intersections']:
                members = item['members']
                acc = []
                for m in members:
                    ci_idx, ep_side = m[0], m[1]
                    cd = (warped_cd[ci_idx]
                          if ci_idx < len(warped_cd) else None)
                    if cd is not None:
                        acc.append(cd['positions'][0] if ep_side == 0
                                   else cd['positions'][-1])
                isect['intersections'].append({
                    'pos': np.mean(acc, axis=0) if acc else item['pos'],
                    'members': members,
                })

            snf = self._make_surface_normal_fn(rest_isect, isect, warped_cd)
            corner, _, _ = compute_corner_frames(
                isect['intersections'], warped_cd,
                surface_normal_fn=snf,
                reference_corner_frames=rest_isect.get('corner_frames'),
                rest_sorted_orders=rest_isect.get('sorted_orders'),
                rest_tangents_at_isect=rest_isect.get('tangents_at_isect'))
            out = compute_all_frames(
                warped_cd, isect, corner,
                surface_normal_fn=snf,
                reference_frames=rest_frames)
            # 取り直せなかったカーブは元の値を使う
            out = [o if o is not None else rest_frames[i]
                   for i, o in enumerate(out)]
            self._rest_frames_warped = out
            return out
        except Exception as e:
            _log.warning("レストフレームのワープに失敗、バインド時の値を使用: %s", e)
            return rest_frames

    def deform(self, dataBlock, geoIter, matrix, multiIndex):
        import numpy as np

        # ---- Envelope ------------------------------------------------
        envelope = dataBlock.inputValue(self.envelope).asFloat()
        if envelope < 1e-4:
            return

        # ---- Read attribute strings ----------------------------------
        cn_str = dataBlock.inputValue(
            ProfileCurveDeformer.aRetopoGuideData).asString()
        bind_str = dataBlock.inputValue(
            ProfileCurveDeformer.aPoissonBindData).asString()
        rest_str = dataBlock.inputValue(
            ProfileCurveDeformer.aRestFrameData).asString()
        isect_str = dataBlock.inputValue(
            ProfileCurveDeformer.aRestIsectData).asString()
        pin_str = dataBlock.inputValue(
            ProfileCurveDeformer.aPinWeights).asString()
        if not cn_str or not bind_str or not rest_str or not isect_str:
            return

        # ---- Deserialise / cache -------------------------------------
        bd = self._get_bind(bind_str)
        if bd is None:
            return
        rest_frames = self._get_rest_frames(rest_str)
        if rest_frames is None:
            return
        rest_isect = self._get_rest_isect(isect_str)
        if rest_isect is None:
            return

        # §3: サンプル数はバインド時の値を必ず再利用する。異なると
        # サンプル数 M がずれて f_c の si インデックスが破綻する。
        n_per_spline = int(rest_isect.get('n_per_spline', 5))

        # ---- Solve (cached) ------------------------------------------
        # §5 点単位ソフト拘束: ピン重みは毎回 bd に適用する。
        # 重みが変わったらソルブをやり直す必要があるのでキャッシュキーにも
        # 含める。レスト残差もピンで変わるため無効化する。
        pin_hash = self._apply_pin_weights(bd, pin_str)

        # カーブネットの影響が届く距離。式(5) は勾配しか目標に持たないので
        # カーブに覆われていない領域は遠いカーブに引きずられる。レスト
        # ポーズへの弱い吸着を足して、この距離で影響を止める。
        #
        # 実際の距離はプルダウン (falloffMode) から決める。プリセットは
        # レストメッシュの大きさに対する比なので、シーンのスケールにも
        # 今のポーズにも依存しない。カスタムのときだけ restFalloff を使う。
        from Aru_RetopoTool.editor.deformer import poisson_solve as ps
        fmode = int(dataBlock.inputValue(
            ProfileCurveDeformer.aFalloffMode).asShort())
        falloff = ps.falloff_from_mode(
            fmode, bd.rest_size(),
            float(dataBlock.inputValue(
                ProfileCurveDeformer.aRestFalloff).asDouble()))
        if float(bd.rest_falloff or 0.0) != falloff:
            bd.rest_falloff = falloff
            self._solve_hash = None
        pin_hash = "%s:%.6g" % (pin_hash, falloff)

        # §5 プロジェクション対レスト: 入力ジオメトリをレストポーズとして
        # 使う。上流に何も無ければ入力 = バインドポーズなので no-op。
        use_input_rest = dataBlock.inputValue(
            ProfileCurveDeformer.aUseInputAsRest).asBool()
        warped_samples, rest_pose_key = self._apply_rest_pose(
            bd, dataBlock, multiIndex, geoIter, matrix, use_input_rest)
        if warped_samples is not None:
            rest_frames = self._warp_rest_frames(
                bd, rest_frames, rest_isect, warped_samples)

        cn_hash = hashlib.md5(cn_str.encode("utf-8")).hexdigest()
        cache_key = "%s:%s:%s:%s:%s" % (
            cn_hash, self._bind_hash, self._rest_hash, pin_hash, rest_pose_key)

        if cache_key != self._solve_hash or self._new_verts is None:
            try:
                d = json.loads(cn_str)
                positions = np.array(d["positions"], dtype=float)
                splines = [tuple(sp) for sp in d["splines"]]
                curves = self._rebuild_curves(splines)



                from Aru_RetopoTool.editor.curvenet.curvenet_frames import (
                    sample_curves,
                    compute_corner_frames, compute_all_frames,
                    compute_deformation_gradients,
                )
                from Aru_RetopoTool.editor.deformer.poisson_solve import PoissonSolver

                # rest_positions_pool: バインド時の CP 位置を使って
                # 適応 nk を計算 (論文 §3 — ニュートラルポーズで固定)
                _rest_pos_pool = rest_isect.get('rest_positions_pool')

                posed_cd = sample_curves(
                    positions, splines, curves,
                    n_per_spline=n_per_spline,
                    avg_edge_length=bd.avg_edge_length,
                    rest_positions_pool=_rest_pos_pool)



                # 論文 §3: posed では rest の intersection トポロジーを再利用し
                # intersection の pos を posed の endpoint 位置に更新する
                isect = {
                    'ep_type': rest_isect['ep_type'],
                    'ep_isect': rest_isect['ep_isect'],
                    'intersections': [],
                }
                for ri_item in rest_isect['intersections']:
                    members = ri_item['members']
                    # posed endpoint 位置の平均で pos を更新
                    posed_pos_list = []
                    for m in members:
                        ci_idx, ep_side = m[0], m[1]
                        cd = (posed_cd[ci_idx]
                              if ci_idx < len(posed_cd) and
                              posed_cd[ci_idx] is not None else None)
                        if cd is not None:
                            p = (cd['positions'][0] if ep_side == 0
                                 else cd['positions'][-1])
                            posed_pos_list.append(p)
                    if posed_pos_list:
                        new_pos = np.mean(posed_pos_list, axis=0)
                    else:
                        new_pos = ri_item['pos']
                    isect['intersections'].append({
                        'pos': new_pos,
                        'members': members,
                    })

                # rest の CCW ソート順を再利用して posed の corner frame を
                # 計算する (§3)。順序が変わると n_plus/n_minus の割り当てが
                # rest と食い違い、F が爆発する根本原因になる。
                rest_sorted_orders = rest_isect.get('sorted_orders')
                rest_tangents_at_isect = rest_isect.get('tangents_at_isect')

                # rest corner frames を取得
                # (新バインド: restIsectData に保存済み、
                #  旧バインド: rest_frames の端点法線から再構築)
                rest_corner_frames = rest_isect.get('corner_frames')
                if rest_corner_frames is None:
                    # 旧バインドの後方互換: rest_frames の端点法線を使う。
                    # これは PT+トーション補正済みの値で、コーナー外積法線
                    # とは異なるが、min-rotation の符号参照として使える。
                    rest_corner_frames = {}
                    ep_isect = rest_isect.get('ep_isect', {})
                    for ci_rc in range(len(rest_frames)):
                        rf_rc = rest_frames[ci_rc]
                        if rf_rc is None:
                            continue
                        if (ci_rc, 0) in ep_isect:
                            rest_corner_frames[(ci_rc, 0)] = {
                                'n_plus': np.array(rf_rc['n_plus'][0]),
                                'n_minus': np.array(rf_rc['n_minus'][0]),
                                'w_plus': float(rf_rc['w_plus'][0]),
                                'w_minus': float(rf_rc['w_minus'][0]),
                            }
                        if (ci_rc, 1) in ep_isect:
                            rest_corner_frames[(ci_rc, 1)] = {
                                'n_plus': np.array(rf_rc['n_plus'][-1]),
                                'n_minus': np.array(rf_rc['n_minus'][-1]),
                                'w_plus': float(rf_rc['w_plus'][-1]),
                                'w_minus': float(rf_rc['w_minus'][-1]),
                            }

                # §3: バインド時に取得したニュートラルメッシュ法線を
                # 同じ交点・端点トポロジーに対応付けて再利用する。
                surface_normal_fn = self._make_surface_normal_fn(
                    rest_isect, isect, posed_cd)

                corner, _, _ = compute_corner_frames(
                    isect["intersections"],
                    posed_cd,
                    surface_normal_fn=surface_normal_fn,
                    reference_corner_frames=rest_corner_frames,
                    rest_sorted_orders=rest_sorted_orders,
                    rest_tangents_at_isect=rest_tangents_at_isect)
                posed_frames = compute_all_frames(
                    posed_cd, isect, corner,
                    surface_normal_fn=surface_normal_fn,
                    reference_frames=rest_frames)

                dg = compute_deformation_gradients(
                    rest_frames, posed_frames)

                # PoissonSolver — 初回のみ生成
                if self._solver_inst is None:
                    self._solver_inst = PoissonSolver(bd)

                solved = self._solver_inst.solve_from_frames(
                    posed_frames, dg, rest_frames,
                )
                self._solve_hash = cache_key

                # --- レスト残差の較正 -----------------------------------
                # カーブネットの CP は Maya のメッシュ頂点 (float32) 経由で
                # 運ばれるため、レストポーズでも rest_frames と posed_frames
                # の間に ~1e-6 の量子化差が残る。これが Poisson で増幅され、
                # バインド直後でもメッシュが数 mm 動いてしまう。
                # 「レストと判定できる評価」で一度だけ残差を測り、以降の
                # 解から差し引くことでバインド直後の無変形を保証する。
                if self._rest_residual is None:
                    tol = 1e-3 * max(float(bd.avg_edge_length), 1e-6)
                    at_rest = True
                    for rf_c, pf_c in zip(rest_frames, posed_frames):
                        if rf_c is None or pf_c is None:
                            continue
                        a = np.asarray(rf_c['positions'], dtype=float)
                        b = np.asarray(pf_c['positions'], dtype=float)
                        if a.shape != b.shape or np.abs(a - b).max() > tol:
                            at_rest = False
                            break
                    if at_rest:
                        self._rest_residual = solved - bd.rest_verts
                        _log.info(
                            "レスト残差を較正: max=%.6f mean=%.6f",
                            float(np.abs(self._rest_residual).max()),
                            float(np.abs(self._rest_residual).mean()))

                if self._rest_residual is not None:
                    solved = solved - self._rest_residual

                self._new_verts = solved

            except Exception as e:
                _log.error("Poisson solve: %s", e, exc_info=True)
                return

        new_verts = self._new_verts
        rest_verts = bd.rest_verts
        # bd.rest_verts / ソルバー出力はワールド空間 (バインド時に
        # MSpace.kWorld で取得)。一方 geoIter.setPosition() はオブジェクト
        # 空間を期待するため、ワールド → オブジェクトの逆行列を掛ける。
        mat_inv = matrix.inverse()

        # ---- Absolute position output (Pixar §4.3) --------------------
        # Poisson 出力 = 最終メッシュ位置。
        # final = rest + (poisson - rest) * envelope
        geoIter.reset()
        while not geoIter.isDone():
            vi = geoIter.index()
            if vi < len(new_verts):
                dx = float(new_verts[vi][0]) - float(rest_verts[vi][0])
                dy = float(new_verts[vi][1]) - float(rest_verts[vi][1])
                dz = float(new_verts[vi][2]) - float(rest_verts[vi][2])
                fx = float(rest_verts[vi][0]) + dx * envelope
                fy = float(rest_verts[vi][1]) + dy * envelope
                fz = float(rest_verts[vi][2]) + dz * envelope
                wpt = om.MPoint(fx, fy, fz)
                opt = wpt * mat_inv
                geoIter.setPosition(opt)
            geoIter.next()


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def _curve_data_from_positions(pts):
    """サンプル位置から ``sample_curves`` 互換の辞書を作る (§5 のワープ用)。

    接線は中央差分 (= 前後セグメントの平均、論文 §4.3 の要求)。
    """
    import numpy as np

    M = len(pts)
    diffs = np.diff(pts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
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
    return {'positions': pts, 'tangents': tangs, 'seg_lengths': seg_lens}


def nodeCreator():
    return ompx.asMPxPtr(ProfileCurveDeformer())


def nodeInitializer():
    from Aru_RetopoTool.editor.deformer import poisson_solve as ps
    tAttr = om.MFnTypedAttribute()
    nAttr = om.MFnNumericAttribute()

    # retopoGuideData (string — connected to retopoGuideNode.outNetData)
    ProfileCurveDeformer.aRetopoGuideData = tAttr.create(
        "retopoGuideData", "cnd", om.MFnData.kString)
    tAttr.setStorable(False); tAttr.setReadable(False); tAttr.setWritable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aRetopoGuideData)

    # poissonBindData (JSON — Poisson precompute, set at bind)
    ProfileCurveDeformer.aPoissonBindData = tAttr.create(
        "poissonBindData", "pbd", om.MFnData.kString)
    tAttr.setStorable(True); tAttr.setReadable(True); tAttr.setWritable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aPoissonBindData)

    # restFrameData (JSON — rest-pose curvenet frames, set at bind)
    ProfileCurveDeformer.aRestFrameData = tAttr.create(
        "restFrameData", "rfd", om.MFnData.kString)
    tAttr.setStorable(True); tAttr.setReadable(True); tAttr.setWritable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aRestFrameData)

    # restIsectData (JSON — rest-pose intersection topology, set at bind)
    ProfileCurveDeformer.aRestIsectData = tAttr.create(
        "restIsectData", "rid", om.MFnData.kString)
    tAttr.setStorable(True); tAttr.setReadable(True); tAttr.setWritable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aRestIsectData)

    # pinWeights (JSON — §5 の点単位ソフト拘束。{"頂点index": 重み})
    ProfileCurveDeformer.aPinWeights = tAttr.create(
        "pinWeights", "pnw", om.MFnData.kString)
    tAttr.setStorable(True); tAttr.setReadable(True); tAttr.setWritable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aPinWeights)

    # useInputAsRest (§5 プロジェクション対レスト)
    ProfileCurveDeformer.aUseInputAsRest = nAttr.create(
        "useInputAsRest", "uir", om.MFnNumericData.kBoolean, True)
    nAttr.setStorable(True); nAttr.setReadable(True); nAttr.setWritable(True)
    nAttr.setKeyable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aUseInputAsRest)

    # restFalloff (カーブネットの影響が届く距離。0 で無制限 = 論文そのまま)
    ProfileCurveDeformer.aRestFalloff = nAttr.create(
        "restFalloff", "rfo", om.MFnNumericData.kDouble, 0.0)
    nAttr.setStorable(True); nAttr.setReadable(True); nAttr.setWritable(True)
    nAttr.setKeyable(True)
    nAttr.setMin(0.0)
    nAttr.setSoftMax(200.0)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aRestFalloff)

    # falloffMode (効果範囲のプリセット。メッシュの大きさに対する比で決まる)
    eAttr = om.MFnEnumAttribute()
    ProfileCurveDeformer.aFalloffMode = eAttr.create(
        "falloffMode", "fmd", ps.FALLOFF_MODE_NORMAL)
    for _m in (ps.FALLOFF_MODE_OFF, ps.FALLOFF_MODE_NARROW,
               ps.FALLOFF_MODE_NORMAL, ps.FALLOFF_MODE_WIDE,
               ps.FALLOFF_MODE_CUSTOM):
        eAttr.addField(ps.FALLOFF_MODE_LABELS[_m], _m)
    eAttr.setStorable(True); eAttr.setReadable(True); eAttr.setWritable(True)
    eAttr.setKeyable(True)
    ProfileCurveDeformer.addAttribute(ProfileCurveDeformer.aFalloffMode)

    # attributeAffects
    try:
        outputGeom = ompx.cvar.MPxGeometryFilter_outputGeom
    except (AttributeError, Exception):
        _tmp = ProfileCurveDeformer()
        outputGeom = _tmp.outputGeom
        del _tmp
    for a in (ProfileCurveDeformer.aRetopoGuideData,
              ProfileCurveDeformer.aPoissonBindData,
              ProfileCurveDeformer.aRestFrameData,
              ProfileCurveDeformer.aRestIsectData,
              ProfileCurveDeformer.aPinWeights,
              ProfileCurveDeformer.aUseInputAsRest,
              ProfileCurveDeformer.aRestFalloff,
              ProfileCurveDeformer.aFalloffMode):
        ProfileCurveDeformer.attributeAffects(a, outputGeom)


def initializePlugin(plugin):
    fn = ompx.MFnPlugin(plugin, "ProfileCurveRig", "2.0", "Any")
    fn.registerNode(
        kPluginNodeName, kPluginNodeId,
        nodeCreator, nodeInitializer,
        ompx.MPxNode.kDeformerNode,
    )


def uninitializePlugin(plugin):
    ompx.MFnPlugin(plugin).deregisterNode(kPluginNodeId)
