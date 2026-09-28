# -*- coding: utf-8 -*-
"""
RetopoGuide Draw -- VP2 GeometryOverride + ComponentConverter
============================================================
"""

from __future__ import annotations

import ctypes
import json as _json
import numpy as _np

import maya.api.OpenMaya as om2
import maya.api.OpenMayaRender as omr

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.curve_net_node import (
    RetopoGuideNode, _compute_sculpt_envelopes, _envelope_at,
    _translate_handles_by_ep_cp, _apply_sculpt, _read_sculpt_pose_map,
    _read_sculpt_targets,
    _plug_double, SCULPT_FALLOFF_FRACTION,
)
from Aru_RetopoTool.editor.curvenet import sculpt_pose as _sp
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx

class _ForegroundDraw:
    """Batch screen-space strokes while preserving outline, clipping and ordering."""
    def __init__(self,manager,path,frame):
        import numpy as np
        self.np=np;self.manager=manager;self.pending=[];self.outline=True
        self.color=om2.MColor((.2,1.,1.,1.));self.width=1.
        self.matrix=path.inclusiveMatrix()*frame.getMatrix(omr.MFrameContext.kViewProjMtx)
        self.array_matrix=np.asarray(tuple(self.matrix),dtype=float).reshape(4,4)
        self.viewport=frame.getViewportDimensions()

    def __getattr__(self,name):return getattr(self.manager,name)

    def project(self,p):
        q=p*self.matrix
        if q.w<=1e-10 or q.z < -q.w:return None
        x,y,w,h=self.viewport
        return om2.MPoint(x+(q.x/q.w+1)*w*.5,y+(q.y/q.w+1)*h*.5,0)

    def flush(self):
        if not self.pending:return
        np=self.np;blocks=[];starts=[];offset=0
        for strip in self.pending:
            if isinstance(strip,np.ndarray):
                block=np.column_stack((strip,np.ones(len(strip))))
            else:
                block=np.asarray([(p.x,p.y,p.z,p.w) for p in strip])
            blocks.append(block)
            starts.extend(range(offset,offset+len(strip)-1));offset+=len(strip)
        self.pending=[]
        if not starts:return
        clip=np.concatenate(blocks)@self.array_matrix
        visible=(clip[:,3]>1e-10)&(clip[:,2]>=-clip[:,3])
        starts=np.asarray(starts,dtype=np.int32)
        starts=starts[visible[starts]&visible[starts+1]]
        if not len(starts):return
        indices=np.column_stack((starts,starts+1)).ravel();q=clip[indices]
        x,y,w,h=self.viewport
        xy=q[:,:2]/q[:,3,None];xy=(xy+1)*np.asarray((w*.5,h*.5))+np.asarray((x,y))
        lines=om2.MPointArray(np.column_stack((xy,np.zeros(len(xy)))).tolist())
        if self.outline:
            self.manager.setColor(om2.MColor((.025,.055,.07,1.)))
            self.manager.setLineWidth(self.width+2.);self.manager.lineList(lines,True)
            self.manager.setColor(self.color);self.manager.setLineWidth(self.width)
        self.manager.lineList(lines,True)

    def setColor(self,color):
        self.flush();self.color=color;self.manager.setColor(color)

    def setLineWidth(self,width):
        self.flush();self.width=width;self.manager.setLineWidth(width)

    def point(self,p):
        self.flush();p=self.project(p)
        if p is not None:self.manager.point2d(p)

    def line(self,a,b):
        if self.outline:self.flush();self.outline=False
        self.pending.append((a,b))

    def lineStrip(self,points,draw2D):
        if draw2D:self.flush();return self.manager.lineStrip(points,True)
        if not self.outline:self.flush();self.outline=True
        self.pending.append(points)

    def endDrawInXray(self):
        self.flush();self.manager.endDrawInXray()

    def endDrawable(self):
        self.flush();self.manager.endDrawable()


class _WorldForegroundDraw(_ForegroundDraw):
    """GPU preview guide pass owns depth; retain world coordinates for camera motion."""
    def __init__(self,*args):
        super().__init__(*args);self.point_pending=[];self.point_size=None

    def flush(self):
        if self.pending:
            np=self.np
            if all(len(strip)==2 for strip in self.pending):
                coords=[(p.x,p.y,p.z) for strip in self.pending for p in strip]
            else:
                blocks=[]
                for strip in self.pending:
                    block=strip if isinstance(strip,np.ndarray) else np.asarray([(p.x,p.y,p.z) for p in strip])
                    if len(block)>1:blocks.append(np.stack((block[:-1],block[1:]),axis=1).reshape(-1,3))
                coords=np.concatenate(blocks).tolist() if blocks else []
            self.pending=[]
            if coords:
                lines=om2.MPointArray(coords)
                if self.outline:
                    self.manager.setColor(om2.MColor((.025,.055,.07,1.)))
                    self.manager.setLineWidth(self.width+2.);self.manager.lineList(lines,False)
                    self.manager.setColor(self.color);self.manager.setLineWidth(self.width)
                self.manager.lineList(lines,False)
        if self.point_pending:
            self.manager.points(om2.MPointArray(self.point_pending),False)
            self.point_pending=[]

    def setColor(self,color):
        if tuple(color)!=tuple(self.color):
            self.flush();self.color=color;self.manager.setColor(color)

    def setPointSize(self,size):
        if size!=self.point_size:
            self.flush();self.point_size=size;self.manager.setPointSize(size)

    def point(self,p):
        if self.pending:self.flush()
        self.point_pending.append((p.x,p.y,p.z))

    def line(self,a,b):
        if self.point_pending:self.flush()
        super().line(a,b)

    def lineStrip(self,points,draw2D):
        if self.point_pending:self.flush()
        super().lineStrip(points,draw2D)

_gpu_world_guides=False


class RetopoGuideNodeData(om2.MUserData):
    """RetopoGuideDrawOverride 用描画データ。"""
    def __init__(self):
        super().__init__(False)  # deleteAfterUse=False
        self.valid = False
        self.positions = []
        self.splines = []
        self.ep_set = set()
        self.handle_set = set()
        self.sel_ep = None
        self.ep_types = {}
        self.selected_components = set()
        self.preview_start_pos = None
        self.preview_end_pos = None

# ======================================================================
# RetopoGuideDrawOverride
# ======================================================================




# ======================================================================
# MPxComponentConverter — VP2 コンポーネント選択変換
# ======================================================================

class RetopoGuideComponentConverter(omr.MPxComponentConverter):
    """VP2 選択ヒットを .cv[i] コンポーネントに変換する。"""

    def __init__(self):
        super().__init__()
        self._comp_fn = om2.MFnSingleIndexedComponent()
        self._comp = om2.MObject()

    @classmethod
    def creator(cls):
        return cls()

    def initialize(self, renderItem):
        self._comp = self._comp_fn.create(om2.MFn.kMeshVertComponent)

    def addIntersection(self, intersection):
        buf_idx = intersection.index
        # _VERTEX_SEL_ITEM のインデックスバッファ位置 → 実際の CV インデックス。
        # 範囲外のヒットは別レンダーアイテム由来の誤検出なので捨てる。
        # (以前はそのまま addElement していたため、存在しない頂点が
        #  選択されることがあった)
        if 0 <= buf_idx < len(_g_active_indices):
            self._comp_fn.addElement(_g_active_indices[buf_idx])

    def component(self):
        return self._comp

    def selectionMask(self):
        return om2.MSelectionMask(om2.MSelectionMask.kSelectCVs)


# ======================================================================
# RetopoGuideGeometryOverride — VP2 描画 + 選択
# ======================================================================

# ComponentConverter と GeometryOverride で共有するインデックスマッピング。
# populateGeometry が書き込み、ComponentConverter.addIntersection が参照する。
# リスト位置 i → 実際の頂点インデックス _g_active_indices[i]
_g_active_indices = []

_VERTEX_SEL_ITEM = "retopoGuideVertexSelect"

# シェイプの表示属性 (curveColor / curveWidth / pointSize / handleSize /
# handleColor / showHandles)。属性が無い旧ノードではこの既定値を使う。
_DEFAULT_STYLE = {
    "curve_color": (0.4, 0.8, 1.0),
    "curve_width": 2.0,
    "point_size": 8.0,
    "handle_size": 6.0,
    "handle_color": (0.3, 0.85, 0.85),
    "show_handles": True,
}


def _read_style(depFn):
    st = dict(_DEFAULT_STYLE)
    try:
        c = depFn.findPlug("curveColor", False)
        st["curve_color"] = tuple(c.child(k).asFloat() for k in range(3))
        c = depFn.findPlug("handleColor", False)
        st["handle_color"] = tuple(c.child(k).asFloat() for k in range(3))
        st["curve_width"] = max(0.5, depFn.findPlug("curveWidth", False).asFloat())
        st["point_size"] = max(1.0, depFn.findPlug("pointSize", False).asFloat())
        st["handle_size"] = max(1.0, depFn.findPlug("handleSize", False).asFloat())
        st["show_handles"] = depFn.findPlug("showHandles", False).asBool()
    except Exception:
        pass
    return st


_BEZIER_N = 24
_BEZIER_BASIS = None


def _bezier_strips(pos, splines, raw=False):
    """全スプラインの描画用折れ線 (MPointArray) を返す。

    150 本 × 25 点を Python ループで作ると 1 フレーム 0.1 s 超になるので
    numpy で一括計算する。numpy が無ければ純 Python にフォールバック。
    """
    global _BEZIER_BASIS
    n_pos = len(pos)
    valid = [sp for sp in splines if all(0 <= i < n_pos for i in sp)]
    if not valid:
        return []
    try:
        import numpy as np
        if _BEZIER_BASIS is None:
            t = np.linspace(0.0, 1.0, _BEZIER_N + 1)
            u = 1.0 - t
            _BEZIER_BASIS = np.stack([u**3, 3*u*u*t, 3*u*t*t, t**3], axis=1)  # (N+1,4)
        P = np.asarray(pos, dtype=float)
        idx = np.asarray(valid, dtype=int)                       # (S,4)
        ctrl = P[idx]                                            # (S,4,3)
        pts = np.einsum("nk,skd->snd", _BEZIER_BASIS, ctrl)      # (S,N+1,3)
        return pts if raw else [om2.MPointArray(strip) for strip in pts.tolist()]
    except ImportError:
        out = []
        for sp in valid:
            p0, p1, p2, p3 = pos[sp[0]], pos[sp[1]], pos[sp[2]], pos[sp[3]]
            arr = om2.MPointArray()
            for i in range(_BEZIER_N + 1):
                t = i / _BEZIER_N
                u = 1.0 - t
                arr.append(om2.MPoint(*[u**3*p0[k] + 3*u*u*t*p1[k] + 3*u*t*t*p2[k] + t**3*p3[k]
                                        for k in range(3)]))
            out.append(arr)
        return out


def _cached_bezier_strips(owner):
    """Reuse exact world-space strips until their four controls change."""
    pos = owner._positions
    key = (len(pos), tuple(map(tuple, owner._splines)), _BEZIER_N)
    if getattr(owner, '_ui_strip_key', None) != key:
        owner._ui_strip_key = key
        owner._ui_strip_controls = [sp for sp in key[1]
                                   if all(0 <= i < len(pos) for i in sp)]
        owner._ui_strip_previous = None
        owner._ui_strips = [None] * len(owner._ui_strip_controls)
    controls = _np.asarray(pos, dtype=float).reshape(-1, 3)
    previous = owner._ui_strip_previous
    if previous is None:
        dirty = list(range(len(owner._ui_strip_controls)))
    else:
        changed = _np.any(controls != previous, axis=1)
        dirty = [i for i, sp in enumerate(owner._ui_strip_controls)
                 if any(changed[j] for j in sp)]
    strips = _bezier_strips(pos, [owner._ui_strip_controls[i] for i in dirty])
    for i, strip in zip(dirty, strips):
        owner._ui_strips[i] = strip
    owner._ui_strip_previous = controls.copy()
    return owner._ui_strips


class RetopoGuideGeometryOverride(omr.MPxGeometryOverride):
    """VP2 ジオメトリオーバーライド: カーブ描画 + コンポーネント選択。

    - updateDG()          : ノードデータ読み込み
    - updateRenderItems() : 選択可能なポイントレンダーアイテム生成
    - populateGeometry()  : 頂点/インデックスバッファ書き込み
    - addUIDrawables()    : Bezier カーブ + マーカー描画
    """

    def __init__(self, obj):
        super().__init__(obj)
        self._obj = obj
        # キャッシュ
        self._positions = []
        self._splines = []
        self._ep_set = set()
        self._handle_set = set()
        self._ep_types = {}
        self._sel_ep = None
        self._mirror_ep = None
        self._drag_ep = None
        self._selected_components = set()
        self._preview_start_pos = None
        self._preview_end_pos = None
        self._active_indices = []  # 現在のコンポーネントモードでヒット対象とするインデックス
        self._is_valid = False
        self._xray = True
        self._xray_priority = 26
        self._style = dict(_DEFAULT_STYLE)

    @classmethod
    def creator(cls, obj):
        return cls(obj)

    def supportedDrawAPIs(self):
        return (omr.MRenderer.kOpenGL
                | omr.MRenderer.kDirectX11
                | omr.MRenderer.kOpenGLCoreProfile)

    def hasUIDrawables(self):
        return True

    # -----------------------------------------------------------------
    # updateDG — DG からデータ読み込み
    # -----------------------------------------------------------------
    def updateDG(self):
        self._is_valid = False
        if _ctx._is_scene_clearing:
            return

        node_obj = self._obj
        if node_obj.isNull() or not om2.MObjectHandle(node_obj).isValid():
            return

        try:
            depFn = om2.MFnDependencyNode(node_obj)
            raw = depFn.findPlug("netData", False).asString()
            cn = RetopoGuideData.from_json_cached(raw) if raw else RetopoGuideData()
        except Exception:
            cn = RetopoGuideData()
        # from_json は分類済み。共有インスタンスなのでここでは触らない。

        # 描画オプション (メッシュに埋もれないよう手前に描く)
        try:
            self._xray = depFn.findPlug("xray", False).asBool()
            self._xray_priority = depFn.findPlug(
                "xrayDepthPriority", False).asInt()
        except Exception:
            self._xray = True
            self._xray_priority = 26
        self._style = _read_style(depFn)

        # Share the node's evaluated result with the retopo generator. Re-reading
        # each control-point plug duplicates warp/sculpt evaluation and API calls.
        try:
            if depFn.hasAttribute('outPositions'):
                packed=depFn.findPlug('outPositions',False).asMObject()
                values=list(om2.MFnDoubleArrayData(packed).array())
                if len(values)%3:raise ValueError('Invalid guide positions')
                # Own the draw snapshot once; GPU sampling can view it directly.
                # Avoid rebuilding Python tuples and converting them back to NumPy.
                positions=_np.array(values,dtype=_np.float64).reshape(-1,3)
            else:
                evaluated=depFn.findPlug('outNetData',False).asString()
                positions=_json.loads(evaluated)['positions'] if evaluated else [list(p) for p in cn.positions]
        except Exception:
            return

        from .gpu_guides import sync_topology
        sync_topology(self, cn, shared_readonly=True)
        ep_set = self._ep_set
        handle_set = self._handle_set
        self._positions = positions
        self._manual_handles = set(getattr(cn, "manual_handles", ()))
        self._sel_ep = _ctx.sel_ep
        # 対称ドラッグ中の相方 (ミラー先)。リロード直後などで無くても落ちない
        self._mirror_ep = getattr(_ctx, "drag_mirror_ep", None)
        # 中ボタンドラッグ中の EP。カーブへのホバー表示の出し分けに使う
        self._drag_ep = getattr(_ctx, "drag_ep", None)

        # コンポーネント選択状態
        self._selected_components = set()
        try:
            sel = om2.MGlobal.getActiveSelectionList()
            for i in range(sel.length()):
                try:
                    dag, comp = sel.getComponent(i)
                    if dag.node() == node_obj and not comp.isNull():
                        if comp.hasFn(om2.MFn.kSingleIndexedComponent):
                            cfn = om2.MFnSingleIndexedComponent(comp)
                            for j in range(cfn.elementCount):
                                self._selected_components.add(
                                    cfn.element(j))
                except Exception:
                    pass
        except Exception:
            pass

        # プレビュー
        sel_ep = _ctx.sel_ep
        preview_end = _ctx.preview_end
        if (sel_ep is not None and preview_end is not None
                and sel_ep < len(positions)):
            self._preview_start_pos = positions[sel_ep]
            self._preview_end_pos = preview_end
        else:
            self._preview_start_pos = None
            self._preview_end_pos = None

        # コンポーネントモードに応じて選択対象インデックスを絞る。
        # "all" でも ep_set | handle_set に限定すること。
        # cn.positions には、EP 削除やマージで参照が外れた「孤立 CV」が
        # 残っている場合がある (_remove_ep はスプラインだけ削除して
        # positions は詰めない)。孤立 CV は addUIDrawables で描画されない
        # ため、range(len(positions)) を使うと画面に何も無い場所を矩形選択
        # しただけで見えない頂点が選ばれてしまう。
        component_mode = _ctx._component_mode
        if component_mode == "ep":
            self._active_indices = sorted(ep_set)
        elif component_mode == "handle":
            self._active_indices = sorted(handle_set)
        elif not self._style.get("show_handles", True):
            # 非表示のハンドルを矩形選択で拾わないようにする
            self._active_indices = sorted(ep_set)
        else:
            self._active_indices = sorted(ep_set | handle_set)

        self._is_valid = True

    def cleanUp(self):
        """シーンクリア等でノードが削除された際に Maya C++ から呼ばれる。
        Python オブジェクトが GC 済みでも安全に処理できるよう守る。
        """
        try:
            self._is_valid = False
            self._positions = []
            self._active_indices = []
        except Exception:
            pass

    # -----------------------------------------------------------------
    # updateSelectionGranularity — コンポーネント選択の有効化
    # -----------------------------------------------------------------
    def updateSelectionGranularity(self, path, selectionContext):
        displayStatus = omr.MGeometryUtilities.displayStatus(path)
        if displayStatus == omr.MGeometryUtilities.kHilite:
            # ハイライト状態 = テンプレートではなくコンポーネント選択可能
            if om2.MGlobal.selectionMode() == om2.MGlobal.kSelectComponentMode:
                globalComponentMask = om2.MGlobal.componentSelectionMask()
            else:
                globalComponentMask = om2.MGlobal.objectSelectionMask()
            supportedMask = om2.MSelectionMask(
                om2.MSelectionMask.kSelectCVs)
            if globalComponentMask.intersects(supportedMask):
                selectionContext.selectionLevel = (
                    omr.MSelectionContext.kComponent)
        elif omr.MPxGeometryOverride.pointSnappingActive():
            selectionContext.selectionLevel = (
                omr.MSelectionContext.kComponent)

    # -----------------------------------------------------------------
    # updateRenderItems — 選択可能なポイントレンダーアイテム
    # -----------------------------------------------------------------
    def updateRenderItems(self, dagPath, renderItemList):
        from .gpu_guides import configure
        configure(self,renderItemList,_gpu_world_guides, foreground=self._xray)
        idx = renderItemList.indexOf(_VERTEX_SEL_ITEM)
        if idx < 0:
            item = omr.MRenderItem.create(
                _VERTEX_SEL_ITEM,
                omr.MRenderItem.DecorationItem,
                omr.MGeometry.kPoints)
            item.setDrawMode(omr.MGeometry.kAll)
            item.setDepthPriority(
                omr.MRenderItem.sDormantPointDepthPriority)
            item.setSelectionMask(
                om2.MSelectionMask(om2.MSelectionMask.kSelectCVs))
            # 小さなポイントで描画 (視覚的描画は addUIDrawables が担当)
            shaderMgr = omr.MRenderer.getShaderManager()
            if shaderMgr:
                shader = shaderMgr.getStockShader(
                    omr.MShaderManager.k3dFatPointShader)
                if shader:
                    shader.setParameter("pointSize", [5.0])
                    shader.setParameter("solidColor",
                                        [0.0, 0.0, 0.0, 0.0])
                    item.setShader(shader)
            renderItemList.append(item)
        else:
            item = renderItemList[idx]

        # 見た目と選択判定がずれないよう、選択用ポイントにも同じ深度優先度を使う
        item.setDepthPriority(
            self._xray_priority if self._xray
            else omr.MRenderItem.sDormantPointDepthPriority)

        # apiMeshShape パターン: hilite 時のみ頂点選択アイテムを有効化
        displayStatus = omr.MGeometryUtilities.displayStatus(dagPath)
        if (displayStatus == omr.MGeometryUtilities.kHilite
                or omr.MPxGeometryOverride.pointSnappingActive()):
            item.enable(self._is_valid and len(self._positions) > 0)
        else:
            item.enable(False)

    # -----------------------------------------------------------------
    # populateGeometry — 頂点/インデックスバッファ
    # -----------------------------------------------------------------
    def populateGeometry(self, requirements, renderItems, geo):
        import ctypes

        gpu_curves=getattr(self,'_gpu_curve_active',False)
        if gpu_curves:
            from .gpu_guides import positions,upload_indices
            vertex_positions=positions(self)
        else:vertex_positions=self._positions
        nPos = len(vertex_positions)
        if nPos == 0:
            return

        # 頂点バッファ (position)
        descList = requirements.vertexRequirements()
        for i in range(len(descList)):
            desc = descList[i]
            if desc.semantic == omr.MGeometry.kPosition:
                vb = geo.createVertexBuffer(desc)
                addr = vb.acquire(nPos, True)
                if addr:
                    if gpu_curves:
                        ctypes.memmove(addr,vertex_positions.ctypes.data,vertex_positions.nbytes)
                    else:
                        buf = (ctypes.c_float * (nPos * 3)).from_address(addr)
                        for pi,p in enumerate(vertex_positions):
                            buf[pi*3:pi*3+3]=p
                    vb.commit(addr)
                break

        if gpu_curves:upload_indices(self,renderItems,geo)

        # インデックスバッファ (頂点選択用)
        # 現在のコンポーネントモードで有効なインデックスのみ参照する。
        # _active_indices が空 = 選択できる点が無い、という意味なので
        # 全点にフォールバックしてはいけない (孤立 CV を拾ってしまう)。
        active = self._active_indices
        _g_active_indices[:] = active
        n_active = len(active)
        if n_active == 0:
            return
        for i in range(len(renderItems)):
            rItem = renderItems[i]
            if rItem.name() == _VERTEX_SEL_ITEM:
                ib = geo.createIndexBuffer(omr.MGeometry.kUnsignedInt32)
                addr = ib.acquire(n_active, True)
                if addr:
                    idx_buf = (ctypes.c_uint32 * n_active).from_address(addr)
                    for j, ai in enumerate(active):
                        idx_buf[j] = ai
                    ib.commit(addr)
                rItem.associateWithIndexBuffer(ib)
                break

    # -----------------------------------------------------------------
    # addUIDrawables — Bezier カーブ + マーカー描画
    # -----------------------------------------------------------------
    def addUIDrawables(self, objPath, drawManager, frameContext):
        if not self._is_valid:
            return
        pos = self._positions

        # UI ドローアブルは既定で選択可能になる。そのままだとコンポーネント
        # モードでカーブ線 (Bezier の線分) やタンジェントラインを矩形選択で
        # 拾ってしまい、線分バッファ上のインデックスがそのまま vtx[N] として
        # 選択されてしまう (ポイントもハンドルも無い場所なのに謎の頂点が
        # 選ばれる原因)。
        # コンポーネント選択は _VERTEX_SEL_ITEM + ComponentConverter が
        # 担当するので、ハイライト時は描画専用にする。
        # オブジェクトモードではカーブをクリックしてノードを選択できるよう
        # 選択可能なままにしておく。
        try:
            hilite = (omr.MGeometryUtilities.displayStatus(objPath)
                      == omr.MGeometryUtilities.kHilite)
        except Exception:
            hilite = False
        if hilite:
            drawManager.beginDrawable(omr.MUIDrawManager.kNonSelectable)
        else:
            drawManager.beginDrawable()

        # カーブネットはメッシュ表面に張り付くため、そのまま描くとメッシュに
        # 埋もれて掴めなくなる。ジョイントの X 線表示と同じく常に手前に描く。
        # (深度優先度は面とほぼ同じ奥行きにしか効かないので、浮いたハンドルや
        #  めり込んだ点には足りない)
        xray_begun = False
        if self._xray:
            drawManager.setDepthPriority(self._xray_priority)
            try:
                drawManager.beginDrawInXray()
                xray_begun = True
            except Exception:
                pass

        if self._xray:
            drawManager=(_WorldForegroundDraw if _gpu_world_guides else _ForegroundDraw)(drawManager,objPath,frameContext)
        st = getattr(self, "_style", None) or _DEFAULT_STYLE
        cr, cg, cb = st["curve_color"]
        psz = st["point_size"]
        hsz = st["handle_size"]

        # ---- Bezier カーブ ----
        drawManager.setColor(om2.MColor([cr, cg, cb, 1.0]))
        drawManager.setLineWidth(st["curve_width"])
        if not getattr(self,'_gpu_curve_active',False):
            for pts in (_bezier_strips(pos, self._splines, raw=True)
                        if isinstance(drawManager, _ForegroundDraw)
                        else _cached_bezier_strips(self)):
                drawManager.lineStrip(pts, False)

        if isinstance(drawManager, _WorldForegroundDraw) or not isinstance(drawManager, _ForegroundDraw):
            from .gpu_guides import draw_controls
            draw_controls(self, drawManager, st, wrapped=isinstance(drawManager, _WorldForegroundDraw))
        else:
            # ---- ハンドル タンジェントライン ----
            # 選択中のハンドルは非表示でも描く (どこを掃んでいるか見えないと困る)
            show_h = st["show_handles"]
            vis_handles = [hi for hi in self._handle_set
                           if show_h or hi in self._selected_components]
            drawManager.setColor(om2.MColor([0.55, 0.55, 0.55, 0.7]))
            drawManager.setLineWidth(1.0)
            for sp in self._splines:
                if any(i >= len(pos) for i in sp):
                    continue
                if show_h or sp[1] in self._selected_components:
                    drawManager.line(om2.MPoint(*pos[sp[0]]),
                                     om2.MPoint(*pos[sp[1]]))
                if show_h or sp[2] in self._selected_components:
                    drawManager.line(om2.MPoint(*pos[sp[2]]),
                                     om2.MPoint(*pos[sp[3]]))

            # ---- EP マーカー ----
            for ep in self._ep_set:
                if ep >= len(pos):
                    continue
                p = pos[ep]
                if ep in self._selected_components or self._sel_ep == ep:
                    drawManager.setColor(om2.MColor([0.0, 1.0, 0.0, 1.0]))
                    drawManager.setPointSize(psz * 1.75)
                elif self._mirror_ep == ep:
                    # 対称ドラッグで一緒に動いている相方
                    drawManager.setColor(om2.MColor([0.0, 0.8, 1.0, 1.0]))
                    drawManager.setPointSize(psz * 1.75)
                elif self._ep_types.get(ep) == "intersection":
                    drawManager.setColor(om2.MColor([1.0, 0.2, 0.2, 1.0]))
                    drawManager.setPointSize(psz * 1.25)
                else:
                    drawManager.setColor(om2.MColor([1.0, 0.9, 0.0, 1.0]))
                    drawManager.setPointSize(psz)
                drawManager.point(om2.MPoint(p[0], p[1], p[2]))

            # ---- ハンドル マーカー ----
            hr, hg, hb = st["handle_color"]
            for hi in vis_handles:
                if hi >= len(pos):
                    continue
                p = pos[hi]
                if hi in self._selected_components:
                    drawManager.setColor(om2.MColor([0.0, 1.0, 0.0, 1.0]))
                    drawManager.setPointSize(hsz * 1.35)
                elif hi in getattr(self, "_manual_handles", ()):
                    # 手で置いたハンドル (自動フィットしない) は暖色で区別
                    drawManager.setColor(om2.MColor([1.0, 0.75, 0.3, 1.0]))
                    drawManager.setPointSize(hsz * 1.15)
                else:
                    drawManager.setColor(om2.MColor([hr, hg, hb, 1.0]))
                    drawManager.setPointSize(hsz)
                drawManager.point(om2.MPoint(p[0], p[1], p[2]))

        # ---- スクリーン空間で狙っているカーブのハイライト ----
        # 新しく追加した状態フィールドなので、リロード直後などで
        # 参照できなくてもこの後のプレビュー描画を巻き添えにしない
        hov = getattr(_ctx, "hover_spline", None)
        if hov is not None and (self._preview_end_pos is not None
                                or self._drag_ep is not None):
            try:
                hsi, ht, _hwp = hov
                if 0 <= hsi < len(self._splines):
                    hsp = self._splines[hsi]
                    if not any(i >= len(pos) for i in hsp):
                        q0, q1 = pos[hsp[0]], pos[hsp[1]]
                        q2, q3 = pos[hsp[2]], pos[hsp[3]]

                        def _bz(t):
                            u = 1.0 - t
                            return om2.MPoint(*[
                                u**3*q0[k] + 3*u**2*t*q1[k]
                                + 3*u*t**2*q2[k] + t**3*q3[k]
                                for k in range(3)])

                        drawManager.setColor(om2.MColor([1.0, 0.4, 1.0, 1.0]))
                        drawManager.setLineWidth(4.0)
                        hpts = om2.MPointArray()
                        for i in range(25):
                            hpts.append(_bz(i / 24.0))
                        drawManager.lineStrip(hpts, False)
                        # 交点が作られる位置
                        drawManager.setPointSize(12.0)
                        drawManager.point(_bz(ht))
            except Exception:
                pass

        # ---- プレビューカーブ + プレビューポイント ----
        if (self._preview_start_pos is not None
                and self._preview_end_pos is not None):
            p0 = self._preview_start_pos
            p3 = self._preview_end_pos
            drawManager.setColor(om2.MColor([0.4, 0.8, 1.0, 0.4]))
            drawManager.setLineWidth(1.5)
            pts = om2.MPointArray()
            N = 24
            for i in range(N + 1):
                t = i / N
                pts.append(om2.MPoint(
                    p0[0] + (p3[0] - p0[0]) * t,
                    p0[1] + (p3[1] - p0[1]) * t,
                    p0[2] + (p3[2] - p0[2]) * t,
                ))
            drawManager.lineStrip(pts, False)
            drawManager.setColor(om2.MColor([1.0, 0.9, 0.0, 0.5]))
            drawManager.setPointSize(10.0)
            drawManager.point(om2.MPoint(*p3))

        # ---- リングカット プレビュー ----
        ring_preview = _ctx.ring_preview
        if ring_preview and len(ring_preview) >= 3:
            drawManager.setColor(om2.MColor([1.0, 0.7, 0.0, 0.8]))
            drawManager.setLineWidth(2.5)
            ring_pts = om2.MPointArray()
            for rp in ring_preview:
                ring_pts.append(om2.MPoint(rp[0], rp[1], rp[2]))
            # 閉ループにするため始点を末尾に追加
            ring_pts.append(om2.MPoint(
                ring_preview[0][0], ring_preview[0][1], ring_preview[0][2]))
            drawManager.lineStrip(ring_pts, False)
            # EP マーカー
            drawManager.setColor(om2.MColor([1.0, 0.9, 0.0, 0.9]))
            drawManager.setPointSize(8.0)
            for rp in ring_preview:
                drawManager.point(om2.MPoint(rp[0], rp[1], rp[2]))

        # ---- freecut ドラッグ線プレビュー ----
        ring_line = _ctx.ring_line
        if ring_line and len(ring_line) == 2:
            drawManager.setColor(om2.MColor([1.0, 0.5, 0.0, 0.5]))
            drawManager.setLineWidth(1.5)
            drawManager.line(
                om2.MPoint(ring_line[0][0], ring_line[0][1], ring_line[0][2]),
                om2.MPoint(ring_line[1][0], ring_line[1][1], ring_line[1][2]))

        if xray_begun:
            drawManager.endDrawInXray()
        drawManager.endDrawable()
