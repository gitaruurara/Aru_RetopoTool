"""
curve_profile_ui.py — Curve Profile Deformer UI
=================================================
PySide6 / PySide2 QDialog.

Usage (Script Editor)::

    from Aru_RetopoTool.editor.ui import poisson_ui
    poisson_ui.show()
"""

from __future__ import annotations

import os
import traceback

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets

_here = os.path.dirname(os.path.abspath(__file__))
_WIN_NAME = "curveProfileDeformerUI"


# ======================================================================
# Dialog
# ======================================================================

class CurveProfileWindow(QtWidgets.QDialog):
    """Curve Profile デフォーマの作成・再バインド UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(_WIN_NAME)
        self.setWindowTitle("Curve Profile Deformer")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(360)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)

        # ---- RetopoGuide ノード選択 ------------------------------------
        grp_src = QtWidgets.QGroupBox("ソース (RetopoGuide)")
        src_lay = QtWidgets.QHBoxLayout(grp_src)

        src_lay.addWidget(QtWidgets.QLabel("RetopoGuide:"))
        self._cn_combo = QtWidgets.QComboBox()
        self._cn_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        src_lay.addWidget(self._cn_combo)

        btn_refresh_cn = QtWidgets.QPushButton("↻")
        btn_refresh_cn.setFixedWidth(28)
        btn_refresh_cn.setToolTip("RetopoGuide ノードリストを更新")
        btn_refresh_cn.clicked.connect(self._refresh_cn_list)
        src_lay.addWidget(btn_refresh_cn)
        lay.addWidget(grp_src)

        # ---- メッシュ選択 --------------------------------------------
        grp_mesh = QtWidgets.QGroupBox("ターゲットメッシュ")
        mesh_lay = QtWidgets.QHBoxLayout(grp_mesh)

        self._mesh_le = QtWidgets.QLineEdit()
        self._mesh_le.setPlaceholderText("メッシュ名 (空の場合は選択から取得)")
        mesh_lay.addWidget(self._mesh_le)

        btn_sel = QtWidgets.QPushButton("<<")
        btn_sel.setFixedWidth(32)
        btn_sel.setToolTip("選択中のメッシュを取得")
        btn_sel.clicked.connect(self._pick_mesh_from_selection)
        mesh_lay.addWidget(btn_sel)
        lay.addWidget(grp_mesh)

        # ---- バインド (作成) ------------------------------------------
        grp_bind = QtWidgets.QGroupBox("バインド")
        bind_lay = QtWidgets.QVBoxLayout(grp_bind)

        btn_create = QtWidgets.QPushButton("デフォーマを作成")
        btn_create.setToolTip(
            "retopoGuideNode.outNetData → profileCurveDeformer\n"
            "カットメッシュ＋ベジエ直接評価")
        btn_create.setStyleSheet("font-weight: bold;")
        btn_create.clicked.connect(self._on_create)
        bind_lay.addWidget(btn_create)

        lay.addWidget(grp_bind)

        # ---- 既存デフォーマ操作 ----------------------------------------
        grp_deformer = QtWidgets.QGroupBox("既存デフォーマ")
        def_lay = QtWidgets.QGridLayout(grp_deformer)

        def_lay.addWidget(QtWidgets.QLabel("デフォーマ:"), 0, 0)
        self._def_combo = QtWidgets.QComboBox()
        self._def_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        def_lay.addWidget(self._def_combo, 0, 1)

        btn_refresh_def = QtWidgets.QPushButton("↻")
        btn_refresh_def.setFixedWidth(28)
        btn_refresh_def.setToolTip("デフォーマリストを更新")
        btn_refresh_def.clicked.connect(self._refresh_deformer_list)
        def_lay.addWidget(btn_refresh_def, 0, 2)



        btn_select_def = QtWidgets.QPushButton("デフォーマを選択")
        btn_select_def.clicked.connect(self._on_select_deformer)
        def_lay.addWidget(btn_select_def, 2, 0, 1, 3)

        lay.addWidget(grp_deformer)

        # ---- カットメッシュ デバッグ表示 (§4.1) --------------------------
        grp_dbg = QtWidgets.QGroupBox("カットメッシュ デバッグ表示")
        dbg_lay = QtWidgets.QGridLayout(grp_dbg)

        dbg_lay.addWidget(QtWidgets.QLabel("色分け:"), 0, 0)
        self._dbg_mode = QtWidgets.QComboBox()
        self._dbg_mode.addItem("ブロック (変形の到達範囲)", "block")
        self._dbg_mode.addItem("カーブの表裏 (+/-)", "side")
        self._dbg_mode.addItem("カーブ別", "curve")
        self._dbg_mode.addItem("未知数 / 拘束", "constraint")
        self._dbg_mode.setToolTip(
            "ブロック: V^T L_h V の連結成分。カーブネットで囲まれた領域が\n"
            "分離できていれば別々の色になる（論文 §4.2）。")
        dbg_lay.addWidget(self._dbg_mode, 0, 1, 1, 2)

        dbg_lay.addWidget(QtWidgets.QLabel("縮小:"), 1, 0)
        self._dbg_shrink = QtWidgets.QDoubleSpinBox()
        self._dbg_shrink.setRange(0.0, 0.45)
        self._dbg_shrink.setSingleStep(0.02)
        self._dbg_shrink.setValue(0.12)
        self._dbg_shrink.setToolTip(
            "各カットフェイスを重心方向へ縮める割合。\n"
            "大きくするとカット線が隙間として見える。")
        dbg_lay.addWidget(self._dbg_shrink, 1, 1, 1, 2)

        self._dbg_live = QtWidgets.QCheckBox("変形に追従")
        self._dbg_live.setChecked(True)
        self._dbg_live.setToolTip(
            "カットメッシュをデフォーマ出力メッシュの現在の形状に\n"
            "追従させる。カット頂点を元メッシュ頂点のアフィン結合として\n"
            "保持しているので、ポーズを付けたままブロック分離を確認できる。\n"
            "重い場合はオフにするとレスト形状で固定表示になる。")
        dbg_lay.addWidget(self._dbg_live, 2, 0, 1, 3)

        btn_dbg_show = QtWidgets.QPushButton("カットメッシュを表示")
        btn_dbg_show.setToolTip(
            "カットメッシュ専用ロケータ (AruCutMeshLocator) を作って\n"
            "ビューポートに直接描画する。ポリゴンではないので\n"
            "マテリアルの割り当ては不要。")
        btn_dbg_show.clicked.connect(self._on_show_cut_mesh)
        dbg_lay.addWidget(btn_dbg_show, 3, 0, 1, 2)

        btn_dbg_clear = QtWidgets.QPushButton("消去")
        btn_dbg_clear.clicked.connect(self._on_clear_cut_mesh)
        dbg_lay.addWidget(btn_dbg_clear, 3, 2)

        btn_dbg_report = QtWidgets.QPushButton("診断レポート")
        btn_dbg_report.setToolTip(
            "ブロック数・カーブを跨いでいるフェイスなどを出力する。")
        btn_dbg_report.clicked.connect(self._on_report_cut_mesh)
        dbg_lay.addWidget(btn_dbg_report, 4, 0, 1, 2)

        btn_dbg_strad = QtWidgets.QPushButton("短絡箇所をマーク")
        btn_dbg_strad.setToolTip(
            "カーブの + と - の両方に接しているカットフェイスの位置に\n"
            "ロケータを立てる。そこから変形が反対側へ漏れる。")
        btn_dbg_strad.clicked.connect(self._on_select_straddling)
        dbg_lay.addWidget(btn_dbg_strad, 4, 2)

        lay.addWidget(grp_dbg)

        # 既に表示中のロケータへ即座に反映する
        self._dbg_mode.currentIndexChanged.connect(self._apply_cut_mesh_attrs)
        self._dbg_shrink.valueChanged.connect(self._apply_cut_mesh_attrs)
        self._dbg_live.toggled.connect(self._apply_cut_mesh_attrs)

        # ---- 情報 ----------------------------------------------------
        grp_info = QtWidgets.QGroupBox("情報")
        info_lay = QtWidgets.QVBoxLayout(grp_info)
        self._info_label = QtWidgets.QLabel("—")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("font-size: 11px;")
        info_lay.addWidget(self._info_label)
        lay.addWidget(grp_info)

        # ---- コンボ変更 → 情報更新 --------------------------------------
        self._def_combo.currentTextChanged.connect(self._on_deformer_changed)

        # 初期化
        self._refresh_cn_list()
        self._refresh_deformer_list()

    # ------------------------------------------------------------------
    # ヘルパ
    # ------------------------------------------------------------------

    def _refresh_cn_list(self):
        nodes = cmds.ls(type="retopoGuideNode") or []
        self._cn_combo.blockSignals(True)
        prev = self._cn_combo.currentText()
        self._cn_combo.clear()
        self._cn_combo.addItems(nodes)
        idx = self._cn_combo.findText(prev)
        if idx >= 0:
            self._cn_combo.setCurrentIndex(idx)
        self._cn_combo.blockSignals(False)

    def _refresh_deformer_list(self):
        nodes = cmds.ls(type="profileCurveDeformer") or []
        self._def_combo.blockSignals(True)
        prev = self._def_combo.currentText()
        self._def_combo.clear()
        self._def_combo.addItems(nodes)
        idx = self._def_combo.findText(prev)
        if idx >= 0:
            self._def_combo.setCurrentIndex(idx)
        self._def_combo.blockSignals(False)
        self._update_info()

    def _pick_mesh_from_selection(self):
        sel = cmds.ls(selection=True, long=True) or []
        for s in sel:
            shapes = cmds.listRelatives(
                s, shapes=True, type="mesh", fullPath=True) or []
            if shapes:
                self._mesh_le.setText(s.split("|")[-1])
                return
            if cmds.nodeType(s) == "mesh":
                parent = cmds.listRelatives(s, parent=True, fullPath=True)
                self._mesh_le.setText(
                    (parent[0] if parent else s).split("|")[-1])
                return
        if sel:
            self._mesh_le.setText(sel[0].split("|")[-1])

    def _resolve_mesh(self) -> str | None:
        """メッシュ名を返す。空ならretopoGuideNodeのmeshName→選択から取得。"""
        name = self._mesh_le.text().strip()
        if name and cmds.objExists(name):
            return name
        # retopoGuideNode の meshName から取得
        cn_node = self._cn_combo.currentText()
        if cn_node and cmds.objExists(cn_node):
            try:
                mn = cmds.getAttr(f"{cn_node}.meshName") or ""
                if mn and cmds.objExists(mn):
                    return mn
            except Exception:
                pass
        # 選択から取得
        sel = cmds.ls(selection=True, long=True) or []
        for s in sel:
            shapes = cmds.listRelatives(
                s, shapes=True, type="mesh", fullPath=True) or []
            if shapes:
                return s.split("|")[-1]
        return None

    def _on_deformer_changed(self, _):
        self._update_info()

    def _update_info(self):
        node = self._def_combo.currentText()
        if not node or not cmds.objExists(node):
            self._info_label.setText("—")
            return
        try:
            meshes = cmds.deformer(node, query=True, geometry=True) or []
            mesh_str = meshes[0] if meshes else "(未接続)"

            cn_conns = cmds.listConnections(
                f"{node}.retopoGuideData", source=True,
                destination=False) or []
            cn_str = cn_conns[0] if cn_conns else "(未接続)"

            import json as _json
            pbd_str = cmds.getAttr(f"{node}.poissonBindData") or ""
            if not pbd_str:
                self._info_label.setText(
                    f"メッシュ: {mesh_str}\nRetopoGuide: {cn_str}\n"
                    "Poisson バインドデータなし")
                return
            pbd = _json.loads(pbd_str)
            n_verts = pbd.get("n_verts", 0)
            n_v = pbd.get("n_v", 0)
            n_c = pbd.get("n_c", 0)
            n_h = pbd.get("n_h", 0)
            n_cut_faces = len(pbd.get("face_loops", []))
            self._info_label.setText(
                f"メッシュ: {mesh_str}\n"
                f"RetopoGuide: {cn_str}\n"
                f"メッシュ頂点: {n_verts}\n"
                f"Unknowns: {n_v} / Constraints: {n_c}\n"
                f"カットフェイス: {n_cut_faces} / HE: {n_h}")
        except Exception:
            self._info_label.setText("情報取得エラー")

    # ------------------------------------------------------------------
    # アクション
    # ------------------------------------------------------------------

    def _on_create(self):
        cn_node = self._cn_combo.currentText()
        if not cn_node:
            QtWidgets.QMessageBox.warning(
                self, "警告", "RetopoGuide ノードを選択してください。")
            return

        mesh = self._resolve_mesh()
        if not mesh:
            QtWidgets.QMessageBox.warning(
                self, "警告",
                "ターゲットメッシュが見つかりません。\n"
                "メッシュ名を入力するか、メッシュを選択してください。")
            return

        # numpy/scipy が利用可能か事前チェック
        try:
            import numpy  # noqa: F401
            import scipy  # noqa: F401
        except ImportError as _imp_err:
            QtWidgets.QMessageBox.critical(
                self, "依存パッケージ不足",
                f"Poisson ソルバーには numpy と scipy が必要です。\n\n{_imp_err}")
            return

        try:
            # profileCurveDeformer プラグインをロード (C++ ビルドがあればそれを使う)
            from Aru_RetopoTool.editor import launch as _launch
            _plugin_path = _launch._deformer_plugin_path()
            try:
                if not cmds.pluginInfo(
                        "curve_profile_deformer", query=True, loaded=True):
                    cmds.loadPlugin(_plugin_path)
            except Exception:
                cmds.loadPlugin(_plugin_path)

            from Aru_RetopoTool.editor.deformer.curve_profile_rig import ProfileCurveRig
            deformer = ProfileCurveRig().create_from_curvenet(
                mesh_name=mesh,
                cn_node_name=cn_node,
            )
            self._refresh_deformer_list()
            idx = self._def_combo.findText(deformer)
            if idx >= 0:
                self._def_combo.setCurrentIndex(idx)
            QtWidgets.QMessageBox.information(
                self, "完了",
                f"デフォーマ '{deformer}' を作成しました。\n"
                f"接続: {cn_node}.outNetData → {deformer}.retopoGuideData")
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "エラー",
                f"{e}\n\n{traceback.format_exc()}")

    def _on_select_deformer(self):
        deformer = self._def_combo.currentText()
        if deformer and cmds.objExists(deformer):
            cmds.select(deformer, replace=True)

    # ------------------------------------------------------------------
    # カットメッシュ デバッグ表示
    # ------------------------------------------------------------------

    def _current_deformer(self):
        """コンボで選択中のデフォーマ名を返す。無ければ警告して None。"""
        deformer = self._def_combo.currentText()
        if not deformer or not cmds.objExists(deformer):
            QtWidgets.QMessageBox.warning(
                self, "Curve Profile", "デフォーマを選択してください。")
            return None
        return deformer

    def _on_show_cut_mesh(self):
        deformer = self._current_deformer()
        if not deformer:
            return
        from Aru_RetopoTool.editor.deformer import cut_mesh_debug
        try:
            cut_mesh_debug.show(
                deformer,
                mode=self._dbg_mode.currentData(),
                shrink=self._dbg_shrink.value(),
                live=self._dbg_live.isChecked())
        except Exception as exc:
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self, "Curve Profile",
                "カットメッシュの表示に失敗しました:\n%s" % exc)

    def _on_clear_cut_mesh(self):
        from Aru_RetopoTool.editor.deformer import cut_mesh_debug
        cut_mesh_debug.clear()

    def _apply_cut_mesh_attrs(self, *_args):
        """表示中のカットメッシュロケータへ色分け・縮小率を反映する。"""
        from Aru_RetopoTool.editor.curvenet import cut_mesh_locator
        from Aru_RetopoTool.editor.deformer import cut_mesh_debug

        shapes = cmds.ls(type=cut_mesh_locator.CutMeshLocator.kNodeName) or []
        for shp in shapes:
            cmds.setAttr("%s.mode" % shp,
                         cut_mesh_debug.MODES.index(
                             self._dbg_mode.currentData()))
            cmds.setAttr("%s.shrink" % shp, self._dbg_shrink.value())
            if cmds.attributeQuery("live", node=shp, exists=True):
                cmds.setAttr("%s.live" % shp, self._dbg_live.isChecked())
        if shapes:
            cmds.refresh()

    def _on_report_cut_mesh(self):
        deformer = self._current_deformer()
        if not deformer:
            return
        from Aru_RetopoTool.editor.deformer import cut_mesh_debug
        try:
            text = cut_mesh_debug.report(deformer)
        except Exception as exc:
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self, "Curve Profile", "レポートに失敗しました:\n%s" % exc)
            return
        print(text)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("カットメッシュ 診断レポート")
        dlg.setMinimumSize(560, 360)
        dlg_lay = QtWidgets.QVBoxLayout(dlg)
        edit = QtWidgets.QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-family: Consolas, monospace;")
        dlg_lay.addWidget(edit)
        dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()

    def _on_select_straddling(self):
        deformer = self._current_deformer()
        if not deformer:
            return
        from Aru_RetopoTool.editor.deformer import cut_mesh_debug
        try:
            cut_mesh_debug.select_straddling_faces(deformer)
        except Exception as exc:
            traceback.print_exc()
            QtWidgets.QMessageBox.warning(
                self, "Curve Profile", "%s" % exc)


# ======================================================================
# 起動ヘルパ
# ======================================================================

def show():
    """
    UI を表示（既に開いていれば前面に出す）。

    Maya Script Editor から::

        from Aru_RetopoTool.editor.ui import poisson_ui
        poisson_ui.show()
    """
    # プラグインを自動ロード
    for plugin_name, plugin_subdir in [
        ("aru_retopo_guide_plugin.py", "curvenet"),
        ("curve_profile_deformer.py", "deformer"),
    ]:
        plugin_path = os.path.join(os.path.dirname(_here), plugin_subdir, plugin_name)
        try:
            if not cmds.pluginInfo(plugin_path, query=True, loaded=True):
                cmds.loadPlugin(plugin_path)
        except Exception:
            try:
                cmds.loadPlugin(plugin_path)
            except Exception:
                pass

    from Aru_RetopoTool.editor.ui import qt_window
    w = qt_window.find_window(_WIN_NAME)
    if w is not None:
        qt_window.show_tool_window(w)
        return w

    win = CurveProfileWindow(qt_window.maya_main_window())
    qt_window.show_tool_window(win)
    return win
