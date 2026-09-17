"""
RetopoGuide UI  -  Maya QWidget パネル
=====================================
Script Editor に貼るだけで起動できる軽量 UI。

使い方
------
    from Aru_RetopoTool.editor.ui import curve_net_ui
    curve_net_ui.show()
"""

from __future__ import annotations
import sys, os, json

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.ui import qt_window

_WIN_NAME = "RetopoGuideWindow"


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------

class RetopoGuideWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RetopoGuide Editor")
        self.setObjectName(_WIN_NAME)
        self.setMinimumWidth(320)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._build_ui()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(4)

        # ---- ノード選択 ----
        node_row = QtWidgets.QHBoxLayout()
        node_row.addWidget(QtWidgets.QLabel("Node:"))
        self._node_combo = QtWidgets.QComboBox()
        self._node_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        node_row.addWidget(self._node_combo)
        refresh_btn = QtWidgets.QPushButton("↺")
        refresh_btn.setFixedWidth(28)
        refresh_btn.setToolTip("ノード一覧を更新")
        refresh_btn.clicked.connect(self._refresh_node_list)
        node_row.addWidget(refresh_btn)
        lay.addLayout(node_row)

        # ---- アクション ----
        grp_new = QtWidgets.QGroupBox("作成")
        grp_new_lay = QtWidgets.QVBoxLayout(grp_new)

        self._mesh_le = QtWidgets.QLineEdit()
        self._mesh_le.setPlaceholderText("メッシュ名 (空=選択から自動)")
        grp_new_lay.addWidget(self._mesh_le)

        btn_create = QtWidgets.QPushButton("新規 RetopoGuide を作成")
        btn_create.setToolTip("選択したメッシュに retopoGuideNode を作成して編集コンテキストへ切り替える")
        btn_create.clicked.connect(self._on_create)
        grp_new_lay.addWidget(btn_create)
        lay.addWidget(grp_new)

        # ---- 編集 ----
        grp_edit = QtWidgets.QGroupBox("編集")
        grp_edit_lay = QtWidgets.QGridLayout(grp_edit)

        btn_ctx = QtWidgets.QPushButton("編集コンテキストへ")
        btn_ctx.clicked.connect(self._on_enter_ctx)
        grp_edit_lay.addWidget(btn_ctx, 0, 0, 1, 2)

        self._chk_xray = QtWidgets.QCheckBox("X 線表示 (メッシュより前に描画)")
        self._chk_xray.setToolTip(
            "ジョイントの X 線表示と同じく、カーブ・ポイント・ハンドルを\n"
            "メッシュに埋もれさせず常に手前に描きます")
        self._chk_xray.toggled.connect(self._on_xray_toggled)
        grp_edit_lay.addWidget(self._chk_xray, 1, 0, 1, 2)

        from Aru_RetopoTool.editor.curvenet import curve_net_rebind as _rebind
        self._chk_rebind = QtWidgets.QCheckBox("デフォーマを自動リバインド")
        self._chk_rebind.setToolTip(
            "カーブネット (レスト形状) を編集するたびに、繋がっている\n"
            "profileCurveDeformer のバインドデータをたの場で作り直します。\n"
            "デフォーマ・接続・スキンクラスタはそのまま残ります (ドラッグ中はリリース時に 1 回)。")
        self._chk_rebind.setChecked(_rebind.is_enabled())
        self._chk_rebind.toggled.connect(lambda s: _rebind.set_enabled(bool(s)))
        grp_edit_lay.addWidget(self._chk_rebind, 2, 0)

        btn_rebind = QtWidgets.QPushButton("今リバインド")
        btn_rebind.setToolTip("このカーブネットに繋がるデフォーマを今すぐリバインドします")
        btn_rebind.clicked.connect(self._on_rebind_now)
        grp_edit_lay.addWidget(btn_rebind, 2, 1)


        hint = QtWidgets.QLabel(
            "LMB: EP選択 / EP追加 / スプライン接続　同 EP再クリック: 選択解除\n"
            "Ctrl+LMB: スプライン上に EP 挿入\n"
            "Shift+LMB クリック (選択中 EP あり): マージ\n"
            "Shift+LMB ドラッグ: 表面に沿ってリラックス\n"
            "MMBドラッグ: EP移動 / ハンドル移動 (オレンジ=手動固定)"
        )
        hint.setStyleSheet("color: gray; font-size: 10px;")
        grp_edit_lay.addWidget(hint, 3, 0, 1, 2)

        lay.addWidget(grp_edit)

        # ---- ツール ----
        grp_tools = QtWidgets.QGroupBox("ツール")
        tools_lay = QtWidgets.QVBoxLayout(grp_tools)

        btn_fit = QtWidgets.QPushButton("スプラインをメッシュにフィット")
        btn_fit.setToolTip(
            "全スプラインのカーブをメッシュ表面に沿わせるように\n"
            "EP とハンドルを最適化します")
        btn_fit.clicked.connect(self._on_fit_to_mesh)
        tools_lay.addWidget(btn_fit)

        fit_param_lay = QtWidgets.QHBoxLayout()
        fit_param_lay.addWidget(QtWidgets.QLabel("反復:"))
        self._spin_fit_iter = QtWidgets.QSpinBox()
        self._spin_fit_iter.setRange(1, 20)
        self._spin_fit_iter.setValue(3)
        fit_param_lay.addWidget(self._spin_fit_iter)
        fit_param_lay.addWidget(QtWidgets.QLabel("強さ:"))
        self._spin_fit_weight = QtWidgets.QDoubleSpinBox()
        self._spin_fit_weight.setRange(0.1, 1.0)
        self._spin_fit_weight.setSingleStep(0.1)
        self._spin_fit_weight.setValue(0.5)
        fit_param_lay.addWidget(self._spin_fit_weight)
        fit_param_lay.addStretch()
        tools_lay.addLayout(fit_param_lay)

        lay.addWidget(grp_tools)

        # ---- 情報 ----
        grp_info = QtWidgets.QGroupBox("情報")
        info_lay = QtWidgets.QVBoxLayout(grp_info)
        self._info_label = QtWidgets.QLabel("CVs: 0 / Splines: 0 / Curves: 0")
        self._info_label.setWordWrap(True)
        info_lay.addWidget(self._info_label)
        lay.addWidget(grp_info)

        # ---- ノードコンボの変更で情報更新 ----
        self._node_combo.currentTextChanged.connect(self._on_node_changed)

        # 初期化
        self._refresh_node_list()

    # ------------------------------------------------------------------

    def _current_node(self) -> str:
        return self._node_combo.currentText()

    def _refresh_node_list(self):
        nodes = cmds.ls(type="retopoGuideNode") or []
        self._node_combo.blockSignals(True)
        prev = self._node_combo.currentText()
        self._node_combo.clear()
        self._node_combo.addItems(nodes)
        idx = self._node_combo.findText(prev)
        if idx >= 0:
            self._node_combo.setCurrentIndex(idx)
        self._node_combo.blockSignals(False)
        self._update_info()
        self._sync_xray()

    def _on_node_changed(self, _):
        node = self._current_node()
        if node:
            cmds.optionVar(sv=("retopoGuideContext_node", node))
        self._update_info()
        self._sync_xray()

    def _sync_xray(self):
        node = self._current_node()
        chk = getattr(self, "_chk_xray", None)
        if chk is None:
            return
        on = True
        if node and cmds.objExists(node + ".xray"):
            on = bool(cmds.getAttr(node + ".xray"))
        chk.blockSignals(True)
        chk.setChecked(on)
        chk.blockSignals(False)

    def _on_xray_toggled(self, state):
        node = self._current_node()
        if node and cmds.objExists(node + ".xray"):
            cmds.setAttr(node + ".xray", bool(state))

    def _on_rebind_now(self):
        node = self._current_node()
        if not node:
            return
        from Aru_RetopoTool.editor.curvenet import curve_net_rebind
        curve_net_rebind.rebind_now(node)

    def _update_info(self):
        node = self._current_node()
        if not node or not cmds.objExists(node):
            self._info_label.setText("CVs: - / Splines: - / Curves: -")
            return
        raw = cmds.getAttr("{}.netData".format(node)) or ""
        if not raw:
            self._info_label.setText("CVs: 0 / Splines: 0 / Curves: 0")
            return
        cn = RetopoGuideData.from_json(raw)
        mesh = cmds.getAttr("{}.meshName".format(node)) or "(none)"
        self._info_label.setText(
            "Mesh: {}\nCVs: {} / Splines: {} / Curves: {}".format(
                mesh, len(cn.positions), len(cn.splines), len(cn.curves)
            )
        )

    def _on_create(self):
        mesh = self._mesh_le.text().strip()
        if mesh:
            cmds.select(mesh, replace=True)
        try:
            cmds.loadPlugin(
                os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             os.pardir, "curvenet", "aru_retopo_guide_plugin.py"), quiet=True)
        except Exception:
            pass
        try:
            result = cmds.retopoGuideCreate()
            node = result[0] if isinstance(result, (list, tuple)) else str(result)
            self._refresh_node_list()
            idx = self._node_combo.findText(node)
            if idx >= 0:
                self._node_combo.setCurrentIndex(idx)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "エラー", str(e))

    def _on_enter_ctx(self):
        node = self._current_node()
        if node:
            cmds.optionVar(sv=("retopoGuideContext_node", node))
        try:
            from Aru_RetopoTool.editor.curvenet.aru_retopo_guide_plugin import _ctx, _DRAGGER_CTX
            from Aru_RetopoTool.editor.curvenet.curve_net_menu import _get_or_create_dragger_ctx
            _ctx.sel_ep = None
            _ctx.drag_ep = None
            # initialize/finalize を必ず登録するため既存コンテキストを削除
            try:
                if cmds.contextInfo(_DRAGGER_CTX, exists=True):
                    cmds.deleteUI(_DRAGGER_CTX)
            except Exception:
                pass
            ctx = _get_or_create_dragger_ctx()
        except Exception:
            ctx = "retopoGuideDraggerCtx1"
        cmds.setToolTo(ctx)

    def _on_fit_to_mesh(self):
        node = self._current_node()
        if not node:
            QtWidgets.QMessageBox.warning(self, "エラー",
                                          "RetopoGuide ノードを選択してください。")
            return
        try:
            from Aru_RetopoTool.editor.curvenet.curve_net_edit import (
                fit_splines_to_mesh)
            n_iter = self._spin_fit_iter.value()
            weight = self._spin_fit_weight.value()
            cmds.undoInfo(openChunk=True,
                          chunkName="FitSplinesToMesh")
            try:
                result = fit_splines_to_mesh(
                    node, n_iterations=n_iter,
                    handle_weight=weight)
            finally:
                cmds.undoInfo(closeChunk=True)
            if result:
                self._update_info()
                QtWidgets.QMessageBox.information(
                    self, "完了",
                    "スプラインをメッシュにフィットしました。")
            else:
                QtWidgets.QMessageBox.warning(
                    self, "警告",
                    "フィットに失敗しました。メッシュが設定されているか確認してください。")
        except Exception as e:
            import traceback
            QtWidgets.QMessageBox.critical(
                self, "エラー",
                f"{e}\n\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
# 起動ヘルパ
# ---------------------------------------------------------------------------

def show():
    """
    UI を表示（既に開いていれば前面に出す）。
    Maya Script Editor から呼ぶ:

        from Aru_RetopoTool.editor.ui import curve_net_ui
        curve_net_ui.show()
    """
    # プラグインを自動ロード (未ロード時のみ)
    _plugin_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "curvenet", "aru_retopo_guide_plugin.py")
    try:
        if not cmds.pluginInfo(_plugin_file, query=True, loaded=True):
            cmds.loadPlugin(_plugin_file)
    except Exception:
        try:
            cmds.loadPlugin(_plugin_file)
        except Exception:
            pass

    # 既存ウィンドウがあれば前面に出す
    w = qt_window.find_window(_WIN_NAME)
    if w is not None:
        qt_window.show_tool_window(w)
        return w

    win = RetopoGuideWindow(qt_window.maya_main_window())
    qt_window.show_tool_window(win)
    return win
