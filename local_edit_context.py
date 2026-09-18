"""Influence painting and Ctrl+MMB loop reduction in the combined editor."""
import json,math
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as omr
from . import qt,density,local_fields,maya_api as api
from .local_edit_runtime import Snapshot,PreviewValue
from .editor.curvenet import brush,curve_net_edit as edit

MODE='aruRetopoPaintInfluence'
TARGET='aruRetopoPaintTarget'
STRENGTH='aruRetopoPaintStrength'
preview={}


def painting():return bool(cmds.optionVar(q=MODE)) if cmds.optionVar(exists=MODE) else False

def set_painting(value):
    """Change interaction mode without leaving a stroke or stale UI behind."""
    cmds.optionVar(iv=(MODE,int(bool(value))))
    from . import patch_context
    tool=patch_context._active
    if tool and not tool.stopped:
        tool.local.close()
        tool.brush.last=None
        tool.brush.update()
        tool._last_hover=None
    app=qt.QApplication.instance()
    if app:
        for widget in app.allWidgets():
            if isinstance(widget,qt.QCheckBox) and widget.objectName()=='AruRetopoInfluenceToggle':
                blocked=widget.blockSignals(True)
                widget.setChecked(bool(value));widget.blockSignals(blocked)
    cmds.refresh(force=True)


def option(name,default):return float(cmds.optionVar(q=name)) if cmds.optionVar(exists=name) else default


def publish(node,values=(),faces=(),weights=(),removed=(),lines=(),message=''):
    view=omui.M3dView.active3dView();groups=[[] for _ in range(8)]
    visible=None
    if faces or removed or lines:
        source=cmds.listConnections(node+'.guideData',s=True,d=False,shapes=True)[0]
        visible=edit.make_visibility_test(edit.RetopoGuideAccessor(source).mesh_name)
    if faces:
        centers=[tuple(sum(values[v][k] for v in face)/4 for k in range(3)) for face in faces]
        mask=visible.many(centers) if visible else [True]*len(faces)
        for face,show in zip(faces,mask):
            if not show:continue
            level=max(0,min(7,round(sum(weights[v] for v in face)/4*7))) if weights else 3
            groups[level].extend(values[face[i]] for i in (0,1,2,0,2,3))
    def visible_lines(points):
        if not points or not visible:return list(points)
        pairs=list(zip(points[::2],points[1::2]))
        centers=[tuple((a[k]+b[k])*.5 for k in range(3)) for a,b in pairs]
        return [p for pair,show in zip(pairs,visible.many(centers)) if show for p in pair]
    removed=visible_lines(removed);lines=visible_lines(lines)
    preview.clear()
    for overlay in cmds.listConnections(api.output_plug(node),s=False,d=True,shapes=True,type='aruRetopoOverlay') or []:
        path=cmds.ls(overlay,long=True)[0]
        preview[path]=(view.getCamera().fullPathName(),groups,list(removed),list(lines),message,view.portHeight())
    cmds.refresh(force=True)


def draw(manager,data):
    camera,groups,removed,lines,message,height=data
    for i,points in enumerate(groups):
        if points:
            t=i/7;manager.setColor(om.MColor((.1+.9*t,.2,1-.85*t,.6)))
            manager.mesh(omr.MUIDrawManager.kTriangles,om.MPointArray(points))
    if lines:
        manager.setColor(om.MColor((.4,1.,.3,1.)));manager.setLineWidth(2.)
        manager.lineList(om.MPointArray(lines),False)
    if removed:
        manager.setColor(om.MColor((1.,.25,.1,1.)));manager.setLineWidth(3.)
        manager.lineList(om.MPointArray(removed),False)
    if message:
        manager.setColor(om.MColor((1.,.85,.3,1.)))
        manager.text2d(om.MPoint(24,height-40,0),message)


class PaintStroke:
    def __init__(self,node):
        self.snapshot=Snapshot(node)
        try:
            self.records,self.positions=self.snapshot.paint_samples()
            if not self.records:raise ValueError('先に面張りするパッチを確定してください。')
            self.preview=PreviewValue(node,'influenceField')
        except BaseException:self.snapshot.close();raise
        self.last=None

    def update(self,x,y,reverse=False):
        if self.preview.closed:return
        if self.last and math.hypot(x-self.last[0],y-self.last[1])<2:return
        self.last=(x,y)
        from .editor.curvenet.maya_screen import radius_candidates
        candidates=radius_candidates(self.positions,x,y,brush.radius())
        if candidates is None:
            screens=edit._world_to_screen_many(self.positions)
            candidates=[(i,math.hypot(p[0]-x,p[1]-y)) for i,p in enumerate(screens) if p and math.hypot(p[0]-x,p[1]-y)<brush.radius()]
        visibility=edit.make_visibility_test(self.snapshot.mesh)
        visible=visibility.many([self.positions[i] for i,d in candidates]) if visibility else [True]*len(candidates)
        target=option(TARGET,1.);target=1-target if reverse else target
        strength=option(STRENGTH,.3);fields=self.snapshot.fields
        stamps={}
        for (i,d),show in zip(candidates,visible):
            if not show:continue
            key,uv=self.records[i];alpha=strength*(1-d/brush.radius())**2
            stamps[(key,uv)]=max(stamps.get((key,uv),0.),alpha)
            mirrored=self.snapshot.mirrored_uv(key,uv)
            if mirrored:stamps[mirrored]=max(stamps.get(mirrored,0.),alpha)
        if not stamps:return
        for (key,uv),alpha in stamps.items():local_fields.paint(fields.setdefault(key,{}),*uv,target,alpha)
        self.preview.write(fields)
        plan,values,weights=self.snapshot.evaluate()
        publish(self.snapshot.node,values,plan.faces,weights,message='追従ウェイト: 青=自由 / 赤=ガイドへ追従 | Shift=逆の値 / Esc=取消')

    def finish(self,commit):
        try:
            if commit:self.preview.commit('Aru Retopo: paint influence')
            else:self.preview.cancel()
        finally:self.snapshot.close();preview.clear();cmds.refresh(force=True)


class DensityStroke:
    def __init__(self,snapshot,seed,key,x):
        self.snapshot=snapshot;self.key=key;self.x=x;self.original=list(snapshot.reductions)
        self.preview=PreviewValue(snapshot.node,'loopReductions')
        self.pending=list(self.original);self.count=None;self.seed=seed
        # Candidate rows follow the initially selected loop direction.
        request=density.describe(snapshot.base,seed,key);self.anchor=request
        uv=snapshot.base.edit_coordinates()[key];a,b=request['edge'];direction=(b[0]-a[0],b[1]-a[1]);length=math.hypot(*direction)
        self.candidates=[];seen=set()
        topology=density.Topology(snapshot.base.faces)
        for e in topology.owners:
            if not all(v in uv for v in e):continue
            p,q=[uv[v] for v in e];d=(q[0]-p[0],q[1]-p[1]);n=math.hypot(*d)
            if n<1e-9 or abs(d[0]*direction[0]+d[1]*direction[1])/(n*length)<.999:continue
            try:
                loop=topology.loop(e)
                if loop in seen:continue
                seen.add(loop)
                topology.dissolve(loop,range(len(snapshot.base.endpoints)))
            except ValueError:continue
            distance=sum(((p[k]+q[k]-a[k]-b[k])*.5)**2 for k in range(2))
            self.candidates.append((distance,density.describe(snapshot.base,e,key)))
        self.candidates.sort(key=lambda item:item[0])

    def set_count(self,count):
        if self.preview.closed or self.count==count:return
        self.count=count;pending=list(self.original);changed=0
        if count>=0:
            for _,request in self.candidates:
                if changed>=count:break
                attempt=density.apply(self.snapshot.base,pending+[request])
                if len(attempt.applied)<=len(getattr(density.apply(self.snapshot.base,pending),'applied',())):continue
                pending.append(request);changed+=1
                mirrored=self.snapshot.mirrored_request(request)
                if mirrored:
                    trial=density.apply(self.snapshot.base,pending+[mirrored])
                    if len(trial.applied)>len(attempt.applied):pending.append(mirrored)
        else:
            coordinates=self.snapshot.base.edit_coordinates()[self.key]
            current=density.apply(self.snapshot.base,pending)
            a,b=self.anchor['edge'];direction=(b[0]-a[0],b[1]-a[1])
            def aligned(edge):
                if not all(v in coordinates for v in edge):return False
                p,q=[coordinates[v] for v in edge];d=(q[0]-p[0],q[1]-p[1])
                length=math.hypot(*d)*math.hypot(*direction)
                return length>1e-12 and abs(d[0]*direction[0]+d[1]*direction[1])/length>.999
            removable=[request for request,loop in getattr(current,'applied',[]) if any(aligned(e) for e in loop)]
            for request in reversed(removable[:abs(count)]):
                if request in pending:pending.remove(request);changed-=1
                mirrored=self.snapshot.mirrored_request(request)
                if mirrored in pending:pending.remove(mirrored)
        self.pending=pending;self.preview.write(pending)
        plan,values,weights=self.snapshot.evaluate(pending)
        # The real locator shows the tentative topology; expose every new edge.
        lines=[values[v] for e in density.Topology(plan.faces).owners for v in e]
        base_values=self.snapshot.base.evaluate(self.snapshot.cn.positions,self.snapshot.cn.splines)
        removed=[base_values[v] for request,loop in getattr(plan,'applied',[]) if request not in self.original for e in loop for v in e]
        publish(self.snapshot.node,values,plan.faces,(),removed,lines,
                'ループ削減 {} | 左:間引き / 右:復元 / 離す:確定 / Esc:取消'.format(changed))

    def update(self,x,y,reverse=False):self.set_count(int((self.x-x)/28))

    def finish(self,commit):
        try:
            if commit:self.preview.commit('Aru Retopo: reduce loops')
            else:self.preview.cancel()
        finally:self.snapshot.close();preview.clear();cmds.refresh(force=True)


class Interaction:
    def __init__(self,tool):
        self.tool=tool;self.stroke=None;self.button=None;self.snapshot=None;self.signature=None;self.seed=None;self.reason=None;self.menu=None

    def close_menu(self):
        menu=self.menu
        if menu is None:return
        self.menu=None
        menu.aboutToHide.disconnect(self.menu_hidden)
        menu.close();menu.deleteLater()
        if not self.tool.stopped:self.tool.timer.start()

    def menu_hidden(self):
        menu=self.menu;self.menu=None
        if menu:menu.deleteLater()
        if not self.tool.stopped:self.tool.timer.start()

    def close(self):
        self.close_menu()
        if self.stroke:self.stroke.finish(False);self.stroke=None
        if self.snapshot:self.snapshot.close();self.snapshot=None
        self.signature=None;self.seed=None;self.button=None
        preview.clear()

    def hover(self,x,y,view,force=False):
        if self.stroke or self.menu is not None:return
        self.seed=None;self.reason=None
        if painting():
            guide=cmds.listConnections(self.tool.node+'.guideData',s=True,d=False,shapes=True)[0]
            signature=('paint',cmds.getAttr(guide+'.outNetData'),cmds.getAttr(self.tool.node+'.influenceField'),cmds.getAttr(self.tool.node+'.loopReductions'),cmds.getAttr(self.tool.node+'.selectedPatches'),cmds.getAttr(self.tool.node+'.subdivisions'))
            if signature!=self.signature:
                if self.snapshot:self.snapshot.close()
                self.snapshot=Snapshot(self.tool.node);self.signature=signature
                self.plan,self.positions,self.weights=self.snapshot.evaluate()
                self.view_key=None
            view_key=(tuple(view.modelViewMatrix()),tuple(view.projectionMatrix()))
            if self.view_key!=view_key or not preview:
                publish(self.tool.node,self.positions,self.plan.faces,self.weights,message='追従ウェイト: 青=自由 / 赤=ガイドへ追従 | 左ドラッグで塗る / Escでペイント終了')
                self.view_key=view_key
            return
        if not self.tool.key or (not force and not qt.QApplication.keyboardModifiers() & qt.Qt.ControlModifier):
            if preview:preview.clear();cmds.refresh(force=True)
            return
        from . import drag_extrude,patch_context
        guide,cn,_,_=drag_extrude.selection(self.tool.node);mesh=edit.RetopoGuideAccessor(guide).mesh_name
        if drag_extrude.pick_boundary(cn,mesh,patch_context.selected(self.tool.node),(x,y)):
            publish(self.tool.node,message='境界の押し出し: Ctrl＋中ドラッグ');return
        signature=(cmds.getAttr(guide+'.outNetData'),cmds.getAttr(self.tool.node+'.selectedPatches'),cmds.getAttr(self.tool.node+'.loopReductions'),cmds.getAttr(self.tool.node+'.subdivisions'),self.tool.key if self.tool.key not in patch_context.selected(self.tool.node) else None)
        if signature!=self.signature:
            if self.snapshot:self.snapshot.close()
            self.snapshot=Snapshot(self.tool.node,[self.tool.key]);self.signature=signature
            self.plan,self.positions,_=self.snapshot.evaluate()
            self.topology=density.Topology(self.plan.faces);self.valid_loops=set()
        coords=self.plan.edit_coordinates().get(self.tool.key,{})
        screens=edit._world_to_screen_many(self.positions);topology=self.topology;hits=[]
        for e in topology.owners:
            if not all(v in coords for v in e):continue
            a,b=[screens[v] for v in e]
            if a is None or b is None:continue
            dx=b[0]-a[0];dy=b[1]-a[1];t=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/max(dx*dx+dy*dy,1e-9)))
            distance=(x-a[0]-dx*t)**2+(y-a[1]-dy*t)**2
            hits.append((distance,e))
        if not hits:return
        e=min(hits)[1]
        try:
            loop=topology.loop(e)
            protected=[i for i,v in enumerate(getattr(self.plan,'kept',range(self.plan.count))) if v<len(self.snapshot.base.endpoints)]
            if loop not in self.valid_loops:
                topology.dissolve(loop,protected);self.valid_loops.add(loop)
            self.seed=tuple(self.plan.kept[v] for v in e) if hasattr(self.plan,'kept') else e
            publish(self.tool.node,removed=[self.positions[v] for edge in loop for v in edge],message='ループ削減: Ctrl＋中ドラッグ（左で削減・右で復元）')
        except ValueError as exc:
            self.reason=str(exc);publish(self.tool.node,message='削減できません: '+str(exc))

    def menu_action(self,action):
        try:
            key=getattr(self,'menu_key',self.tool.key)
            if action=='exit_paint':
                set_painting(False);return
            if action=='reset_paint':
                snapshot=Snapshot(self.tool.node,[key])
                try:
                    fields=dict(snapshot.fields);fields.pop(key,None)
                    if key in snapshot.pairs:fields.pop(snapshot.pairs[key][0],None)
                    with api.undo_chunk('Aru Retopo: reset influence'):
                        cmds.setAttr(self.tool.node+'.influenceField',json.dumps(fields),type='string')
                finally:snapshot.close()
            elif action=='restore':
                snapshot=Snapshot(self.tool.node,[key])
                try:
                    plan=density.apply(snapshot.base,snapshot.reductions)
                    uv=snapshot.base.edit_coordinates().get(key,{})
                    discard=[request for request,loop in getattr(plan,'applied',[]) if any(all(v in uv for v in e) for e in loop)]
                    discard.extend(pair for request in list(discard) if (pair:=snapshot.mirrored_request(request)) is not None)
                    pending=[r for r in snapshot.reductions if r not in discard and r.get('patch')!=key]
                    with api.undo_chunk('Aru Retopo: restore loops'):
                        cmds.setAttr(self.tool.node+'.loopReductions',json.dumps(pending),type='string')
                finally:snapshot.close()
            elif self.seed is not None and self.snapshot:
                stroke=DensityStroke(self.snapshot,self.seed,self.tool.key,0.)
                self.snapshot=None
                try:
                    if action=='alternate':
                        a,b=stroke.anchor['edge'];direction=(b[0]-a[0],b[1]-a[1])
                        stroke.candidates.sort(key=lambda item:sum(p[0] for p in item[1]['edge'])*direction[1]-sum(p[1] for p in item[1]['edge'])*direction[0])
                        stroke.candidates=stroke.candidates[::2]
                    stroke.set_count(1 if action=='one' else len(stroke.candidates))
                    stroke.finish(True)
                except BaseException:stroke.finish(False);raise
            self.signature=None
        except Exception as exc:cmds.warning('[Aru Retopo] '+str(exc))

    def event(self,event):
        kind=event.type()
        if kind==qt.QEvent.ApplicationDeactivate:
            self.close();self.button=None;return False
        if self.menu is not None:return False
        mouse=self.tool.brush.mouse()
        if self.stroke:
            if kind==qt.QEvent.KeyPress and event.key()==qt.Qt.Key_Escape:
                self.stroke.finish(False);self.stroke=None;return True
            if kind==qt.QEvent.MouseMove:
                if mouse:self.stroke.update(mouse[1],mouse[2],bool(event.modifiers() & qt.Qt.ShiftModifier))
                return True
            if kind==qt.QEvent.MouseButtonRelease and event.button()==self.button:
                self.stroke.finish(True);self.stroke=None;self.button=None;self.signature=None;return True
        if kind==qt.QEvent.KeyPress and event.key()==qt.Qt.Key_Escape and painting():
            set_painting(False);return True
        if self.button is not None:
            if kind==qt.QEvent.MouseButtonRelease and event.button()==self.button:self.button=None;return True
            if kind==qt.QEvent.MouseMove:return True
        if kind!=qt.QEvent.MouseButtonPress or mouse is None or event.modifiers() & qt.Qt.AltModifier:return False
        if painting() and event.button()==qt.Qt.LeftButton:
            self.stroke=PaintStroke(self.tool.node);self.button=event.button()
            self.stroke.update(mouse[1],mouse[2],bool(event.modifiers() & qt.Qt.ShiftModifier));return True
        if event.button()==qt.Qt.RightButton and self.tool.key and not self.tool.near_control_point():
            # Determine the nearby loop even when Ctrl is not physically held.
            view=mouse[0]
            self.hover(mouse[1],mouse[2],view,force=True)
            self.menu_key=self.tool.key
            self.tool.timer.stop()
            self.menu=qt.QMenu(qt.getMayaMainWindow())
            self.menu.setObjectName('AruRetopoLocalEditMenu')
            self.menu.aboutToHide.connect(self.menu_hidden)
            for label,action in [('1ループ削減','one'),('同方向を間引く','alternate'),('このパッチを通る削減を解除','restore'),('このパッチの追従ペイントを解除','reset_paint')]:
                item=self.menu.addAction(label)
                item.setEnabled(action in ('restore','reset_paint') or self.seed is not None)
                item.triggered.connect(lambda checked=False,mode=action:self.menu_action(mode))
            if painting():
                self.menu.addSeparator()
                self.menu.addAction('追従ペイントを終了').triggered.connect(lambda:self.menu_action('exit_paint'))
            self.menu.popup(qt.QCursor.pos());return True
        if event.button()==qt.Qt.MiddleButton and event.modifiers() & qt.Qt.ControlModifier:
            self.tool.tick(force=True)
            if self.seed is not None:
                self.stroke=DensityStroke(self.snapshot,self.seed,self.tool.key,mouse[1])
                self.snapshot=None;self.signature=None;self.button=event.button();return True
            if self.reason:cmds.warning(self.reason);return True
        return False
