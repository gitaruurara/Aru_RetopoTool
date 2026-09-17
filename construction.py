"""Preview/commit tools for ring guides and one-row boundary extrusion."""
import json
from collections import defaultdict
from maya import cmds
import maya.api.OpenMaya as om
from . import qt
from . import core, maya_api as api, patch_context
from .editor.curvenet import curve_net_edit as edit, curve_net_context as context
from .editor.curvenet.curve_net_relax import _world_data

preview_lines = {}
preview_points = {}
_window = None
NAME = 'aruRetopoConstructionContext'


def boundary_edges(cn, requested, keys, normal):
    """Use selected EP chain, or expand one EP along the unbranched boundary."""
    owners=defaultdict(int)
    if keys:
        for loop in core.regions(cn.positions,cn.splines,normal):
            if core.patch_key(loop) in keys:
                for side in loop:
                    for si,_ in side: owners[si]+=1
        candidates={si for si in range(len(cn.splines)) if owners[si]<2}
    else: candidates=set(range(len(cn.splines)))
    requested=set(requested)&set(cn.endpoint_indices())
    if not requested: raise ValueError('押し出す境界のEPを選択してください。1点なら境界全体、複数なら選択範囲を使います。')
    if len(requested)>1:
        chosen={si for si in candidates if cn.splines[si][0] in requested and cn.splines[si][3] in requested}
    else:
        connected=set(requested);chosen=set()
        while True:
            extra={si for si in candidates if cn.splines[si][0] in connected or cn.splines[si][3] in connected}-chosen
            if not extra:break
            chosen.update(extra)
            connected.update(v for si in extra for v in (cn.splines[si][0],cn.splines[si][3]))
    adj=defaultdict(list)
    for si in chosen:
        a,_,_,b=cn.splines[si];adj[a].append((b,si));adj[b].append((a,si))
    if not adj or any(len(v)>2 for v in adj.values()):
        raise ValueError('分岐のない境界列を選択してください。分岐がある場合は連続したEPを複数選択してください。')
    ends=[v for v in adj if len(adj[v])==1]
    if len(ends) not in (0,2): raise ValueError('連続した境界を1列だけ選択してください。')
    start=min(ends or list(adj));current=start;used=set();ordered=[]
    while True:
        options=[(v,si) for v,si in adj[current] if si not in used]
        if not options:break
        other,si=options[0];used.add(si);ordered.append((current,other,si));current=other
    if used!=chosen:raise ValueError('離れた境界が含まれています。1列ずつ押し出してください。')
    return ordered


def extrude(cn, mesh, edges, vector):
    """Create one projected row without changing any original CV or index."""
    fn,dag=edit._get_mesh_fn(mesh)
    old_eps=sorted({v for a,b,_ in edges for v in (a,b)})
    new={};bridges={};new_edges=set()
    from .editor.curvenet import curve_net_symmetry as symmetry
    mirrored_vector=None
    if symmetry.is_enabled():
        origin=symmetry.mirror_point([0,0,0],mesh)
        mirrored_vector=[a-b for a,b in zip(symmetry.mirror_point(vector,mesh),origin)]
    for ep in old_eps:
        p=cn.positions[ep]
        delta=vector
        if mirrored_vector is not None:
            partner=symmetry.find_mirror_ep(cn,mesh,ep,1e-5)
            if partner in old_eps:
                side=symmetry.plane_coord(p,mesh)
                if abs(side)<1e-6:delta=[(a+b)*.5 for a,b in zip(vector,mirrored_vector)]
                elif side<0:delta=mirrored_vector
        q,face,bary=edit._closest_point_on_mesh(fn,dag,[p[k]+delta[k] for k in range(3)])
        if sum((q[k]-p[k])**2 for k in range(3))<1e-10:
            raise ValueError('押し出し先が元の点と重なります。方向または距離を変えてください。')
        new[ep]=cn.add_cv(q,surface=(face,bary))
    for a,b,si in edges:
        new_edges.add(context._add_spline_to_cn(cn,mesh,new[a],new[b]))
    for ep in old_eps:
        bridges[ep]=context._add_spline_to_cn(cn,mesh,ep,new[ep])
    cn.classify_endpoints()
    normals=lambda p: edit._get_normal_at_point(fn,p)
    keys=set()
    bridge_ids=set(bridges.values())
    for loop in core.regions(cn.positions,cn.splines,normals):
        ids={si for side in loop for si,_ in side}
        if len(loop)==4 and len(ids&bridge_ids)==2 and len(ids&new_edges)==1:
            keys.add(core.patch_key(loop))
    if len(keys)!=len(edges):
        raise ValueError('押し出しが折り返すか交差しています。方向・距離を調整してください。')
    from .symmetry_ops import patch_keys
    return patch_keys(cn,mesh,keys,create=True)


def chain_vertices(edges):
    if not edges: raise ValueError('境界が選択されていません。')
    vertices=[edges[0][0]]+[b for a,b,si in edges]
    closed=vertices[0]==vertices[-1]
    return (vertices[:-1] if closed else vertices),closed


def bridge_pairs(first, second, shift=0, reverse=False):
    a,closed_a=chain_vertices(first);b,closed_b=chain_vertices(second)
    if closed_a!=closed_b:raise ValueError('閉じたリング同士、または開いた境界同士を指定してください。')
    if len(a)!=len(b):raise ValueError('ポイント数が異なります：A {}点 / B {}点。同じ点数に揃えてください。'.format(len(a),len(b)))
    if set(a)&set(b):raise ValueError('AとBはポイントを共有しない別の境界を指定してください。')
    if reverse:b=list(reversed(b))
    if closed_a:
        shift=int(shift)%len(b);b=b[shift:]+b[:shift]
    elif shift:raise ValueError('接続位置のずらしは閉じたリングで使用できます。開いた境界は向き反転で調整してください。')
    return list(zip(a,b))


def best_alignment(cn, first, second):
    a,closed=chain_vertices(first)
    options=[]
    for reverse in (False,True):
        for shift in range(len(a) if closed else 1):
            pairs=bridge_pairs(first,second,shift,reverse)
            cost=sum(sum((cn.positions[x][k]-cn.positions[y][k])**2 for k in range(3)) for x,y in pairs)
            options.append((cost,shift,reverse))
    _,shift,reverse=min(options)
    return shift,reverse


def bridge(cn, mesh, first, second, shift=0, reverse=False):
    """Connect existing equal-count boundaries; no original CV is moved."""
    pairs=bridge_pairs(first,second,shift,reverse)
    existing={frozenset((a,b)) for a,_,_,b in cn.splines}
    if any(frozenset(pair) in existing for pair in pairs):
        raise ValueError('対応点間に既存カーブがあります。未接続の境界を選択してください。')
    if any(sum((cn.positions[a][k]-cn.positions[b][k])**2 for k in range(3))<1e-10 for a,b in pairs):
        raise ValueError('対応点が重なっています。境界の位置を調整してください。')
    joins={context._add_spline_to_cn(cn,mesh,a,b) for a,b in pairs}
    cn.classify_endpoints()
    fn,_=edit._get_mesh_fn(mesh)
    a_ids={si for a,b,si in first};b_ids={si for a,b,si in second}
    keys=set()
    for loop in core.regions(cn.positions,cn.splines,lambda p:edit._get_normal_at_point(fn,p)):
        ids={si for side in loop for si,_ in side}
        if len(loop)==4 and len(ids&joins)==2 and len(ids&a_ids)==1 and len(ids&b_ids)==1:
            keys.add(core.patch_key(loop))
    if len(keys)!=len(first):
        raise ValueError('接続がねじれるか折り返しています。接続位置・向き反転を調整してください。')
    from .symmetry_ops import patch_keys
    return patch_keys(cn,mesh,keys,create=True)


class ConstructionWindow(qt.AruMainWindow):
    def __init__(self,node):
        super().__init__(object_name='Aru_RetopoConstructionWindow')
        self.node=node;self.pending=None;self.previous=None;self.boundaries={};self._preview_requested=False
        self.setWindowTitle('Aru Retopo — 輪切り・押し出し・ブリッジ')
        self.setMinimumSize(480,660)
        body=qt.QWidget(self);self.setCentralWidget(body);layout=qt.QVBoxLayout(body)
        form=qt.QFormLayout();self.form=form;form.setVerticalSpacing(8);layout.addLayout(form)
        self.mode=qt.QComboBox();self.mode.addItems(['輪切り','境界を一段押し出し','境界間をブリッジ'])
        self.axis=qt.QComboBox();self.axis.addItems(['X','Y','Z']);self.axis.setCurrentIndex(1)
        self.count=qt.QSpinBox();self.count.setRange(3,128)
        self.count.setValue(cmds.optionVar(q='aruRetopoRingCount') if cmds.optionVar(exists='aruRetopoRingCount') else 8)
        self.phase=qt.QDoubleSpinBox();self.phase.setRange(-360,360);self.phase.setSuffix(' °')
        self.phase.setValue(cmds.optionVar(q='aruRetopoRingPhase') if cmds.optionVar(exists='aruRetopoRingPhase') else 0)
        self.offset=qt.QDoubleSpinBox();self.offset.setRange(-100000,100000);self.offset.setDecimals(3);self.offset.setSingleStep(.1)
        self.offset.setValue(cmds.optionVar(q='aruRetopoRingOffset') if cmds.optionVar(exists='aruRetopoRingOffset') else 0)
        self.distance=qt.QDoubleSpinBox();self.distance.setRange(-100000,100000);self.distance.setDecimals(3);self.distance.setValue(.5);self.distance.setSingleStep(.1)
        self.faces=qt.QCheckBox('作成した帯の面も確定');self.faces.setChecked(True)
        for label,widget in [('作成方法',self.mode),('ワールド方向',self.axis),('輪切りのポイント数',self.count),('ポイントの回転配置',self.phase),('輪切り位置（メッシュ中心から）',self.offset),('押し出し距離',self.distance),('',self.faces)]:form.addRow(label,widget)
        self.bridge_box=qt.QGroupBox('ブリッジする境界');self.bridge_box.setMinimumHeight(200);bridge_layout=qt.QVBoxLayout(self.bridge_box)
        self.boundary_labels={}
        for name in ('A','B'):
            row=qt.QHBoxLayout();label=qt.QLabel(name+'：未指定');self.boundary_labels[name]=label
            button=qt.QPushButton('選択を境界'+name+'に登録')
            button.clicked.connect(lambda checked=False,n=name:self.run(lambda:self.capture_boundary(n)))
            row.addWidget(label);row.addWidget(button);bridge_layout.addLayout(row)
        self.shift=qt.QSpinBox();self.shift.setRange(0,127)
        self.reverse=qt.QCheckBox('Bの向きを反転')
        bf=qt.QFormLayout();bf.setVerticalSpacing(8);self.shift.setMinimumHeight(28);bf.addRow('接続位置をずらす',self.shift);bf.addRow(self.reverse);bridge_layout.addLayout(bf)
        auto=qt.QPushButton('近いポイント同士に合わせる');auto.clicked.connect(lambda:self.run(self.align));bridge_layout.addWidget(auto)
        layout.addWidget(self.bridge_box);self.bridge_box.hide()
        note=qt.QLabel('輪切りの設定はCtrl＋左ドラッグにも反映します。\n境界のEPを選択（1点：境界全体／複数：選択範囲）。\nブリッジはA・Bを順に登録してプレビュー。\n中クリックで確定。Qまたは閉じるでキャンセル。')
        note.setWordWrap(True);layout.addWidget(note)
        for label,cb in [('プレビュー',self.build),('確定',self.commit),('キャンセル',self.cancel)]:
            button=qt.QPushButton(label);button.clicked.connect(lambda checked=False,f=cb:self.run(f));layout.addWidget(button)
        self.status=qt.QLabel('プレビューは確定するまでガイド・面を変更しません。');self.status.setWordWrap(True);layout.addWidget(self.status)
        for spin in (self.count,self.phase,self.offset,self.distance):spin.valueChanged.connect(self.changed)
        self.axis.currentIndexChanged.connect(self.changed);self.mode.currentIndexChanged.connect(self.changed);self.faces.toggled.connect(self.changed)
        self.shift.valueChanged.connect(self.changed);self.reverse.toggled.connect(self.changed)
        self.timer=qt.QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.check_context)
        qt.QApplication.instance().installEventFilter(self)

    def run(self,fn):
        try:fn()
        except Exception as exc:
            self.clear();self.status.setText(str(exc));cmds.warning('[Aru Retopo] '+str(exc))

    def changed(self,*args):
        self.bridge_box.setVisible(self.mode.currentIndex()==2)
        for widget in (self.axis,self.count,self.phase,self.offset,self.distance):
            visible=self.mode.currentIndex()!=2 and (widget not in (self.count,self.phase,self.offset) or self.mode.currentIndex()==0) and (widget!=self.distance or self.mode.currentIndex()==1)
            widget.setVisible(visible)
            label=self.form.labelForField(widget)
            if label:label.setVisible(visible)
        cmds.optionVar(iv=('aruRetopoRingCount',self.count.value()))
        cmds.optionVar(fv=('aruRetopoRingPhase',self.phase.value()))
        cmds.optionVar(fv=('aruRetopoRingOffset',self.offset.value()))
        if self.pending or self._preview_requested:self.run(self.build)

    def capture_boundary(self,name):
        guide=(cmds.listConnections(self.node+'.guideData',s=True,d=False,shapes=True) or [None])[0]
        cn,_=_world_data(guide);mesh=edit.RetopoGuideAccessor(guide).mesh_name
        _,requested=edit.get_selected_cv_indices(guide)
        if not requested:
            from .editor.curvenet.aru_retopo_guide_plugin import _ctx
            requested=[] if _ctx.sel_ep is None else [_ctx.sel_ep]
        fn,_=edit._get_mesh_fn(mesh)
        edges=boundary_edges(cn,requested,patch_context.selected(self.node),lambda p:edit._get_normal_at_point(fn,p))
        self.cancel()
        self.boundaries[name]=(guide,tuple(tuple(s) for s in cn.splines),edges)
        vertices,closed=chain_vertices(edges)
        self.boundary_labels[name].setText('{}：{}点 {}'.format(name,len(vertices),'リング' if closed else '開いた列'))
        if len(self.boundaries)==2:self.align()

    def get_boundaries(self,cn,guide):
        if len(self.boundaries)!=2:raise ValueError('境界AとBを登録してください。')
        for g,topology,edges in self.boundaries.values():
            if g!=guide or topology!=tuple(tuple(s) for s in cn.splines):
                raise ValueError('ガイドの接続が変更されています。境界A・Bを登録し直してください。')
        return self.boundaries['A'][2],self.boundaries['B'][2]

    def align(self):
        guide=(cmds.listConnections(self.node+'.guideData',s=True,d=False,shapes=True) or [None])[0]
        cn,_=_world_data(guide);first,second=self.get_boundaries(cn,guide)
        shift,reverse=best_alignment(cn,first,second)
        vertices,closed=chain_vertices(first)
        self.shift.blockSignals(True);self.reverse.blockSignals(True)
        self.shift.setRange(0,len(vertices)-1 if closed else 0);self.shift.setValue(shift);self.reverse.setChecked(reverse)
        self.shift.blockSignals(False);self.reverse.blockSignals(False)
        self.status.setText('対応を合わせました。プレビューして接続を確認してください。')
        if self.pending or self._preview_requested:self.run(self.build)

    def signature(self):
        sel=om.MSelectionList();sel.add(self.mesh)
        fn=om.MFnMesh(sel.getDagPath(0))
        geometry=tuple((p.x,p.y,p.z) for p in fn.getPoints(om.MSpace.kWorld))
        return (cmds.getAttr(self.guide+'.outNetData'),cmds.getAttr(self.guide+'.worldMatrix[0]'),cmds.getAttr(self.node+'.selectedPatches'),geometry)

    def build(self):
        self._preview_requested=True
        self.guide=(cmds.listConnections(self.node+'.guideData',s=True,d=False,shapes=True) or [None])[0]
        cn,matrix=_world_data(self.guide);self.mesh=edit.RetopoGuideAccessor(self.guide).mesh_name
        fn,dag=edit._get_mesh_fn(self.mesh);start=len(cn.splines);old_eps=set(cn.endpoint_indices())
        vector=[0.,0.,0.];vector[self.axis.currentIndex()]=1.
        keys=set()
        if self.mode.currentIndex()==0:
            bb=cmds.exactWorldBoundingBox(self.mesh);center=[(bb[k]+bb[k+3])*.5 for k in range(3)]
            points=context._compute_ring_by_plane(fn,dag,center,vector,self.count.value(),phase=self.phase.value(),offset=self.offset.value())
            if len(points)<3:raise ValueError('この位置には閉じた切断ループがありません。位置や方向を変えてください。')
            context._create_ring_curve(cn,self.mesh,points)
        elif self.mode.currentIndex()==1:
            _,requested=edit.get_selected_cv_indices(self.guide)
            if not requested:
                from .editor.curvenet.aru_retopo_guide_plugin import _ctx
                requested=[] if _ctx.sel_ep is None else [_ctx.sel_ep]
            edges=boundary_edges(cn,requested,patch_context.selected(self.node),lambda p:edit._get_normal_at_point(fn,p))
            keys=extrude(cn,self.mesh,edges,[v*self.distance.value() for v in vector])
        else:
            first,second=self.get_boundaries(cn,self.guide)
            keys=bridge(cn,self.mesh,first,second,self.shift.value(),self.reverse.isChecked())
        self.clear()
        self.pending=(cn,matrix,keys,self.signature())
        lines=[]
        for sp in cn.splines[start:]:
            pts=[core.bezier(cn.positions,sp,k/16.) for k in range(17)]
            for a,b in zip(pts,pts[1:]):lines.extend((a,b))
        triangles=[]
        if keys:
            from .native import Surface,stencil
            sel=om.MSelectionList();sel.add(self.mesh);ref=om.MFnMesh(sel.getDagPath(0))
            _,tri=ref.getTriangles();surface=Surface([(p.x,p.y,p.z) for p in ref.getPoints(om.MSpace.kWorld)],list(tri))
            try:
                plan=core.Plan(cn.positions,cn.splines,lambda p:edit._get_normal_at_point(fn,p),2,selected=keys)
                pts,_=surface.relax(plan.evaluate(cn.positions,cn.splines,stencil),plan,iterations=2,guard=False)
                for a,b,c,d in plan.faces:triangles.extend(pts[i] for i in (a,b,c,a,c,d))
            finally:surface.close()
        if cmds.currentCtx()!=NAME:
            self.previous=cmds.currentCtx()
            if patch_context._active:
                try:patch_context._active.stop()
                except RuntimeError:pass
                patch_context._active=None
            if not cmds.draggerContext(NAME,exists=True):cmds.draggerContext(NAME,cursor='crossHair')
            cmds.setToolTo(NAME)
        for overlay in cmds.listConnections(self.node+'.outMesh',s=False,d=True,shapes=True,type='aruRetopoOverlay') or []:
            path=cmds.ls(overlay,long=True)[0];preview_lines[path]=lines
            preview_points[path]=[cn.positions[i] for i in cn.endpoint_indices() if i not in old_eps]
            if triangles:patch_context.preview[path]=triangles
        self.timer.start();cmds.refresh(force=True)
        self.status.setText('プレビュー中：値を変えて調整 → 中クリックで確定')

    def clear(self):
        self.pending=None;preview_lines.clear();preview_points.clear();patch_context.preview.clear();cmds.refresh(force=True)

    def commit(self):
        if not self.pending:return
        cn,matrix,keys,signature=self.pending
        if self.signature()!=signature:raise ValueError('プレビュー後にガイドが変更されました。再プレビューしてください。')
        inv=matrix.inverse()
        for i,p in enumerate(cn.positions):
            q=om.MPoint(*p)*inv;cn.positions[i]=[q.x,q.y,q.z]
        with api.undo_chunk('Aru Retopo: construct guides'):
            edit.RetopoGuideAccessor(self.guide).write(cn)
            if self.faces.isChecked() and keys:
                cmds.setAttr(self.node+'.selectedPatches',json.dumps(sorted(patch_context.selected(self.node)|keys)),type='string')
                cmds.setAttr(self.node+'.rebuildSerial',cmds.getAttr(self.node+'.rebuildSerial')+1)
        self.cancel();self.status.setText('確定しました。Undoで戻せます。')

    def cancel(self):
        self._preview_requested=False
        self.clear();self.timer.stop()
        if cmds.currentCtx()==NAME:
            from . import guides
            guides.edit(self.node)

    def check_context(self):
        if cmds.currentCtx()!=NAME:self._preview_requested=False;self.clear();self.timer.stop()

    def eventFilter(self,obj,event):
        if event.type()==qt.QEvent.MouseButtonRelease and getattr(self,'_eat_release',False) and event.button()==qt.Qt.MiddleButton:
            self._eat_release=False;return True
        if cmds.currentCtx()!=NAME or not self.pending:return False
        if event.type()==qt.QEvent.MouseButtonPress and event.button()==qt.Qt.MiddleButton and not event.modifiers()&qt.Qt.AltModifier:
            import maya.api.OpenMayaUI as omui
            widget=qt.wrapInstance(int(omui.M3dView.active3dView().widget()),qt.QWidget)
            if widget.rect().contains(widget.mapFromGlobal(qt.QCursor.pos())):
                self._eat_release=True;self.run(self.commit);return True
        return False

    def closeEvent(self,event):
        self.cancel();qt.QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)


def show(node):
    global _window
    if _window:
        try:_window.close();_window.deleteLater()
        except RuntimeError:pass
    _window=ConstructionWindow(node);return _window.show_and_raise()
