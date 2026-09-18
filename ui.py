"""Maya-owned window; DG owns live updates, no polling or scene callbacks."""
from . import qt
from maya import cmds
from . import maya_api as api

_window = None


class RetopoWindow(qt.AruMainWindow):
    def __init__(self):
        super().__init__(object_name='Aru_RetopoTool_MainWindow')
        self.setWindowTitle('Aru Retopo Tool')
        self.resize(510, 430)
        self.setMinimumSize(550, 920)
        self.node = None
        central = qt.QWidget(self); self.setCentralWidget(central)
        layout = qt.QVBoxLayout(central)
        title = qt.QLabel('カーブで流れを描き、メッシュの表面に生成')
        title.setWordWrap(True); layout.addWidget(title)
        self.guide, self.reference = qt.QLineEdit(), qt.QLineEdit()
        for label, field, kind in [('リトポガイド', self.guide, 'retopoGuideNode'), ('参照メッシュ', self.reference, 'mesh')]:
            row = qt.QHBoxLayout(); row.addWidget(qt.QLabel(label)); row.addWidget(field, 1)
            button = qt.QPushButton('選択から設定'); row.addWidget(button)
            button.clicked.connect(lambda checked=False, f=field, k=kind: self.run(lambda: self.pick(f, k)))
            layout.addLayout(row)
        edit = qt.QPushButton('ガイドと面を編集（左：カーブ / 中：面・ポイント移動）')
        edit.clicked.connect(lambda: self.run(self.open_editor)); layout.addWidget(edit)
        row=qt.QHBoxLayout()
        for label,callback in [('新規ガイド',self.new_guide),('ガイドをコピーして取り込み',self.import_guide),('ガイド編集設定',self.guide_settings)]:
            button=qt.QPushButton(label);button.clicked.connect(lambda checked=False,cb=callback:self.run(cb));row.addWidget(button)
        layout.addLayout(row)
        construct=qt.QPushButton('輪切り・押し出し・ブリッジ')
        construct.clicked.connect(lambda:self.run(self.open_construction));layout.addWidget(construct)
        self.drag_faces=qt.QCheckBox('Ctrl＋中ドラッグの押し出しで面も作成')
        self.drag_faces.setChecked(bool(cmds.optionVar(q='aruRetopoDragExtrudeFaces')) if cmds.optionVar(exists='aruRetopoDragExtrudeFaces') else True)
        self.drag_faces.toggled.connect(lambda value:cmds.optionVar(iv=('aruRetopoDragExtrudeFaces',int(value))))
        layout.addWidget(self.drag_faces)
        from .editor.curvenet import brush
        self.soft_move=qt.QCheckBox('ソフト移動（周囲のEPも移動・自動接続なし）')
        self.soft_move.setChecked(brush.soft())
        self.soft_move.toggled.connect(lambda value:cmds.optionVar(iv=(brush.SOFT,int(value))))
        layout.addWidget(self.soft_move)
        self.auto_connect=qt.QCheckBox('単点移動で自動マージ・カーブ接続')
        self.auto_connect.setChecked(brush.auto_connect())
        self.auto_connect.toggled.connect(lambda value:cmds.optionVar(iv=(brush.MERGE,int(value))))
        connection_row=qt.QHBoxLayout();connection_row.addWidget(self.auto_connect)
        self.connect_radius=qt.QSpinBox();self.connect_radius.setRange(2,32)
        self.connect_radius.setValue(round(brush.snap_radius()));self.connect_radius.setSuffix(' px')
        self.connect_radius.setToolTip('単点移動で接続する距離。ブラシ半径とは独立です。')
        self.connect_radius.valueChanged.connect(lambda value:cmds.optionVar(fv=(brush.SNAP,float(value))))
        connection_row.addWidget(self.connect_radius);layout.addLayout(connection_row)
        layout.addWidget(qt.QLabel('B＋中ドラッグ：ブラシ半径 / Shift＋左ドラッグ：リラックス'))
        from . import hard_surface
        self.hard_surface=qt.QCheckBox('ハードサーフェース：角・稜線を維持（輪切りの角にEP追加）')
        self.hard_surface.setChecked(bool(hard_surface.enabled()))
        self.hard_surface.toggled.connect(lambda value:cmds.optionVar(iv=(hard_surface.OPTION,int(value))))
        layout.addWidget(self.hard_surface)
        feature=qt.QPushButton('参照メッシュの稜線からガイドを追加')
        feature.clicked.connect(lambda:self.run(self.feature_guides));layout.addWidget(feature)
        form = qt.QFormLayout()
        form.setVerticalSpacing(8)
        self.level = qt.QSpinBox(); self.level.setRange(1, 6); self.level.setValue(2)
        self.iterations = qt.QSpinBox(); self.iterations.setRange(0, 30); self.iterations.setValue(3)
        self.weight = qt.QDoubleSpinBox(); self.weight.setRange(0, 1); self.weight.setSingleStep(.1); self.weight.setValue(1.)
        for spin in (self.level, self.iterations, self.weight):
            spin.setMinimumSize(96, 28)
        self.guard = qt.QCheckBox('前回の面の向き・接続成分を維持'); self.guard.setChecked(True)
        form.addRow('細分化レベル', self.level); form.addRow('表面上で整える回数', self.iterations)
        form.addRow('ガイドの影響', self.weight); form.addRow('投影の安定化', self.guard)
        self.foreground = qt.QCheckBox('面と手前のエッジを最前面に表示')
        self.foreground.setChecked(True)
        self.foreground.toggled.connect(lambda value: self.run(lambda: self.set_foreground(value)))
        form.addRow('最前面表示', self.foreground)
        form.addRow('編集中の表示', qt.QLabel('ロケーター（面・エッジ）'))
        layout.addLayout(form)
        note = qt.QLabel('カーブだけでは面は生成されません。面張りツールでホバーし、中クリックでパッチを確定します。\nShift＋中クリックで解除。確定した面はカーブ編集へ自動追従します。')
        note.setWordWrap(True); layout.addWidget(note)
        create = qt.QPushButton('面張りツールを開始（ホバー → 中クリック）'); create.clicked.connect(lambda: self.run(self.start_patches))
        layout.addWidget(create)
        row = qt.QHBoxLayout()
        for label, callback in [('選択から読み込み', self.load), ('設定を適用', self.apply), ('領域を再検出', self.rebuild)]:
            button = qt.QPushButton(label); button.clicked.connect(lambda checked=False, cb=callback: self.run(cb)); row.addWidget(button)
        layout.addLayout(row)
        bake = qt.QPushButton('通常メッシュとしてコピーを確定')
        bake.clicked.connect(lambda: self.run(self.bake)); layout.addWidget(bake)
        self.status = qt.QLabel('カーブネットと参照メッシュを指定してください。')
        self.status.setWordWrap(True); self.status.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        layout.addWidget(self.status); layout.addStretch()
        # Reopening the window while a guide/output is selected resumes its owner.
        try:
            api.generator_from_selection()
        except ValueError:
            pass
        else:
            self.load()

    def run(self, callback):
        try:
            callback()
            from . import viewport_session
            viewport_session.refresh()
        except Exception as exc:
            self.status.setText(str(exc)); cmds.warning('[Aru Retopo] '+str(exc))

    def pick(self, field, kind):
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        if len(selected) != 1: raise ValueError('対象を1つ選択してください。')
        field.setText(api.shape(selected[0], kind))
        self.node = None

    def open_editor(self):
        from . import guides
        if not self.guide.text().strip(): self.new_guide()
        if not self.node or not cmds.objExists(self.node): self.create()
        guides.edit(self.node)
        self.status.setText('左：カーブ / 中ドラッグ：移動 / 境界カーブをCtrl＋中ドラッグ：押し出し（離して確定・Esc取消） / パッチ上の中：面確定 / Shift＋中：解除')

    def new_guide(self):
        from . import guides
        self.guide.setText(guides.create(self.reference.text().strip()))
        self.node=None

    def import_guide(self):
        from . import guides
        source=(cmds.ls(sl=True,long=True) or [None])[0]
        if not source: raise ValueError('取り込むCurveNetを選択してください。')
        guide=guides.import_legacy(source,self.reference.text().strip() or None)
        self.guide.setText(guide)
        self.reference.setText(cmds.getAttr(guide+'.meshName'))
        if self.node: guides.attach(self.node,guide)

    def guide_settings(self):
        from .guides import settings
        settings()

    def feature_guides(self):
        if not self.node or not cmds.objExists(self.node):
            if not self.guide.text().strip():self.new_guide()
            self.create()
        from . import hard_surface
        self.hard_surface.setChecked(True)
        count=hard_surface.create_guides(self.node)
        self.status.setText('稜線ガイドを{}本追加しました。面は中クリックで選んで張れます。'.format(count))

    def open_construction(self):
        if not self.node or not cmds.objExists(self.node):
            if not self.guide.text().strip():self.new_guide()
            self.create()
        from . import construction
        construction.show(self.node)

    def create(self):
        existing = api.generator_for_guide(self.guide.text().strip(), self.reference.text().strip())
        if existing:
            self.node = existing
            self.report()
            return
        _, self.node = api.create(self.guide.text().strip(), self.reference.text().strip(),
                                  self.level.value(), self.iterations.value(), self.weight.value())
        cmds.setAttr(self.node+'.projectionGuard', self.guard.isChecked())
        api.set_foreground(self.node, self.foreground.isChecked())
        self.report()

    def start_patches(self):
        if not self.node or not cmds.objExists(self.node): self.create()
        from . import patch_context
        patch_context.start(self.node)
        self.status.setText('ホバー：半透明プレビュー / 中クリック：面を確定 / Shift＋中クリック：解除 / Q：終了')

    def require_node(self):
        if not self.node or not cmds.objExists(self.node): self.node = api.generator_from_selection()
        return self.node

    def report(self):
        node = self.require_node()
        self.status.setText(node+'\n'+(api.read_status(node)))

    def load(self):
        self.node = api.generator_from_selection()
        for attr, field in [('guideData', self.guide), ('referenceMesh', self.reference)]:
            sources = cmds.listConnections(self.node+'.'+attr, source=True, destination=False) or []
            field.setText(sources[0] if sources else '')
        self.level.setValue(cmds.getAttr(self.node+'.subdivisions'))
        self.iterations.setValue(cmds.getAttr(self.node+'.relaxIterations'))
        self.weight.setValue(cmds.getAttr(self.node+'.guideWeight'))
        self.guard.setChecked(cmds.getAttr(self.node+'.projectionGuard'))
        self.foreground.blockSignals(True)
        self.foreground.setChecked(api.foreground_enabled(self.node))
        self.foreground.blockSignals(False)
        self.report()

    def set_foreground(self, value):
        from . import viewport_session
        if not value:viewport_session.stop()
        if self.node and cmds.objExists(self.node):api.set_foreground(self.node,value)
        if value and not cmds.about(batch=True):viewport_session.start()

    def apply(self):
        node = self.require_node()
        with api.undo_chunk('Aru Retopo: settings'):
            for attr, value in [('subdivisions', self.level.value()), ('relaxIterations', self.iterations.value()),
                                ('guideWeight', self.weight.value()), ('projectionGuard', self.guard.isChecked())]:
                cmds.setAttr(node+'.'+attr, value)
        self.report()

    def rebuild(self): api.rebuild(self.require_node()); self.report()
    def bake(self):
        baked = api.bake(self.require_node())
        self.status.setText('確定コピー: '+baked+'（元の追従メッシュは維持）')


def show():
    global _window
    if _window is not None:
        try: return _window.show_and_raise()
        except RuntimeError: _window = None
    _window = RetopoWindow()
    return _window.show_and_raise()
