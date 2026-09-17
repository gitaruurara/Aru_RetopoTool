# -*- coding: utf-8 -*-
"""カットメッシュ デバッグロケータ (§4.1)
=============================================
参考論文:
  "Character Articulation through Profile Curves"
  F. de Goes, W. Sheffler, K. Fleischer  (Pixar / SIGGRAPH 2022)

``AruCutMeshLocator`` はカットメッシュを VP2 上に直接描画するロケータ。
実体のポリゴンを作らないためマテリアル割り当てが不要で、シーンにジオメトリ
を残さず、書き出しやスキニングにも影響しない。

描画データはデフォーマの ``poissonBindData`` から
``cut_mesh_debug.build_topology()`` で組み立て、モードやデフォーマが
変わったときだけ作り直す。``live`` が有効なときはデフォーマ出力メッシュの
現在の頂点座標を毎リフレッシュで読み、カット頂点のアフィンバインドを
評価し直して変形に追従させる。

ノード構成
----------
- ``CutMeshLocator``     : MPxLocatorNode (API 1.0)
- ``CutMeshDrawOverride``: MPxDrawOverride (API 2.0)

既存の retopoGuideNode と同じく、v1 のノード登録に対して v2 の描画オーバーライド
を組み合わせる構成になっている。
"""

from __future__ import annotations

import traceback

import maya.OpenMaya as om1
import maya.OpenMayaMPx as ompx
import maya.api.OpenMaya as om2
import maya.api.OpenMayaRender as omr
import maya.api.OpenMayaUI as omui2

kDrawDbClassification = "drawdb/geometry/AruCutMeshLocator"
kDrawRegistrantId = "AruCutMeshLocatorPlugin"


# ======================================================================
# ロケータノード (API 1.0)
# ======================================================================

class CutMeshLocator(ompx.MPxLocatorNode):
    """カットメッシュを描画するロケータ。

    Attributes
    ----------
    aDeformer : MObject
        描画元の profileCurveDeformer 名 (string)。
    aMode : MObject
        色分けモード (enum)。``cut_mesh_debug.MODES`` と同じ並び。
    aShrink : MObject
        カットフェイスを重心方向へ縮める割合 (double)。
    aOpacity : MObject
        面の不透明度 (double)。
    aShowFaces / aShowWire : MObject
        面 / ワイヤの表示切り替え (bool)。
    """

    kNodeName = "AruCutMeshLocator"
    kNodeId = om1.MTypeId(0x00131AD4)

    aDeformer = om1.MObject()
    aMode = om1.MObject()
    aShrink = om1.MObject()
    aOpacity = om1.MObject()
    aShowFaces = om1.MObject()
    aShowWire = om1.MObject()
    aLive = om1.MObject()

    def __init__(self):
        ompx.MPxLocatorNode.__init__(self)

    @staticmethod
    def creator():
        return ompx.asMPxPtr(CutMeshLocator())

    @staticmethod
    def initialize():
        tfn = om1.MFnTypedAttribute()
        nfn = om1.MFnNumericAttribute()
        efn = om1.MFnEnumAttribute()

        s = om1.MFnStringData().create("")
        CutMeshLocator.aDeformer = tfn.create(
            "deformer", "dfm", om1.MFnData.kString, s)
        tfn.setStorable(True)
        tfn.setKeyable(False)
        CutMeshLocator.addAttribute(CutMeshLocator.aDeformer)

        CutMeshLocator.aMode = efn.create("mode", "mod", 0)
        efn.addField("block", 0)
        efn.addField("side", 1)
        efn.addField("curve", 2)
        efn.addField("constraint", 3)
        efn.setStorable(True)
        efn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aMode)

        CutMeshLocator.aShrink = nfn.create(
            "shrink", "shk", om1.MFnNumericData.kDouble, 0.12)
        nfn.setMin(0.0)
        nfn.setMax(0.45)
        nfn.setStorable(True)
        nfn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aShrink)

        CutMeshLocator.aOpacity = nfn.create(
            "opacity", "opc", om1.MFnNumericData.kDouble, 1.0)
        nfn.setMin(0.05)
        nfn.setMax(1.0)
        nfn.setStorable(True)
        nfn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aOpacity)

        CutMeshLocator.aShowFaces = nfn.create(
            "showFaces", "shf", om1.MFnNumericData.kBoolean, True)
        nfn.setStorable(True)
        nfn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aShowFaces)

        CutMeshLocator.aShowWire = nfn.create(
            "showWireframe", "shw", om1.MFnNumericData.kBoolean, True)
        nfn.setStorable(True)
        nfn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aShowWire)

        CutMeshLocator.aLive = nfn.create(
            "live", "liv", om1.MFnNumericData.kBoolean, True)
        nfn.setStorable(True)
        nfn.setKeyable(True)
        CutMeshLocator.addAttribute(CutMeshLocator.aLive)

    def isBounded(self):
        return True

    def boundingBox(self):
        """キャッシュ済み描画バッファからバウンディングボックスを返す。"""
        bb = om1.MBoundingBox()
        try:
            fn = om1.MFnDependencyNode(self.thisMObject())
            buf = _cached_buffers(fn.name())
        except Exception:
            buf = None
        if buf is None:
            bb.expand(om1.MPoint(-1.0, -1.0, -1.0))
            bb.expand(om1.MPoint(1.0, 1.0, 1.0))
            return bb
        bb.expand(om1.MPoint(*[float(v) for v in buf.bbox_min]))
        bb.expand(om1.MPoint(*[float(v) for v in buf.bbox_max]))
        return bb


# ======================================================================
# 描画バッファのキャッシュ
# ======================================================================

#: ノード名 -> _NodeCache
_BUFFER_CACHE = {}


class _NodeCache(object):
    """ロケータ 1 ノード分の描画キャッシュ。

    トポロジ・色・バインドは重いので ``topo_sig`` (デフォーマ + モード) が
    変わったときだけ作り直す。変形追従はカット頂点座標の入れ替えだけで済む
    ため、毎フレームでも numpy の行列積 1 回で更新できる。

    Attributes
    ----------
    topo_sig : tuple
        トポロジ再構築の判定キー (deformer, mode)。
    topo : CutMeshTopology | None
        トポロジ。構築に失敗した場合は None。
    geo_sig : tuple | None
        座標バッファ再構築の判定キー (shrink, live, 頂点座標のハッシュ)。
    buf : CutMeshDrawBuffers | None
        描画バッファ。
    gpu : tuple | None
        (三角形頂点, 三角形カラー, 線分頂点)。
    colors : om2.MColorArray | None
        カラー配列。トポロジが同じなら不透明度以外は使い回せる。
    color_alpha : float
        ``colors`` を作ったときの不透明度。
    """

    __slots__ = ("topo_sig", "topo", "geo_sig", "buf", "gpu",
                 "colors", "color_alpha")

    def __init__(self):
        self.topo_sig = None
        self.topo = None
        self.geo_sig = None
        self.buf = None
        self.gpu = None
        self.colors = None
        self.color_alpha = -1.0


def _read_settings(node_name):
    """ロケータのアトリビュートを読む。

    Parameters
    ----------
    node_name : str
        ロケータシェイプ名。

    Returns
    -------
    tuple
        (deformer, mode, shrink, opacity, show_faces, show_wire, live)。
    """
    import maya.cmds as cmds
    from Aru_RetopoTool.editor.deformer import cut_mesh_debug

    mode_i = cmds.getAttr("%s.mode" % node_name)
    try:
        live = bool(cmds.getAttr("%s.live" % node_name))
    except Exception:
        live = False
    return (cmds.getAttr("%s.deformer" % node_name) or "",
            cut_mesh_debug.MODES[mode_i],
            float(cmds.getAttr("%s.shrink" % node_name)),
            float(cmds.getAttr("%s.opacity" % node_name)),
            bool(cmds.getAttr("%s.showFaces" % node_name)),
            bool(cmds.getAttr("%s.showWireframe" % node_name)),
            live)


def _colors_array(cache, topo, opacity):
    """三角形カラー配列を返す。不透明度が変わったときだけ作り直す。

    Parameters
    ----------
    cache : _NodeCache
        ノードキャッシュ。
    topo : CutMeshTopology
        トポロジ。``tri_colors`` は (3T, 4) の RGBA。
    opacity : float
        面のアルファ。

    Returns
    -------
    om2.MColorArray
        カラー配列。
    """
    if cache.colors is not None and abs(cache.color_alpha - opacity) < 1e-6:
        return cache.colors
    rgba = topo.tri_colors.copy()
    rgba[:, 3] = opacity
    cache.colors = om2.MColorArray(rgba.tolist())
    cache.color_alpha = opacity
    return cache.colors


def _cached_buffers(node_name, want_gpu=False):
    """描画バッファを取得する。必要なときだけ再構築する。

    Parameters
    ----------
    node_name : str
        ロケータシェイプ名。
    want_gpu : bool
        True なら om2 の描画配列も併せて返す。

    Returns
    -------
    CutMeshDrawBuffers | tuple | None
        ``want_gpu`` が False ならバッファ、True なら
        (バッファ, 三角形頂点, 三角形カラー, 線分頂点)。
        取得できない場合は None。
    """
    from Aru_RetopoTool.editor.deformer import cut_mesh_debug

    try:
        dfm, mode, shrink, opacity, _sf, _sw, live = _read_settings(node_name)
    except Exception:
        return None
    if not dfm:
        return None

    cache = _BUFFER_CACHE.get(node_name)
    if cache is None:
        cache = _NodeCache()
        _BUFFER_CACHE[node_name] = cache

    topo_sig = (dfm, mode)
    if cache.topo_sig != topo_sig:
        cache.topo_sig = topo_sig
        cache.geo_sig = None
        cache.buf = None
        cache.gpu = None
        cache.colors = None
        try:
            cache.topo = cut_mesh_debug.build_topology(dfm, mode=mode)
        except Exception:
            traceback.print_exc()
            cache.topo = None
    if cache.topo is None:
        return None

    topo = cache.topo
    verts = cut_mesh_debug.deformed_mesh_points(dfm) if live else None
    # 頂点座標の総和で変形を検知する。全頂点比較より速く、実用上は十分。
    stamp = None if verts is None else float(verts.sum())
    geo_sig = (round(shrink, 5), bool(live), stamp)
    if cache.geo_sig != geo_sig or cache.buf is None:
        try:
            pos = cut_mesh_debug.evaluate_positions(topo, verts)
            cache.buf = cut_mesh_debug.buffers_from_positions(
                topo, pos, shrink)
        except Exception:
            traceback.print_exc()
            cache.geo_sig = geo_sig
            cache.buf = None
            return None
        cache.geo_sig = geo_sig
        cache.gpu = None

    if cache.buf is None:
        return None
    if not want_gpu:
        return cache.buf

    if cache.gpu is None:
        cache.gpu = (om2.MPointArray(cache.buf.tri_points.tolist()),
                     om2.MPointArray(cache.buf.line_points.tolist()))
    tri_pts, line_pts = cache.gpu
    return (cache.buf, tri_pts, _colors_array(cache, topo, opacity), line_pts)


def invalidate(node_name=None):
    """描画バッファのキャッシュを破棄する。

    Parameters
    ----------
    node_name : str | None
        対象ノード名。None なら全て破棄する。
    """
    if node_name is None:
        _BUFFER_CACHE.clear()
    else:
        _BUFFER_CACHE.pop(node_name, None)


# ======================================================================
# 描画オーバーライド (API 2.0)
# ======================================================================

class CutMeshUserData(om2.MUserData):
    """CutMeshDrawOverride 用の描画データ。"""

    def __init__(self):
        super().__init__(False)  # deleteAfterUse=False
        self.tri_points = None
        self.tri_colors = None
        self.line_points = None
        self.show_faces = True
        self.show_wire = True


class CutMeshDrawOverride(omr.MPxDrawOverride):
    """カットメッシュを MUIDrawManager で直接描画する。

    シェーダを介さずに描画するのでマテリアル割り当てが不要で、頂点カラーが
    そのまま出る。論文 §4.2 の ``V^T L_h V`` の連結成分をそのまま色として
    見られるため、変形がカーブネットの片側に閉じ込められているかを即座に
    判定できる。
    """

    @staticmethod
    def creator(obj):
        return CutMeshDrawOverride(obj)

    def __init__(self, obj):
        # isAlwaysDirty=True: 変形追従のため毎リフレッシュで prepareForDraw を
        # 呼ばせる。実際の再計算は _cached_buffers 側のシグネチャで抑制する。
        super().__init__(obj, None, True)

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def hasUIDrawables(self):
        return True

    def isBounded(self, objPath, cameraPath):
        return True

    def boundingBox(self, objPath, cameraPath):
        bb = om2.MBoundingBox()
        buf = _cached_buffers(_shape_name(objPath))
        if buf is None:
            bb.expand(om2.MPoint(-1.0, -1.0, -1.0))
            bb.expand(om2.MPoint(1.0, 1.0, 1.0))
            return bb
        bb.expand(om2.MPoint(*[float(v) for v in buf.bbox_min]))
        bb.expand(om2.MPoint(*[float(v) for v in buf.bbox_max]))
        return bb

    def prepareForDraw(self, objPath, cameraPath, frameContext, oldData):
        data = oldData
        if not isinstance(data, CutMeshUserData):
            data = CutMeshUserData()

        name = _shape_name(objPath)
        hit = _cached_buffers(name, want_gpu=True)
        if hit is None:
            data.tri_points = None
            data.line_points = None
            return data

        _buf, tri_pts, tri_cols, line_pts = hit
        try:
            settings = _read_settings(name)
            show_faces, show_wire = settings[4], settings[5]
        except Exception:
            show_faces, show_wire = True, True

        data.tri_points = tri_pts
        data.tri_colors = tri_cols
        data.line_points = line_pts
        data.show_faces = show_faces
        data.show_wire = show_wire
        return data

    def addUIDrawables(self, objPath, drawManager, frameContext, data):
        if not isinstance(data, CutMeshUserData) or data.tri_points is None:
            return

        # kNonSelectable: カットメッシュはデバッグ表示なので、モデル全体を
        # 覆う三角形でメッシュやカーブネットのピックを奪わないようにする。
        # (ロケータ自体はアウトライナから選択できる)
        drawManager.beginDrawable(omr.MUIDrawManager.kNonSelectable)
        try:
            if data.show_faces:
                drawManager.mesh(omr.MUIDrawManager.kTriangles,
                                 data.tri_points, color=data.tri_colors)
            if data.show_wire:
                drawManager.setColor(om2.MColor((0.05, 0.05, 0.05, 1.0)))
                drawManager.setLineWidth(1.0)
                drawManager.mesh(omr.MUIDrawManager.kLines, data.line_points)
        except Exception:
            traceback.print_exc()
        finally:
            drawManager.endDrawable()


def _shape_name(objPath):
    """MDagPath からシェイプの部分名を返す。

    Parameters
    ----------
    objPath : om2.MDagPath
        ロケータのパス。

    Returns
    -------
    str
        シェイプ名。
    """
    return om2.MFnDependencyNode(objPath.node()).name()
