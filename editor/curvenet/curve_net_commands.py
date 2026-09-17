# -*- coding: utf-8 -*-
"""
RetopoGuide Commands -- MPxCommand implementations
================================================
"""

from __future__ import annotations

import maya.OpenMaya as om
import maya.OpenMayaMPx as ompx
import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import (
    kPluginNodeName, kCmdCreate, kCmdAddPoint, kCmdRebuild, kCmdUnbind,
    _ctx,
)
from Aru_RetopoTool.editor.curvenet.curve_net_edit import (
    _dirty_shape_view, _get_mesh_fn, _closest_point_on_mesh,
    _reset_control_points, _get_cv_count, bake_control_points,
    RetopoGuideAccessor,
)
from Aru_RetopoTool.editor.curvenet.curve_net_menu import _get_or_create_dragger_ctx

# ===========================================================================

class CmdRetopoGuideSetSkinWeights(ompx.MPxCommand):
    """skinCluster のウェイトを API で一括設定する (Undo 対応)。

    ``skinPercent`` は CV ごとにコマンドが走るので数百 CV では遅い。
    ``MFnSkinCluster.setWeights`` は速いが Undo できないのでこのコマンドで包む。

    使い方::

        cmds.retopoGuideSetSkinWeights(sh="retopoGuideNode1",
                                    d='{"12": {"joint1": 0.5, "joint2": 0.5}}',
                                    nrm=True)
    """
    kName = "retopoGuideSetSkinWeights"

    def __init__(self):
        super().__init__()
        self._shape = ""
        self._sc = ""
        self._new = {}
        self._old = {}
        self._normalize = True

    def doIt(self, args):
        import json as _json
        from Aru_RetopoTool.editor.curvenet import curve_net_edit as _e
        argdb = om.MArgDatabase(self.syntax(), args)
        if not argdb.isFlagSet("-sh") or not argdb.isFlagSet("-d"):
            self.displayError("[retopoGuideSetSkinWeights] -shape と -data は必須です")
            return
        self._shape = argdb.flagArgumentString("-sh", 0)
        data = _json.loads(argdb.flagArgumentString("-d", 0))
        self._new = {int(k): dict(v) for k, v in data.items() if v}
        self._normalize = (argdb.flagArgumentBool("-nrm", 0)
                           if argdb.isFlagSet("-nrm") else True)
        self._sc = _e._find_skincluster(self._shape) or ""
        if not self._sc:
            self.displayError("[retopoGuideSetSkinWeights] skinCluster がありません: %s" % self._shape)
            return
        # Undo 用に現在値を控える (ウェイトの無い CV は空 dict で保持)
        cur = _e.get_skin_weights(self._shape, cv_indices=list(self._new)) or {}
        self._old = {cv: dict(cur.get(cv) or {}) for cv in self._new}
        self.redoIt()

    def redoIt(self):
        from Aru_RetopoTool.editor.curvenet import curve_net_edit as _e
        n = _e.set_skin_weights_bulk(self._shape, self._new, sc=self._sc,
                                     normalize=self._normalize)
        self.setResult(int(n))

    def undoIt(self):
        from Aru_RetopoTool.editor.curvenet import curve_net_edit as _e
        _e.set_skin_weights_bulk(self._shape, self._old, sc=self._sc,
                                 normalize=False, allow_zero=True)

    def isUndoable(self):
        return True

    @classmethod
    def creator(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def newSyntax(cls):
        syn = om.MSyntax()
        syn.addFlag("-sh", "-shape", om.MSyntax.kString)
        syn.addFlag("-d", "-data", om.MSyntax.kString)
        syn.addFlag("-nrm", "-normalize", om.MSyntax.kBoolean)
        return syn


# ===========================================================================

class CmdRetopoGuideCreate(ompx.MPxCommand):
    """選択メッシュに retopoGuideNode を作成してコンテキストへ切り替える。"""
    kName = kCmdCreate

    def __init__(self):
        super().__init__()
        self._node_name: str = ""

    def doIt(self, args):
        sel = cmds.ls(selection=True, type="transform") or []
        mesh_name = ""
        for s in sel:
            if cmds.listRelatives(s, shapes=True, type="mesh"):
                mesh_name = s
                break
        node = cmds.createNode(kPluginNodeName, name="retopoGuideNode#")
        self._node_name = node
        if mesh_name:
            cmds.setAttr("{}.meshName".format(node), mesh_name, type="string")
            try:
                cmds.displayStyle(mesh_name, wireframeOnShaded=True)
            except Exception:
                pass
        cn = RetopoGuideData()
        cmds.setAttr("{}.netData".format(node), cn.to_json(), type="string")

        ctx_name = _get_or_create_dragger_ctx()
        cmds.optionVar(sv=("retopoGuideContext_node", node))
        _ctx.sel_ep = None
        cmds.setToolTo(ctx_name)
        self.setResult(node)

    def undoIt(self):
        if self._node_name and cmds.objExists(self._node_name):
            cmds.delete(self._node_name)

    def redoIt(self):
        self.doIt(om.MArgList())

    def isUndoable(self):
        return True

    @classmethod
    def creator(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def newSyntax(cls):
        return om.MSyntax()


def _set_context_node(ctx_name: str, node_name: str) -> None:
    """optionVar 経由でコンテキストのカレントノードを設定する。"""
    cmds.optionVar(sv=("retopoGuideContext_node", node_name))


class CmdRetopoGuideAddPoint(ompx.MPxCommand):
    """ワールド座標を指定して endpoint を追加する (Script Editor 用)。"""
    kName = kCmdAddPoint

    def __init__(self):
        super().__init__()
        self._node_name: str = ""
        self._cv_idx:    int = -1

    def doIt(self, args):
        argdb = om.MArgDatabase(self.syntax(), args)
        x = argdb.flagArgumentDouble("-x", 0) if argdb.isFlagSet("-x") else 0.0
        y = argdb.flagArgumentDouble("-y", 0) if argdb.isFlagSet("-y") else 0.0
        z = argdb.flagArgumentDouble("-z", 0) if argdb.isFlagSet("-z") else 0.0
        node = (argdb.flagArgumentString("-nd", 0)
                if argdb.isFlagSet("-nd") else
                cmds.optionVar(q="retopoGuideContext_node") or "")
        if not node or not cmds.objExists(node):
            self.displayError("[retopoGuideAddPoint] node not found: " + node)
            return
        self._node_name = node
        acc  = RetopoGuideAccessor(node)
        cn   = acc.read()
        mesh = acc.mesh_name
        if mesh and cmds.objExists(mesh):
            mesh_fn, mesh_dag = _get_mesh_fn(mesh)
            snap_pt, fi, b    = _closest_point_on_mesh(mesh_fn, mesh_dag, [x, y, z])
            self._cv_idx = cn.add_cv(snap_pt, surface=(fi, b))
        else:
            self._cv_idx = cn.add_cv([x, y, z])
        cn.classify_endpoints()
        cmds.setAttr("{}.netData".format(node), cn.to_json(), type="string")
        _dirty_shape_view()
        self.setResult(self._cv_idx)

    def undoIt(self):
        if not self._node_name:
            return
        cn = RetopoGuideAccessor(self._node_name).read()
        if not cn.positions:
            return
        if 0 <= self._cv_idx == len(cn.positions) - 1:
            cn.positions.pop()
            cn.surface_binding.pop()
            cn.classify_endpoints()
            cmds.setAttr("{}.netData".format(self._node_name),
                         cn.to_json(), type="string")
            _dirty_shape_view()

    def isUndoable(self):
        return True

    @classmethod
    def creator(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def newSyntax(cls):
        syn = om.MSyntax()
        syn.addFlag("-x",  "-xPos",    om.MSyntax.kDouble)
        syn.addFlag("-y",  "-yPos",    om.MSyntax.kDouble)
        syn.addFlag("-z",  "-zPos",    om.MSyntax.kDouble)
        syn.addFlag("-nd", "-nodeArg", om.MSyntax.kString)
        return syn


class CmdRetopoGuideRebuild(ompx.MPxCommand):
    """classify_endpoints() + VP2 強制更新。"""
    kName = kCmdRebuild

    def __init__(self):
        super().__init__()

    def doIt(self, args):
        argdb = om.MArgDatabase(self.syntax(), args)
        node = (argdb.flagArgumentString("-nd", 0)
                if argdb.isFlagSet("-nd") else
                cmds.optionVar(q="retopoGuideContext_node") or "")
        if not node or not cmds.objExists(node):
            self.displayError("[retopoGuideRebuild] node not found: " + node)
            return
        acc = RetopoGuideAccessor(node)
        cn  = acc.read()
        if cn.positions:
            acc.write(cn)

    def isUndoable(self):
        return False

    @classmethod
    def creator(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def newSyntax(cls):
        syn = om.MSyntax()
        syn.addFlag("-nd", "-nodeArg", om.MSyntax.kString)
        return syn


class CmdRetopoGuideUnbind(ompx.MPxCommand):
    """カーブネットのスキンバインドを解除し、Orig ノードまで後始末する。

    Maya 標準の DetachSkin は skinCluster を削除しても中間 shape (Orig)
    を残し、``inSurface`` を ``<shape>Orig.worldSurface`` へ繋ぎ替えた
    ままにする。カーブネットにとってこの残骸は有害で、

      * 再バインドのたびに Orig が積み重なる
      * outSurface が Orig のスナップショットを拾い続ける

    といった問題を招く。本コマンドは skinCluster の削除に加えて
    inSurface の接続断と Orig ノードの削除まで行い、バインド前の
    状態へ確実に戻す。

    使い方::

        cmds.retopoGuideUnbind()               # 選択ノード
        cmds.retopoGuideUnbind(nd="retopoGuideNode1")
        cmds.retopoGuideUnbind(bs=True)        # スカルプトを netData へ焼き込む
    """
    kName = kCmdUnbind

    def doIt(self, args):
        argdb = om.MArgDatabase(self.syntax(), args)
        if argdb.isFlagSet("-nd"):
            nodes = [argdb.flagArgumentString("-nd", 0)]
        else:
            nodes = []
            for s in (cmds.ls(selection=True, long=True) or []):
                if cmds.nodeType(s) == kPluginNodeName:
                    nodes.append(s)
                for sh in (cmds.listRelatives(s, shapes=True, fullPath=True)
                           or []):
                    if cmds.nodeType(sh) == kPluginNodeName:
                        nodes.append(sh)
        nodes = [n for n in dict.fromkeys(nodes)
                 if n and cmds.objExists(n)
                 and not cmds.getAttr(n + ".intermediateObject")]
        if not nodes:
            self.displayError(
                "[retopoGuideUnbind] retopoGuideNode が選択されていません。")
            return

        removed = []
        for node in nodes:
            removed += _unbind_curvenet(
                node, bake_sculpt=argdb.isFlagSet("-bs"))
        if removed:
            cmds.inViewMessage(
                amg="retopoGuide: unbound (%s)" % ", ".join(removed),
                pos="midCenter", fade=True)
        self.setResult(removed)

    def isUndoable(self):
        return False

    @classmethod
    def creator(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def newSyntax(cls):
        syn = om.MSyntax()
        syn.addFlag("-nd", "-nodeArg", om.MSyntax.kString)
        syn.addFlag("-bs", "-bakeSculpt", om.MSyntax.kNoArg)
        return syn


_unbind_in_progress = False


def _has_active_deformer(node: str) -> bool:
    """*node* の inSurface に実際のデフォーマが繋がっているかを返す。"""
    for src in (cmds.listConnections(node + ".inSurface", source=True,
                                     destination=False) or []):
        if not cmds.objExists(src):
            continue
        if "geometryFilter" in (cmds.nodeType(src, inherited=True) or []):
            return True
    return False


def _unbind_curvenet(node: str, bake_sculpt: bool = False) -> list:
    """*node* のデフォーマチェーンを解体し、削除したノード名を返す。"""
    global _unbind_in_progress
    removed = []
    # デフォーマ削除は _on_deformer_removed を発火させ、遅延クリーンアップが
    # 割り込んで controlPoints を消す可能性がある。ベイクを先に済ませ、
    # 処理中は自動クリーンアップを抑止する。
    if bake_sculpt:
        try:
            bake_control_points(node)
        except Exception:
            pass

    _unbind_in_progress = True
    try:
        # 上流のデフォーマ (skinCluster / tweak など) を削除する。
        # inSurface の接続元を辿り、geometryFilter だけを対象にする。
        for _ in range(16):
            srcs = cmds.listConnections(node + ".inSurface", source=True,
                                        destination=False) or []
            if not srcs:
                break
            src = srcs[0]
            if not cmds.objExists(src):
                break
            if "geometryFilter" not in (cmds.nodeType(src, inherited=True) or []):
                break
            cmds.delete(src)
            removed.append(src)

        removed += _cleanup_after_unbind(node)
    finally:
        _unbind_in_progress = False
    return removed


def _cleanup_after_unbind(node: str) -> list:
    """デフォーマが外れた retopoGuideNode の後始末を行う。

    1. inSurface に残った接続 (Orig.worldSurface など) を切る
    2. 不要になった中間 shape (Orig) を削除する
    3. controlPoints のスカルプトを破棄する

    3 について: controlPoints はポーズ空間の補正として設計されており、
    バインドポーズでは envelope=0 で消える (`_compute_sculpt_envelope`)。
    デフォーマが外れるとポーズという概念自体が失われ、この補正がフル
    強度で適用されるため、バインドポーズで見えていた形状から突然
    ジャンプしてしまう。よって補正を破棄して見た目を維持する。
    スカルプトを残したい場合は呼び出し側が事前に
    `bake_control_points()` で netData へ焼き込むこと。
    """
    removed = []

    for p in (cmds.listConnections(node + ".inSurface", source=True,
                                   destination=False, plugs=True) or []):
        try:
            cmds.disconnectAttr(p, node + ".inSurface")
        except Exception:
            pass

    for par in (cmds.listRelatives(node, parent=True, fullPath=True) or []):
        for sh in (cmds.listRelatives(par, shapes=True, fullPath=True) or []):
            if sh == node or not cmds.objExists(sh):
                continue
            if cmds.nodeType(sh) != kPluginNodeName:
                continue
            if not cmds.getAttr(sh + ".intermediateObject"):
                continue
            cmds.delete(sh)
            removed.append(sh)

    try:
        _reset_control_points(node, _get_cv_count(node))
    except Exception:
        pass

    _dirty_shape_view()
    return removed


def cleanup_orphaned_origs() -> list:
    """デフォーマを失った全 retopoGuideNode の Orig を掃除する。

    Maya 標準の DetachSkin は skinCluster を削除しても Orig を残すため、
    デフォーマ削除時のコールバックから本関数を呼んで後始末する。
    """
    if _unbind_in_progress:
        return []
    cleaned = []
    for node in (cmds.ls(type=kPluginNodeName, long=True) or []):
        if not cmds.objExists(node):
            continue
        try:
            if cmds.getAttr(node + ".intermediateObject"):
                continue
            if _has_active_deformer(node):
                continue
            if _cleanup_after_unbind(node):
                cleaned.append(node)
        except Exception:
            pass
    return cleaned
