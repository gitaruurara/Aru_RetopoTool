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
        self.setMinimumSize(550, 780)
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

    def run(self, callback):
        try: callback()
        except Exception as exc:
            self.status.setText(str(exc)); cmds.warning('[Aru Retopo] '+str(exc))

    def pick(self, field, kind):
        selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        if len(selected) != 1: raise ValueError('対象を1つ選択してください。')
        field.setText(api.shape(selected[0], kind))

    def open_editor(self):
        from . import guides
        if not self.guide.text().strip(): self.new_guide()
        if not self.node or not cmds.objExists(self.node): self.create()
        guides.edit(self.node)
        self.status.setText('左：カーブ / ポイント上の中ドラッグ：移動 / パッチ上の中クリック：面確定 / Shift＋中：解除')

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

    def open_construction(self):
        if not self.node or not cmds.objExists(self.node):
            if not self.guide.text().strip():self.new_guide()
            self.create()
        from . import construction
        construction.show(self.node)

    def create(self):
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
        self.status.setText(node+'\n'+(cmds.getAttr(node+'.status') or ''))

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
        if self.node and cmds.objExists(self.node): api.set_foreground(self.node, value)

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
