"""
skin_weight_ui.py — RetopoGuide スキンウェイトエディタ
====================================================
Maya の Component Editor は retopoGuideNode (MPxSurfaceShape) では
「選択した CV だけ」を表示できず、常に全 CV が並んでしまう。
(MItGeometry が kPluginShape を受け付けないため — 詳細は
 curvenet/curve_net_edit.py のコメント参照)

本 UI は選択中の CV だけを行として表示し、直接ウェイトを編集する。

Usage (Script Editor)::

    from Aru_RetopoTool.editor.ui import skin_weight_ui
    skin_weight_ui.show()
"""

from __future__ import annotations

import maya.cmds as cmds
import maya.OpenMaya as om

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

from ..curvenet import curve_net_edit as cne

_WIN_NAME = "retopoGuideSkinWeightUI"


class RetopoGuideSkinWeightWindow(QtWidgets.QWidget):
    """選択 CV のスキンウェイトを表形式で編集する。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(_WIN_NAME)
        self.setWindowTitle("RetopoGuide スキンウェイト")
        self.resize(720, 460)

        self._shape = ""
        self._sc = ""
        self._cvs = []
        self._influences = []
        self._updating = False
        self._sel_job = None
        self._slider_cells = None   # スライド中に対象にしている (cv, joint) のリスト
        self._slider_base = {}      # 掴んだ時の値
        self._slider_chunk = False
        self._handle_ep = {}        # handle cv -> 親 EP
        self._ep_handles = {}       # EP -> [handle cv]

        self._build_ui()
        self._install_script_job()
        self.refresh()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QHBoxLayout()
        self._lbl_node = QtWidgets.QLabel("-")
        info.addWidget(self._lbl_node, 1)

        self._chk_auto = QtWidgets.QCheckBox("選択に追従")
        self._chk_auto.setChecked(True)
        self._chk_auto.setToolTip(
            "ビューポートの選択が変わったら自動でテーブルを更新する")
        info.addWidget(self._chk_auto)

        self._chk_all_inf = QtWidgets.QCheckBox("全ジョイント")
        self._chk_all_inf.setChecked(False)
        self._chk_all_inf.setToolTip(
            "オフ: 選択 CV にウェイトを持つジョイントだけを列に出す (速い)\n"
            "オン: 全インフルエンスを列に出す (新しいジョイントにウェイトを振るとき)")
        self._chk_all_inf.toggled.connect(lambda _s: self.refresh())
        info.addWidget(self._chk_all_inf)

        self._chk_follow = QtWidgets.QCheckBox("ハンドルは EP に追従")
        self._chk_follow.setChecked(True)
        self._chk_follow.setToolTip(
            "オン: EP を編集すると、その EP についているハンドルにも同じウェイトを入れる。\n"
            "ハンドルのセルを編集した場合も EP とその全ハンドルに適用される。\n"
            "(ハンドルのウェイトが EP と違うと、そのスプラインだけ接線が別のジョイントに引かれて反る)")
        self._chk_follow.toggled.connect(lambda _s: self.refresh())
        info.addWidget(self._chk_follow)

        btn_align = QtWidgets.QPushButton("ハンドルを EP に揃える")
        btn_align.setToolTip(
            "選択中の CV (未選択なら全 CV) について、ハンドルのウェイトを親 EP からコピーする")
        btn_align.clicked.connect(self._on_align_handles)
        info.addWidget(btn_align)

        btn_ref = QtWidgets.QPushButton("更新")
        btn_ref.clicked.connect(self.refresh)
        info.addWidget(btn_ref)
        lay.addLayout(info)

        self._table = QtWidgets.QTableWidget()
        self._table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectItems)
        self._table.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self._table, 1)

        # ---- 一括設定 -------------------------------------------------
        ops = QtWidgets.QHBoxLayout()
        self._chk_norm = QtWidgets.QCheckBox("正規化")
        self._chk_norm.setChecked(True)
        self._chk_norm.setToolTip(
            "他ジョイントとの合計が 1.0 になるよう自動調整する")
        ops.addWidget(self._chk_norm)

        # 入力モード (SIWeightEditor の Abs / Add / Add%)
        self._mode_group = QtWidgets.QButtonGroup(self)
        self._mode_btns = {}
        for key, label, tip in (
                ("abs", "絶対", "入力値をそのままセルに入れる"),
                ("add", "加算", "現在値に入力値を足す (負で減算)"),
                ("pct", "加算%", "現在値に対して指定比率を足す (50 なら ×1.5)")):
            b = QtWidgets.QRadioButton(label)
            b.setToolTip(tip)
            b.toggled.connect(lambda on, k=key: on and self._set_mode(k))
            self._mode_group.addButton(b)
            self._mode_btns[key] = b
            ops.addWidget(b)
        self._mode = "add"

        ops.addStretch(1)
        ops.addWidget(QtWidgets.QLabel("値:"))
        self._spin = QtWidgets.QDoubleSpinBox()
        self._spin.setDecimals(4)
        self._spin.setSingleStep(0.05)
        ops.addWidget(self._spin)

        btn_set = QtWidgets.QPushButton("選択セルに適用")
        btn_set.setToolTip("現在のモードで「値」を選択セルに適用")
        btn_set.clicked.connect(self._on_set_selected)
        ops.addWidget(btn_set)

        for label, val in (("0", 0.0), ("0.5", 0.5), ("1", 1.0)):
            b = QtWidgets.QPushButton(label)
            b.setFixedWidth(36)
            b.setToolTip("絶対値で設定")
            b.clicked.connect(lambda _=False, v=val: self._apply_value(v))
            ops.addWidget(b)
        lay.addLayout(ops)

        # ---- スライダ / 相対増減 ----------------------------------------
        sl = QtWidgets.QHBoxLayout()
        sl.addWidget(QtWidgets.QLabel("スライダ:"))
        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setToolTip(
            "選択セルのウェイトをドラッグで変えます。\n"
            "加算 / 加算% モードでは「掴んだ時の値」からの増減で、離すと中央に戻ります。\n"
            "1 回のドラッグ = 1 回の Undo。")
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.valueChanged.connect(self._on_slider_value)
        sl.addWidget(self._slider, 1)
        self._mode_btns["add"].setChecked(True)
        self._set_mode("add")
        for label, dv in (("−0.1", -0.1), ("−0.05", -0.05), ("+0.05", 0.05), ("+0.1", 0.1)):
            b = QtWidgets.QPushButton(label)
            b.setFixedWidth(52)
            b.setToolTip("選択セルのウェイトを現在値から増減")
            b.clicked.connect(lambda _=False, d=dv: self._nudge_selected(d))
            sl.addWidget(b)
        lay.addLayout(sl)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #888;")
        lay.addWidget(self._status)

    # ------------------------------------------------------------------
    # 選択追従
    # ------------------------------------------------------------------

    def _install_script_job(self):
        try:
            self._sel_job = cmds.scriptJob(
                event=["SelectionChanged", self._on_selection_changed],
                protected=False)
        except Exception:
            self._sel_job = None

    def _on_selection_changed(self):
        if self._chk_auto.isChecked():
            self.refresh()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self):
        if self._sel_job is not None:
            try:
                cmds.scriptJob(kill=self._sel_job, force=True)
            except Exception:
                pass
            self._sel_job = None

    # ------------------------------------------------------------------
    # EP / ハンドルの対応
    # ------------------------------------------------------------------

    def _load_topology(self):
        """ハンドル → 親 EP、EP → ハンドル群 を netData から作る。"""
        self._handle_ep = {}
        self._ep_handles = {}
        if not self._shape or not cmds.objExists(self._shape):
            return
        try:
            cn = cne.RetopoGuideAccessor(self._shape).read()
        except Exception:
            return
        for sp in cn.splines:
            for ep, h in ((sp[0], sp[1]), (sp[3], sp[2])):
                self._handle_ep[h] = ep
                self._ep_handles.setdefault(ep, []).append(h)

    def _group_of(self, cv):
        """*cv* と一緒に動かすべき CV (EP + そのハンドル)。追従オフなら自分だけ。"""
        if not self._chk_follow.isChecked():
            return [cv]
        ep = self._handle_ep.get(cv, cv)
        return [ep] + list(self._ep_handles.get(ep, []))

    def _on_align_handles(self):
        """ハンドルのウェイトを親 EP からコピーする。"""
        if not self._sc:
            return
        sel = {c for c, _ in self._selected_cells()} or set(self._cvs or [])
        eps = {self._handle_ep.get(c, c) for c in sel} if sel else set(self._ep_handles)
        eps = [e for e in eps if e in self._ep_handles]
        if not eps:
            self._status.setText("揃える対象がありません。")
            return
        cur = cne.get_skin_weights(self._shape, cv_indices=eps) or {}
        rows = {}
        for ep in eps:
            w = {k.split("|")[-1]: v for k, v in (cur.get(ep) or {}).items() if abs(v) > 1e-9}
            for h in self._ep_handles.get(ep, []):
                rows[h] = w
        n = self._write_rows(rows, chunk_name="retopoGuideAlignHandleWeights")
        self._status.setText("ハンドル %d 個を EP に揃えました。" % n)
        if not self._update_rows(list(rows)):
            self.refresh()

    def _write_rows(self, rows, chunk_name="retopoGuideSkinWeight"):
        """``{cv: {joint: w}}`` (完全な行) を Undo 可能な経路で書く。書いた行数を返す。"""
        if not rows:
            return 0
        cmds.undoInfo(openChunk=True, chunkName=chunk_name)
        try:
            if hasattr(cmds, "retopoGuideSetSkinWeights"):
                import json as _json
                cmds.retopoGuideSetSkinWeights(
                    sh=self._shape, d=_json.dumps({str(k): v for k, v in rows.items()}), nrm=False)
            else:
                for cv, w in rows.items():
                    tv = [(j, v) for j, v in w.items()] or [(self._influences[0], 0.0)]
                    cmds.skinPercent(self._sc, "{}.vtx[{}]".format(self._shape, cv),
                                     transformValue=tv, normalize=0)
        finally:
            cmds.undoInfo(closeChunk=True)
        return len(rows)

    # ------------------------------------------------------------------
    # データ更新
    # ------------------------------------------------------------------

    def refresh(self):
        shape, cvs = cne.get_selected_cv_indices()
        self._shape = shape
        self._cvs = cvs
        self._load_topology()

        if not shape:
            self._lbl_node.setText(
                "<b>retopoGuideNode が選択されていません</b>")
            self._set_table([], [], {})
            self._status.setText("")
            return

        self._sc = cne._find_skincluster(shape) or ""
        if not self._sc:
            self._lbl_node.setText(
                "<b>{}</b> — skinCluster なし".format(shape.split("|")[-1]))
            self._set_table([], [], {})
            self._status.setText("")
            return

        self._influences = cmds.skinCluster(
            self._sc, q=True, influence=True) or []
        n_all = cne._get_cv_count(shape)

        if not cvs:
            self._lbl_node.setText(
                "<b>{}</b> — {} (CV {} 個)".format(
                    shape.split("|")[-1], self._sc, n_all))
            self._set_table([], self._influences, {})
            self._status.setText(
                "CV が選択されていません。コンポーネントモードで "
                "ポイント/ハンドルを選択してください。")
            return

        weights = cne.get_skin_weights(shape, cv_indices=cvs) or {}
        self._lbl_node.setText(
            "<b>{}</b> — {} (選択 {} / 全 {} CV)".format(
                shape.split("|")[-1], self._sc, len(cvs), n_all))
        self._set_table(cvs, self._visible_influences(weights), weights)
        self._status.setText("")

    def _visible_influences(self, weights):
        """列に出すジョイント。既定は選択 CV のどこかにウェイトがあるものだけ。

        80 ジョイント × 600 CV を全部セルにするとテーブル構築だけで 1 秒超える。
        """
        if self._chk_all_inf.isChecked():
            return list(self._influences)
        used = set()
        for w in weights.values():
            for j, v in w.items():
                if abs(v) > 1e-6:
                    used.add(j)
        short = {j.split("|")[-1]: j for j in self._influences}
        vis = [j for j in self._influences
               if j in used or short.get(j.split("|")[-1]) in used
               or j.split("|")[-1] in used]
        return vis or list(self._influences)[:1]

    def _set_table(self, cvs, influences, weights):
        self._updating = True
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.clear()
            self._table.setRowCount(len(cvs))
            self._table.setColumnCount(len(influences) + 1)
            self._table.setHorizontalHeaderLabels(
                [j.split("|")[-1] for j in influences] + ["合計"])
            self._table.setVerticalHeaderLabels(
                ["cv[{}]{}".format(i, " h→{}".format(self._handle_ep[i]) if i in self._handle_ep else "")
                 for i in cvs])
            self._table_influences = list(influences)
            self._table_rows = {cv: r for r, cv in enumerate(cvs)}

            for r, cv in enumerate(cvs):
                self._fill_row(r, cv, influences, weights.get(cv, {}))

            self._table.resizeColumnsToContents()
        finally:
            self._table.setUpdatesEnabled(True)
            self._updating = False

    def _fill_row(self, r, cv, influences, w):
        """1 行分のセルを (作り直して) 埋める。"""
        # フルパス / 短名のどちらで来ても引けるように
        wl = {}
        for j, v in w.items():
            wl[j] = v
            wl[j.split("|")[-1]] = v
        total = 0.0
        is_handle = cv in self._handle_ep
        for c, j in enumerate(influences):
            v = float(wl.get(j, wl.get(j.split("|")[-1], 0.0)))
            total += v
            item = QtWidgets.QTableWidgetItem("{:.4f}".format(v))
            item.setTextAlignment(QtCore.Qt.AlignRight
                                  | QtCore.Qt.AlignVCenter)
            item.setData(QtCore.Qt.UserRole, (cv, j))
            if v <= 1e-9:
                item.setForeground(QtGui.QBrush(QtGui.QColor(120, 120, 120)))
            elif is_handle:
                # ハンドル行は控めに (追従オンなら EP の編集で自動的に揃う)
                item.setForeground(QtGui.QBrush(QtGui.QColor(170, 190, 200)))
            self._table.setItem(r, c, item)
        tot = QtWidgets.QTableWidgetItem("{:.4f}".format(total))
        tot.setFlags(QtCore.Qt.ItemIsEnabled)
        tot.setTextAlignment(QtCore.Qt.AlignRight
                             | QtCore.Qt.AlignVCenter)
        if abs(total - 1.0) > 1e-3:
            tot.setForeground(QtGui.QBrush(QtGui.QColor(220, 120, 60)))
        self._table.setItem(r, len(influences), tot)

    def _update_rows(self, cvs):
        """編集した CV の行だけ読み直す。列構成が変わるなら False。"""
        rows = getattr(self, "_table_rows", None) or {}
        infl = getattr(self, "_table_influences", None) or []
        cvs = [cv for cv in cvs if cv in rows]
        if not cvs or not infl:
            return False
        weights = cne.get_skin_weights(self._shape, cv_indices=cvs) or {}
        if not self._chk_all_inf.isChecked():
            shown = {j.split("|")[-1] for j in infl}
            for w in weights.values():
                for j, v in w.items():
                    if abs(v) > 1e-6 and j.split("|")[-1] not in shown:
                        return False   # 新しいジョイントにウェイトが付いた
        self._updating = True
        self._table.setUpdatesEnabled(False)
        try:
            for cv in cvs:
                self._fill_row(rows[cv], cv, infl, weights.get(cv, {}))
        finally:
            self._table.setUpdatesEnabled(True)
            self._updating = False
        return True

    # ------------------------------------------------------------------
    # 編集
    # ------------------------------------------------------------------

    def _on_item_changed(self, item):
        if self._updating:
            return
        data = item.data(QtCore.Qt.UserRole)
        if not data:
            return
        cv, joint = data
        try:
            val = float(item.text())
        except ValueError:
            self.refresh()
            return
        val = max(0.0, min(1.0, val))
        self._write([(cv, joint, val)])

    def _on_set_selected(self):
        cells = self._selected_cells()
        if not cells:
            self._status.setText("セルが選択されていません。")
            return
        base = self._read_cells(cells)
        x = self._spin.value()
        self._write([(cv, j, self._mode_value(base[(cv, j)], x)) for cv, j in cells])

    # ---- 入力モード ------------------------------------------------------
    _MODE_SPEC = {
        # mode: (spin min, spin max, spin default, slider min, slider max, slider rest)
        "abs": (0.0, 1.0, 1.0, 0, 1000, None),
        "add": (-1.0, 1.0, 0.1, -1000, 1000, 0),
        "pct": (-100.0, 100.0, 10.0, -1000, 1000, 0),
    }

    def _set_mode(self, mode):
        self._mode = mode
        smin, smax, sdef, lmin, lmax, rest = self._MODE_SPEC[mode]
        self._spin.blockSignals(True)
        self._spin.setRange(smin, smax)
        self._spin.setSingleStep(5.0 if mode == "pct" else 0.05)
        self._spin.setDecimals(1 if mode == "pct" else 4)
        self._spin.setValue(sdef)
        self._spin.blockSignals(False)
        self._slider.blockSignals(True)
        self._slider.setRange(lmin, lmax)
        self._slider.setValue(rest if rest is not None else lmax)
        self._slider.blockSignals(False)

    def _slider_to_value(self, s):
        if self._mode == "pct":
            return s / 10.0          # -100..100 %
        return s / 1000.0            # abs: 0..1 / add: -1..1

    def _mode_value(self, base, x):
        """現在値 *base* にモードに応じて *x* を適用した新しい値。"""
        if self._mode == "abs":
            v = x
        elif self._mode == "add":
            v = base + x
        else:
            v = base * (1.0 + x / 100.0)
        return max(0.0, min(1.0, v))

    def _read_cells(self, cells):
        """(cv, joint) -> 現在のウェイト。追従オンならハンドルは親 EP の値を返す。"""
        follow = self._chk_follow.isChecked()
        lead = {cv: (self._handle_ep.get(cv, cv) if follow else cv) for cv, _ in cells}
        cur = cne.get_skin_weights(self._shape, cv_indices=sorted(set(lead.values()))) or {}
        out = {}
        for cv, j in cells:
            w = {k.split("|")[-1]: v for k, v in (cur.get(lead[cv]) or {}).items()}
            out[(cv, j)] = w.get(j.split("|")[-1], 0.0)
        return out

    def _selected_cells(self):
        cells = []
        for item in self._table.selectedItems():
            data = item.data(QtCore.Qt.UserRole)
            if data:
                cells.append((data[0], data[1]))
        return cells

    def _apply_value(self, val):
        cells = self._selected_cells()
        if not cells:
            self._status.setText("セルが選択されていません。")
            return
        self._write([(cv, j, val) for cv, j in cells])

    def _nudge_selected(self, delta):
        """選択セルを現在値から *delta* だけ増減する。"""
        cells = self._selected_cells()
        if not cells:
            self._status.setText("セルが選択されていません。")
            return
        base = self._read_cells(cells)
        self._write([(cv, j, max(0.0, min(1.0, base[(cv, j)] + delta))) for cv, j in cells])

    # ---- スライダ: 掴んだ時の値を基準にモードで増減し、Undo は 1 回にまとめる ----
    def _on_slider_pressed(self):
        self._slider_cells = self._selected_cells()
        if not self._slider_cells:
            self._status.setText("セルが選択されていません。")
            return
        self._slider_base = self._read_cells(self._slider_cells)
        cmds.undoInfo(openChunk=True, chunkName="retopoGuideSkinWeightSlide")
        self._slider_chunk = True

    def _on_slider_value(self, s):
        x = self._slider_to_value(s)
        self._spin.blockSignals(True)
        self._spin.setValue(x)
        self._spin.blockSignals(False)
        if self._slider.isSliderDown() and self._slider_cells:
            base = self._slider_base
            self._write([(cv, j, self._mode_value(base[(cv, j)], x))
                         for cv, j in self._slider_cells], chunk=False)

    def _on_slider_released(self):
        if self._slider_chunk:
            cmds.undoInfo(closeChunk=True)
            self._slider_chunk = False
        if self._slider_cells:
            self._update_rows(sorted({c for c, _ in self._slider_cells}))
        self._slider_cells = None
        # 相対モードは中央 (=変化なし) に戻す
        rest = self._MODE_SPEC[self._mode][5]
        if rest is not None:
            self._slider.blockSignals(True)
            self._slider.setValue(rest)
            self._slider.blockSignals(False)

    def _write(self, edits, chunk=True):
        if not self._sc:
            return
        nrm = self._chk_norm.isChecked()
        by_cv = {}
        for cv, joint, val in edits:
            # 追従オン: ハンドルのセルを編集しても親 EP への編集として扱う
            lead = self._handle_ep.get(cv, cv) if self._chk_follow.isChecked() else cv
            by_cv.setdefault(lead, {})[joint] = val
        # 正規化は「編集したジョイント以外を比例配分」— skinPercent と同じ意味。
        # 完全な行を作ってから書くので、コマンド経路 / skinPercent 経路で結果が揃う。
        cur = cne.get_skin_weights(self._shape, cv_indices=list(by_cv)) or {}
        rows = {}
        for cv, ed in by_cv.items():
            w = {k.split("|")[-1]: v for k, v in (cur.get(cv) or {}).items()}
            fixed = set()
            for j, v in ed.items():
                w[j.split("|")[-1]] = v
                fixed.add(j.split("|")[-1])
            if nrm:
                want = max(0.0, 1.0 - sum(w[j] for j in fixed))
                rest = sum(v for j, v in w.items() if j not in fixed)
                if rest > 1e-12:
                    for j in list(w):
                        if j not in fixed:
                            w[j] = w[j] * want / rest
            row = {j: v for j, v in w.items() if abs(v) > 1e-9}
            for m in self._group_of(cv):
                rows[m] = row
        if chunk:
            cmds.undoInfo(openChunk=True, chunkName="retopoGuideSkinWeight")
        try:
            if hasattr(cmds, "retopoGuideSetSkinWeights"):
                import json as _json
                cmds.retopoGuideSetSkinWeights(
                    sh=self._shape, d=_json.dumps({str(k): v for k, v in rows.items()}), nrm=False)
            else:
                # プラグインが古い (コマンド未登録) 場合は skinPercent
                for cv, w in rows.items():
                    tv = list(w.items()) or [(self._influences[0], 0.0)]
                    cmds.skinPercent(self._sc, "{}.vtx[{}]".format(self._shape, cv),
                                     transformValue=tv, normalize=0)
        except Exception as exc:
            om.MGlobal.displayWarning(
                "[RetopoGuide] ウェイト設定に失敗: {}".format(exc))
        finally:
            if chunk:
                cmds.undoInfo(closeChunk=True)
        if not self._update_rows(list(rows)):
            self.refresh()


# ======================================================================
# エントリポイント
# ======================================================================

_window = None
_WSC_NAME = _WIN_NAME + "WorkspaceControl"


def _on_closed():
    """workspaceControl が閉じられた (closeCommand)。scriptJob を止める。"""
    global _window
    if _window is not None:
        try:
            _window.shutdown()
        except Exception:
            pass
        _window = None


def show():
    """ウィンドウを表示する (Maya の workspaceControl に格納するので裏に回らない)。"""
    global _window
    _on_closed()
    from Aru_RetopoTool.editor.ui import qt_window
    _window = qt_window.show_dockable(
        _WSC_NAME, "RetopoGuide スキンウェイト", RetopoGuideSkinWeightWindow,
        close_command="import Aru_RetopoTool.editor.ui.skin_weight_ui as _m; _m._on_closed()")
    return _window
