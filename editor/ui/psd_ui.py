"""
psd_ui.py — RetopoGuide ポーズ補正 (PSD) エディタ
================================================
カーブネットの blendShape ターゲットを poseInterpolator でポーズ駆動にする。

ワークフロー:
  1. ジョイントでポーズを取る
  2. コンポーネントモードでカーブネットの CV を移動ツールで整える (controlPoints)
  3. 「現在のポーズ + スカルプトを追加」
     → ポーズが poseInterpolator に登録され、スカルプトがレスト空間の
       blendShape ターゲットになり、ポーズの重みで駆動される
  4. 同じポーズで直したいときは「選択ポーズに焼き込む」

Usage (Script Editor)::

    from Aru_RetopoTool.editor.ui import psd_ui
    psd_ui.show()
"""

from __future__ import annotations

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from ..curvenet import curve_net_edit as cne
from ..curvenet import blend_target as bt
from ..curvenet import pose_space as ps

_WIN_NAME = "retopoGuidePsdUI"
_TYPE_LABELS = [("swingandtwist", "スイング+ツイスト"), ("swing", "スイング"), ("twist", "ツイスト")]


class RetopoGuidePsdWindow(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(_WIN_NAME)
        self.setWindowTitle("RetopoGuide ポーズ補正 (PSD)")
        self.resize(560, 520)
        self._shape = ""
        self._bs = None
        self._pi = ""
        self._sel_job = None
        self._build_ui()
        self._install_script_job()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._update_weights)
        self._timer.start()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QHBoxLayout()
        self._lbl_node = QtWidgets.QLabel("-")
        top.addWidget(self._lbl_node, 1)
        btn_ref = QtWidgets.QPushButton("更新")
        btn_ref.clicked.connect(self.refresh)
        top.addWidget(btn_ref)
        lay.addLayout(top)

        # ---- ドライバ -----------------------------------------------------
        grp = QtWidgets.QGroupBox("ドライバ")
        g = QtWidgets.QGridLayout(grp)
        g.addWidget(QtWidgets.QLabel("ジョイント:"), 0, 0)
        self._le_joint = QtWidgets.QLineEdit()
        self._le_joint.setPlaceholderText("補正を駆動するジョイント")
        self._le_joint.editingFinished.connect(self._on_joint_changed)
        g.addWidget(self._le_joint, 0, 1)
        btn_pick = QtWidgets.QPushButton("<<")
        btn_pick.setFixedWidth(32)
        btn_pick.setToolTip("選択中のジョイントを取り込む")
        btn_pick.clicked.connect(self._pick_joint)
        g.addWidget(btn_pick, 0, 2)

        g.addWidget(QtWidgets.QLabel("poseInterpolator:"), 1, 0)
        self._cmb_pi = QtWidgets.QComboBox()
        self._cmb_pi.currentIndexChanged.connect(lambda _i: self._on_pi_changed())
        g.addWidget(self._cmb_pi, 1, 1)
        btn_new_pi = QtWidgets.QPushButton("新規")
        btn_new_pi.setToolTip(
            "このジョイントをドライバにした poseInterpolator を作る。\n"
            "ニュートラルポーズ (rotate=0) も一緒に登録する。")
        btn_new_pi.clicked.connect(self._on_new_pi)
        g.addWidget(btn_new_pi, 1, 2)

        g.addWidget(QtWidgets.QLabel("ツイスト軸:"), 2, 0)
        self._cmb_twist = QtWidgets.QComboBox()
        self._cmb_twist.addItems(["X", "Y", "Z"])
        self._cmb_twist.setToolTip("poseInterpolator を新規作成するときのドライバのツイスト軸 (ジョイントの子方向)")
        g.addWidget(self._cmb_twist, 2, 1)
        lay.addWidget(grp)

        # ---- ポーズ一覧 ---------------------------------------------------
        grp2 = QtWidgets.QGroupBox("ポーズ")
        v = QtWidgets.QVBoxLayout(grp2)
        self._table = QtWidgets.QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ポーズ", "タイプ", "重み", "ターゲット"])
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemDoubleClicked.connect(lambda _it: self._on_goto())
        v.addWidget(self._table, 1)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("ポーズ名:"))
        self._le_name = QtWidgets.QLineEdit()
        self._le_name.setPlaceholderText("空なら自動 (<ジョイント>_pose#)")
        row.addWidget(self._le_name, 1)
        self._cmb_type = QtWidgets.QComboBox()
        for _key, label in _TYPE_LABELS:
            self._cmb_type.addItem(label)
        self._cmb_type.setToolTip(
            "スイング+ツイスト: 回転全体で判定 (既定)\n"
            "スイング: ツイスト軸まわりの回転を無視\n"
            "ツイスト: ツイスト軸まわりの回転だけで判定")
        row.addWidget(self._cmb_type)
        v.addLayout(row)

        btn_add = QtWidgets.QPushButton("現在のポーズ + スカルプトを追加")
        btn_add.setToolTip(
            "今のジョイント姿勢をポーズとして登録し、controlPoints のスカルプトを\n"
            "レスト空間の blendShape ターゲットにしてそのポーズで駆動する。\n"
            "スカルプトが無ければ空のターゲットを作る (後から焼き込める)。")
        btn_add.clicked.connect(self._on_add)
        v.addWidget(btn_add)

        b2 = QtWidgets.QHBoxLayout()
        btn_bake = QtWidgets.QPushButton("選択ポーズに焼き込む")
        btn_bake.setToolTip("controlPoints のスカルプトを選択ポーズのターゲットへ加算する (重み 0.5 以上の姿勢で)")
        btn_bake.clicked.connect(self._on_bake)
        b2.addWidget(btn_bake)
        btn_goto = QtWidgets.QPushButton("ポーズへ移動")
        btn_goto.setToolTip("ジョイントを選択ポーズの姿勢にする (行のダブルクリックでも)")
        btn_goto.clicked.connect(self._on_goto)
        b2.addWidget(btn_goto)
        btn_upd = QtWidgets.QPushButton("姿勢を更新")
        btn_upd.setToolTip("選択ポーズの登録姿勢を今のジョイント姿勢で置き換える")
        btn_upd.clicked.connect(self._on_update_pose)
        b2.addWidget(btn_upd)
        v.addLayout(b2)

        b3 = QtWidgets.QHBoxLayout()
        btn_ren = QtWidgets.QPushButton("名前変更")
        btn_ren.clicked.connect(self._on_rename)
        b3.addWidget(btn_ren)
        btn_del = QtWidgets.QPushButton("削除")
        btn_del.setToolTip("ポーズと、それが駆動していたターゲットを削除する")
        btn_del.clicked.connect(self._on_delete)
        b3.addWidget(btn_del)
        b3.addStretch(1)
        btn_pe = QtWidgets.QPushButton("ポーズエディタ")
        btn_pe.clicked.connect(lambda: mel.eval("PoseEditor"))
        b3.addWidget(btn_pe)
        btn_se = QtWidgets.QPushButton("シェイプエディタ")
        btn_se.clicked.connect(lambda: mel.eval("ShapeEditor"))
        b3.addWidget(btn_se)
        v.addLayout(b3)
        lay.addWidget(grp2, 1)

        hint = QtWidgets.QLabel(
            "手順: ジョイントでポーズ → コンポーネントモードで CV を移動ツールで整える → 「追加」。\n"
            "補正はレスト空間に戻して保存されるので、ポーズと一緒に回り、レストでは消えます。")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #888;")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

    # ------------------------------------------------------------------
    def _install_script_job(self):
        try:
            self._sel_job = cmds.scriptJob(
                event=["SelectionChanged", self._on_selection_changed], protected=False)
        except Exception:
            self._sel_job = None

    def _on_selection_changed(self):
        shape = cne._resolve_curvenet_shape("")
        if shape and shape != self._shape:
            self.refresh()

    def shutdown(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        if self._sel_job is not None:
            try:
                cmds.scriptJob(kill=self._sel_job, force=True)
            except Exception:
                pass
            self._sel_job = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    def _msg(self, text, warn=False):
        self._status.setText(text)
        if warn:
            om.MGlobal.displayWarning("[RetopoGuide PSD] " + text)

    def _joint(self):
        j = self._le_joint.text().strip()
        return j if j and cmds.objExists(j) else ""

    def _pick_joint(self):
        for s in (cmds.ls(selection=True, type="joint") or []):
            self._le_joint.setText(s)
            self._on_joint_changed()
            return
        for s in (cmds.ls(selection=True, type="transform") or []):
            self._le_joint.setText(s)
            self._on_joint_changed()
            return
        self._msg("ジョイントを選択してください。")

    def _on_joint_changed(self):
        self._fill_pi_combo()
        self._fill_poses()

    def _fill_pi_combo(self):
        j = self._joint()
        cur = self._cmb_pi.currentText()
        self._cmb_pi.blockSignals(True)
        self._cmb_pi.clear()
        items = ps.pose_interpolators_for(j) if j else ps.list_pose_interpolators()
        self._cmb_pi.addItems(items)
        i = self._cmb_pi.findText(cur)
        self._cmb_pi.setCurrentIndex(i if i >= 0 else (0 if items else -1))
        self._cmb_pi.blockSignals(False)
        self._pi = self._cmb_pi.currentText()

    def _on_pi_changed(self):
        self._pi = self._cmb_pi.currentText()
        if self._pi and not self._joint():
            d = ps.drivers(self._pi)
            if d:
                self._le_joint.setText(d[0])
        self._fill_poses()

    def _on_new_pi(self):
        j = self._joint()
        if not j:
            self._msg("ドライバジョイントを指定してください。", True)
            return
        try:
            cmds.undoInfo(openChunk=True, chunkName="retopoGuideCreatePoseInterpolator")
            try:
                pi = ps.create_pose_interpolator(j, twist_axis=self._cmb_twist.currentIndex())
            finally:
                cmds.undoInfo(closeChunk=True)
        except Exception as exc:
            self._msg(str(exc), True)
            return
        self._fill_pi_combo()
        i = self._cmb_pi.findText(pi)
        if i >= 0:
            self._cmb_pi.setCurrentIndex(i)
        self._fill_poses()
        self._msg("%s を作成しました。" % pi)

    # ------------------------------------------------------------------
    def refresh(self):
        self._shape = cne._resolve_curvenet_shape("")
        if not self._shape:
            self._lbl_node.setText("<b>retopoGuideNode が選択されていません</b>")
            self._bs = None
        else:
            self._bs = bt.find_blend_shape(self._shape)
            self._lbl_node.setText("<b>%s</b> — blendShape: %s" % (
                self._shape.split("|")[-1], self._bs or "(追加時に作成)"))
        self._fill_pi_combo()
        self._fill_poses()

    def _fill_poses(self):
        self._rows = ps.list_poses(self._pi, self._bs) if self._pi else []
        sel_name = self._selected_pose()
        self._table.setRowCount(len(self._rows))
        type_label = dict(_TYPE_LABELS)
        for r, (idx, name, ptype, w, tgt) in enumerate(self._rows):
            neutral = name in ps.NEUTRAL_POSES
            items = [
                QtWidgets.QTableWidgetItem(name),
                QtWidgets.QTableWidgetItem(type_label.get(ptype, ptype)),
                QtWidgets.QTableWidgetItem("%.3f" % w),
                QtWidgets.QTableWidgetItem("-" if tgt is None else "有 (w[%d])" % tgt),
            ]
            for c, it in enumerate(items):
                it.setData(QtCore.Qt.UserRole, (idx, name))
                if neutral:
                    it.setForeground(QtGui.QBrush(QtGui.QColor(130, 130, 130)))
                if c == 2:
                    it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                self._table.setItem(r, c, it)
            if name == sel_name:
                self._table.selectRow(r)
        self._table.resizeColumnsToContents()

    def _update_weights(self):
        if not self._pi or not cmds.objExists(self._pi) or not self.isVisible():
            return
        for r in range(self._table.rowCount()):
            it = self._table.item(r, 2)
            if it is None:
                continue
            idx, _name = it.data(QtCore.Qt.UserRole)
            w = ps.pose_weight(self._pi, idx)
            txt = "%.3f" % w
            if it.text() != txt:
                it.setText(txt)
            it.setForeground(QtGui.QBrush(QtGui.QColor(230, 180, 80) if w > 0.5
                                          else QtGui.QColor(200, 200, 200)))

    def _selected_pose(self):
        for it in self._table.selectedItems():
            d = it.data(QtCore.Qt.UserRole)
            if d:
                return d[1]
        return None

    def _auto_name(self):
        j = self._joint() or "pose"
        stem = j.split("|")[-1].split(":")[-1] + "_pose"
        used = set(ps.pose_names(self._pi)) if self._pi else set()
        n = 1
        while "%s%d" % (stem, n) in used:
            n += 1
        return "%s%d" % (stem, n)

    # ------------------------------------------------------------------
    def _on_add(self):
        if not self._shape:
            self._msg("カーブネットを選択してください。", True)
            return
        j = self._joint()
        pi = self._pi if (self._pi and cmds.objExists(self._pi)) else None
        if not pi and not j:
            self._msg("ドライバジョイントを指定してください。", True)
            return
        name = self._le_name.text().strip() or self._auto_name()
        ptype = _TYPE_LABELS[self._cmb_type.currentIndex()][0]
        cmds.undoInfo(openChunk=True, chunkName="retopoGuideAddPoseCorrective")
        try:
            pi, idx, bs, tname = ps.add_pose_corrective(
                self._shape, joint=j, pose_name=name, ptype=ptype, pi=pi,
                twist_axis=self._cmb_twist.currentIndex())
        except Exception as exc:
            self._msg(str(exc), True)
            return
        finally:
            cmds.undoInfo(closeChunk=True)
        self._le_name.clear()
        self.refresh()
        i = self._cmb_pi.findText(pi)
        if i >= 0:
            self._cmb_pi.setCurrentIndex(i)
        self._select_pose(tname)
        self._msg("ポーズ '%s' を追加しました (%s.%s)。" % (tname, bs, tname))

    def _on_bake(self):
        name = self._selected_pose()
        if not name or not self._pi:
            self._msg("ポーズを選択してください。", True)
            return
        if name in ps.NEUTRAL_POSES:
            self._msg("ニュートラルポーズには焼き込めません。", True)
            return
        cmds.undoInfo(openChunk=True, chunkName="retopoGuideBakePoseCorrective")
        try:
            bs, widx, n = ps.update_pose_corrective(self._shape, pi=self._pi, pose_name=name)
        except Exception as exc:
            self._msg(str(exc), True)
            return
        finally:
            cmds.undoInfo(closeChunk=True)
        self.refresh()
        self._select_pose(name)
        self._msg("'%s' に %d 点を焼き込みました。" % (name, n))

    def _on_goto(self):
        name = self._selected_pose()
        if not name or not self._pi:
            return
        try:
            ps.go_to_pose(self._pi, name)
        except Exception as exc:
            self._msg(str(exc), True)

    def _on_update_pose(self):
        name = self._selected_pose()
        if not name or not self._pi:
            return
        try:
            ps.update_pose(self._pi, name)
        except Exception as exc:
            self._msg(str(exc), True)
            return
        self._msg("'%s' の姿勢を更新しました。" % name)

    def _on_rename(self):
        name = self._selected_pose()
        if not name or not self._pi or name in ps.NEUTRAL_POSES:
            return
        new, ok = QtWidgets.QInputDialog.getText(self, "名前変更", "新しいポーズ名:", text=name)
        new = (new or "").strip()
        if not ok or not new or new == name:
            return
        try:
            ps.rename_pose(self._pi, name, new)
        except Exception as exc:
            self._msg(str(exc), True)
            return
        self._fill_poses()
        self._select_pose(new)

    def _on_delete(self):
        name = self._selected_pose()
        if not name or not self._pi:
            return
        if name in ps.NEUTRAL_POSES:
            self._msg("ニュートラルポーズは削除できません。", True)
            return
        if QtWidgets.QMessageBox.question(
                self, "削除", "ポーズ '%s' とそのターゲットを削除しますか?" % name,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return
        cmds.undoInfo(openChunk=True, chunkName="retopoGuideDeletePose")
        try:
            ps.delete_pose(self._pi, name)
        except Exception as exc:
            self._msg(str(exc), True)
            return
        finally:
            cmds.undoInfo(closeChunk=True)
        self.refresh()

    def _select_pose(self, name):
        for r in range(self._table.rowCount()):
            it = self._table.item(r, 0)
            if it is not None and it.text() == name:
                self._table.selectRow(r)
                return


# ======================================================================
# エントリポイント
# ======================================================================

_window = None
_WSC_NAME = _WIN_NAME + "WorkspaceControl"


def _on_closed():
    global _window
    if _window is not None:
        try:
            _window.shutdown()
        except Exception:
            pass
        _window = None


def show():
    """ウィンドウを表示する (workspaceControl に格納するので Maya の裏に回らない)。"""
    global _window
    _on_closed()
    ps.load_plugin()
    from Aru_RetopoTool.editor.ui import qt_window
    _window = qt_window.show_dockable(
        _WSC_NAME, "RetopoGuide ポーズ補正 (PSD)", RetopoGuidePsdWindow,
        close_command="import Aru_RetopoTool.editor.ui.psd_ui as _m; _m._on_closed()",
        width=560, height=520)
    return _window
