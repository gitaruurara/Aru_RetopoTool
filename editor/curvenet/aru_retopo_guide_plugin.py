"""
RetopoGuide Plugin  -  Maya Python Plugin
=======================================
Pixar SIGGRAPH 2022 §3 に基づく cubic Bézier カーブネット 編集プラグイン。

プラグインノード: retopoGuideNode
  - JSON 形式でカーブネットデータを保持する depNode。
  - Maya のアトリビュートとして保存されるのでシーン保存で永続化される。

コンテキスト: RetopoGuideContext (retopoGuideContext)
  - ポリゴン頂点や面上にクリックして交点・アンカーを挿入する。
  - 2 点をクリックして spline を追加する。

コマンド群:
  retopoGuideCreate   : 新規 retopoGuideNode を作成し選択メッシュに関連付ける
  retopoGuideAddPoint : 現在コンテキストの最終クリック点を交点として追加
  retopoGuideRebuild  : classify_endpoints() / ビジュアル更新を強制

使い方 (Script Editor)
-----------------------

    # カーブネットを作成 (ポリゴン選択してから)
    cmds.retopoGuideCreate()

    # 編集コンテキストへ切り替え
    cmds.setToolTo("retopoGuideContext1")

モジュール構成
--------------
- aru_retopo_guide_plugin.py    : 定数 / 共有状態 / プラグイン登録 (本ファイル)
- curve_net_node.py      : RetopoGuideNode (MPxSurfaceShape) + ShapeUI + GeomIterator
- curve_net_skin.py      : RetopoGuideSkinCluster (MPxSkinCluster)
- curve_net_draw.py      : RetopoGuideGeometryOverride + ComponentConverter
- curve_net_edit.py      : RetopoGuideAccessor / メッシュユーティリティ / RMBメニュー / scriptJob
- curve_net_context.py   : ドラッガーコンテキスト / スプライン操作
- curve_net_commands.py  : MPxCommand 群 (Create / AddPoint / Rebuild)
- curve_net_data.py      : RetopoGuideData (データモデル)
"""

from __future__ import annotations

import sys
import os
import traceback
import logging

_log = logging.getLogger("RetopoGuide")
_log.setLevel(logging.DEBUG)
if not _log.handlers:
    _fmt = logging.Formatter("[RetopoGuide] %(asctime)s %(levelname)s %(message)s",
                             datefmt="%H:%M:%S")
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(_fmt)
    _log.addHandler(_sh)
    try:
        _log_dir = os.path.join(os.path.expanduser("~"), "RetopoGuide_logs")
        os.makedirs(_log_dir, exist_ok=True)
        _fh = logging.FileHandler(
            os.path.join(_log_dir, "curve_net.log"), mode="w", encoding="utf-8")
        _fh.setFormatter(_fmt)
        _log.addHandler(_fh)
    except Exception:
        pass

import maya.OpenMaya as om1
import maya.OpenMayaMPx as ompx
import maya.api.OpenMayaRender as omr
import maya.cmds as cmds

# サブモジュールパスを確保
try:
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
except NameError:
    pass


# ===========================================================================
# 定数
# ===========================================================================

kPluginNodeName       = "retopoGuideNode"
kPluginNodeId         = om1.MTypeId(0x00131AD2)
kDrawDbClassification = "drawdb/geometry/retopoGuideNode"
kDrawRegistrantId     = "retopoGuideNodePlugin"
kCmdCreate            = "retopoGuideCreate"
kCmdAddPoint          = "retopoGuideAddPoint"
kCmdRebuild           = "retopoGuideRebuild"
kCmdUnbind            = "retopoGuideUnbind"

# (EP/Handle ロケーターノードはコンポーネント化で廃止)
kEPNodeName       = "retopoGuideEPShape"       # 後方互換用
kHandleNodeName   = "retopoGuideHandleShape"   # 後方互換用

# draggerContext 名
_DRAGGER_CTX       = "retopoGuideDraggerCtx1"
_LOC_GRP_SUFFIX    = "_loc"   # 旧ロケーターグループ互換


# ===========================================================================
# 共有状態 (モジュールレベル)
# ===========================================================================

class RetopoGuideState:
    """RetopoGuide 編集コンテキストの共有ミュータブル状態。

    旧 ``_ctx_state`` dict の代替。属性アクセスにより
    タイプセーフかつ IDE 補完が効く。
    """

    __slots__ = (
        "sel_ep", "drag_ep", "drag_handle", "drag_handle_anchor",
        "drag_mirror_handle",
        "preview_end", "merge_target",
        "ring_cut", "ring_preview", "ring_line",
        "press_screen", "drag_screen", "hover_spline",
        "drag_mirror_ep", "drag_side",
        "_sj_id", "_sel_sj", "_is_scene_clearing", "_component_mode",
        "_orig_cleanup_pending",
    )

    def __init__(self):
        self.reset()

    def reset(self):
        """全フィールドを初期値に戻す。"""
        self.sel_ep: int | None = None
        self.drag_ep: int | None = None
        self.drag_handle: int | None = None
        self.drag_handle_anchor: list | None = None
        self.drag_mirror_handle: int | None = None
        self.preview_end: list | None = None
        self.merge_target: int | None = None
        self.ring_cut: dict | None = None
        self.ring_preview: list | None = None
        self.ring_line: tuple | None = None
        # 押下位置 / 直近のドラッグ位置 (スクリーン座標)。カーブがメッシュに
        # 埋まっていても掴めるよう、接続先の判定をスクリーン空間で行う。
        # press_screen との差分で「クリックだけ」か「ドラッグ」かを判定する。
        self.press_screen: tuple | None = None
        self.drag_screen: tuple | None = None
        # ドラッグ中にスクリーン空間で狙っているカーブ (sp_idx, t, world_pt)
        self.hover_spline: tuple | None = None
        # 対称ドラッグ用: drag_ep の反対側 EP と、ドラッグ開始時にいた側の符号。
        # 対称面を跨がせないためにドラッグ開始時の側を憶えておく。
        self.drag_mirror_ep: int | None = None
        self.drag_side: float | None = None
        self._sj_id = None
        self._sel_sj: list | None = None
        self._is_scene_clearing: bool = False
        self._component_mode: str | None = None
        self._orig_cleanup_pending: bool = False


    def remap_cv_indices(self, remap) -> None:
        """CV の再採番に合わせてキャッシュしている CV インデックスを張り替える。

        孤立 CV の掃除で positions が詰められると、保持している
        ``sel_ep`` などが別の CV を指してしまうため。削除された CV を
        指していた場合は None に落とす。

        Parameters
        ----------
        remap : dict[int, int] | None
            旧→新インデックス写像。None なら何もしない。
        """
        if not remap:
            return
        for name in ("sel_ep", "drag_ep", "merge_target", "drag_mirror_ep"):
            old = getattr(self, name, None)
            if old is not None:
                setattr(self, name, remap.get(old))

    def __getattr__(self, name):
        """未設定のスロットへのアクセスを None として扱う。

        リロード時に古いインスタンスが残っていても、新しく追加した
        フィールドの参照で AttributeError を出さないための保険。
        """
        if name in self.__slots__:
            return None
        raise AttributeError(name)


_ctx = RetopoGuideState()

_nd_sj_map: dict = {}
_orphaned_loc_groups: list = []
_scene_cb_ids: list = []


# ===========================================================================
# サブモジュール遅延インポート
# ===========================================================================
# render / edit はこのモジュールの定数・状態を import するため、
# ここではトップレベルで import しない（循環参照回避）。
# initializePlugin() 内で明示的にインポートする。

_node = None  # curve_net_node モジュール参照
_skin = None  # curve_net_skin モジュール参照
_draw = None  # curve_net_draw モジュール参照
_edit = None  # curve_net_edit モジュール参照
_menu = None  # curve_net_menu モジュール参照
_cmds = None  # curve_net_commands モジュール参照
_cutloc = None  # cut_mesh_locator モジュール参照


def _ensure_submodules():
    """サブモジュールをロード (初回のみ)。"""
    global _node, _skin, _draw, _edit, _menu, _cmds, _cutloc
    if _node is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_node as _n
        _node = _n
    if _skin is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_skin as _s
        _skin = _s
    if _draw is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_draw as _d
        _draw = _d
    if _edit is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_edit as _e
        _edit = _e
    if _menu is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_menu as _m
        _menu = _m
    if _cmds is None:
        from Aru_RetopoTool.editor.curvenet import curve_net_commands as _c
        _cmds = _c
    if _cutloc is None:
        from Aru_RetopoTool.editor.curvenet import cut_mesh_locator as _cl
        _cutloc = _cl


# ===========================================================================
# シーンクリア時の DrawOverride 保護
# ===========================================================================

def _before_scene_clear(*args, **kwargs):
    _log.info(">>> _before_scene_clear")
    _ctx._is_scene_clearing = True
    _ensure_submodules()
    try:
        import __main__
        if hasattr(__main__, '__retopoGuideCtx__') and __main__.__retopoGuideCtx__:
            __main__.__retopoGuideCtx__.stop_scriptjob()
    except Exception:
        pass
    _nd_sj_map.clear()
    _orphaned_loc_groups.clear()
    _log.info("<<< _before_scene_clear done")


def _after_scene_clear(*args, **kwargs):
    _log.info(">>> _after_scene_clear")
    _ctx._is_scene_clearing = False
    _ensure_submodules()
    try:
        import __main__
        if hasattr(__main__, '__retopoGuideCtx__') and __main__.__retopoGuideCtx__:
            __main__.__retopoGuideCtx__.start_scriptjob()
    except Exception:
        pass
    _log.info("<<< _after_scene_clear done")


def _deferred_orig_cleanup():
    """デフォーマ削除後に走る後始末 (evalDeferred から呼ばれる)。"""
    _ctx._orig_cleanup_pending = False
    if _ctx._is_scene_clearing:
        return
    _ensure_submodules()
    try:
        cleaned = _cmds.cleanup_orphaned_origs()
        if cleaned:
            _log.info("cleaned orphaned Orig for: %s", cleaned)
    except Exception as exc:
        _log.debug("orig cleanup skipped: %s", exc)


def _on_deformer_removed(node_obj, client_data=None):
    """geometryFilter 削除時に Orig の後始末を予約する。

    Maya 標準の DetachSkin は skinCluster を消しても retopoGuideNode の
    Orig を残し inSurface を繋いだままにする。削除の最中にグラフを
    触るのは危険なため evalDeferred で遅延実行する。
    """
    if _ctx._is_scene_clearing or getattr(_ctx, "_orig_cleanup_pending", False):
        return
    try:
        import maya.cmds as _c
        _ctx._orig_cleanup_pending = True
        _c.evalDeferred(_deferred_orig_cleanup, low=True)
    except Exception:
        _ctx._orig_cleanup_pending = False


# ===========================================================================
# プラグイン登録
# ===========================================================================

def initializePlugin(plugin_obj):
    _ensure_submodules()

    try:
        _menu._register_in_main()
    except Exception:
        pass

    mplugin = ompx.MFnPlugin(plugin_obj, "RetopoGuide", "1.0", "Any")

    # --- メインノード (MPxSurfaceShape + ShapeUI) ---
    try:
        mplugin.registerShape(
            _node.RetopoGuideNode.kNodeName,
            _node.RetopoGuideNode.kNodeId,
            _node.RetopoGuideNode.creator,
            _node.RetopoGuideNode.initialize,
            _node.RetopoGuideShapeUI.creator,
            kDrawDbClassification,
        )
    except Exception:
        traceback.print_exc(); raise
    try:
        omr.MDrawRegistry.registerGeometryOverrideCreator(
            kDrawDbClassification,
            kDrawRegistrantId,
            _draw.RetopoGuideGeometryOverride.creator,
        )
    except Exception:
        traceback.print_exc(); raise
    try:
        omr.MDrawRegistry.registerComponentConverter(
            _draw._VERTEX_SEL_ITEM,
            _draw.RetopoGuideComponentConverter.creator,
        )
    except Exception:
        traceback.print_exc(); raise

    # --- コマンド ---
    for cls in (_cmds.CmdRetopoGuideCreate,
                _cmds.CmdRetopoGuideAddPoint,
                _cmds.CmdRetopoGuideRebuild):
        try:
            mplugin.registerCommand(cls.kName, cls.creator, cls.newSyntax)
        except Exception:
            traceback.print_exc(); raise

    # --- scriptJob ---
    try:
        import __main__
        if hasattr(__main__, '__retopoGuideCtx__') and __main__.__retopoGuideCtx__:
            __main__.__retopoGuideCtx__.start_scriptjob()
    except Exception:
        pass

    # --- マーキングメニュー MEL proc 登録 ---
    try:
        _menu._install_dag_menu()
    except Exception:
        pass

    # --- Shift + 右クリックのマーキングメニュー ---
    # 対象の popupMenu はプラグイン読み込み時点でまだ無いことがあるので、
    # UI の準備が済んでから差し込む。
    try:
        cmds.evalDeferred(_menu.install_shift_menu, lowestPriority=True)
    except Exception:
        pass

    # --- Attribute Editor テンプレート ---
    if not cmds.about(batch=True):
        try:
            from Aru_RetopoTool.editor.curvenet import curve_net_ae
            curve_net_ae.install()
        except Exception as _exc:
            _log.warning("AE template install failed: %s", _exc)

    # --- MSceneMessage コールバック ---
    for _msg in (om1.MSceneMessage.kBeforeNew,
                 om1.MSceneMessage.kBeforeOpen,
                 om1.MSceneMessage.kMayaExiting):
        _scene_cb_ids.append(
            om1.MSceneMessage.addCallback(_msg, _before_scene_clear))
    for _msg in (om1.MSceneMessage.kAfterNew,
                 om1.MSceneMessage.kAfterOpen):
        _scene_cb_ids.append(
            om1.MSceneMessage.addCallback(_msg, _after_scene_clear))

    om1.MGlobal.displayInfo("[RetopoGuide] Plugin loaded.")


def uninitializePlugin(plugin_obj):
    _ensure_submodules()
    try:
        import __main__
        if hasattr(__main__, '__retopoGuideCtx__') and __main__.__retopoGuideCtx__:
            __main__.__retopoGuideCtx__.stop_scriptjob()
    except Exception:
        pass

    # Shift + 右クリックを Maya 標準へ戻す
    try:
        _menu.uninstall_shift_menu()
    except Exception:
        pass

    # シーンコールバック除去
    for cb_id in _scene_cb_ids:
        try:
            om1.MMessage.removeCallback(cb_id)
        except Exception:
            pass
    _scene_cb_ids.clear()

    # --- シーン上の全 RetopoGuide ノードを事前削除 ---
    _log.info(">>> uninitializePlugin: deleting scene nodes")
    for ntype in (kPluginNodeName,):
        try:
            nodes = cmds.ls(type=ntype, long=True)
            if nodes:
                cmds.delete(nodes)
        except Exception:
            pass
    for grp in list(_orphaned_loc_groups):
        try:
            if cmds.objExists(grp):
                cmds.delete(grp)
        except Exception:
            pass
    _orphaned_loc_groups.clear()

    try:
        cmds.refresh()
    except Exception:
        pass

    # --- 登録解除 ---
    _log.info(">>> uninitializePlugin: deregistering")
    mplugin = ompx.MFnPlugin(plugin_obj)
    for cls in (_cmds.CmdRetopoGuideCreate,
                _cmds.CmdRetopoGuideAddPoint,
                _cmds.CmdRetopoGuideRebuild):
        try:
            mplugin.deregisterCommand(cls.kName)
        except Exception:
            pass
    try:
        omr.MDrawRegistry.deregisterComponentConverter(
            _draw._VERTEX_SEL_ITEM)
    except Exception:
        pass
    try:
        omr.MDrawRegistry.deregisterGeometryOverrideCreator(
            kDrawDbClassification, kDrawRegistrantId)
    except Exception:
        pass
    try:
        mplugin.deregisterNode(_node.RetopoGuideNode.kNodeId)
    except Exception:
        pass

    _log.info("<<< uninitializePlugin done")
    om1.MGlobal.displayInfo("[RetopoGuide] Plugin unloaded.")
