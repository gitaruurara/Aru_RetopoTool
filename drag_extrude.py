"""Ctrl+MMB surface extrusion inside the combined editing context."""
import json
import time
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from . import qt,construction as c,patch_context,core,maya_api as api
from .editor.curvenet import curve_net_edit as edit,curve_net_context as context
from .editor.curvenet.curve_net_relax import _world_data
from .editor.curvenet.curve_net_data import RetopoGuideData
from .editor.curvenet.aru_retopo_guide_plugin import _ctx

selected_points={}
selected_lines={}


def mouse():
    view=omui.M3dView.active3dView();widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
    p=widget.mapFromGlobal(qt.QCursor.pos());scale=view.portWidth()/max(1,widget.width())
    if not widget.rect().contains(p):return None
    return p.x()*scale,(widget.height()-p.y()-1)*scale


def overlays(node):
    return [cmds.ls(s,long=True)[0] for s in cmds.listConnections(node+'.outMesh',s=False,d=True,shapes=True,type='aruRetopoOverlay') or []]


def selection(node):
    guide=cmds.listConnections(node+'.guideData',s=True,d=False,shapes=True)[0]
    cn,matrix=_world_data(guide)
    _,eps=edit.get_selected_cv_indices(guide)
    eps=set(eps)&set(cn.endpoint_indices())
    if not eps and _ctx.sel_ep in cn.endpoint_indices():eps={_ctx.sel_ep}
    return guide,cn,matrix,eps


def highlight(node,points=None):
    if points is None:
        _,cn,_,eps=selection(node);points=[cn.positions[i] for i in eps]
    selected_points.clear()
    for path in overlays(node):selected_points[path]=points


def pick_boundary(cn,mesh,keys,xy):
    """Pick displayed boundary curves, then expand their whole unbranched chain."""
    from collections import Counter
    fn,_=edit._get_mesh_fn(mesh)
    normal=lambda p:edit._get_normal_at_point(fn,p)
    owners=Counter()
    try: loops=core.regions(cn.positions,cn.splines,normal)
    except ValueError: loops=[]
    for loop in loops:
        if not keys or core.patch_key(loop) in keys:
            owners.update(si for side in loop for si,_ in side)
    boundary={si for si in range(len(cn.splines)) if owners[si]==1}
    # Unfilled standalone curves remain extrudable too.
    attached={v for si in boundary for v in (cn.splines[si][0],cn.splines[si][3])}
    boundary.update(si for si,sp in enumerate(cn.splines) if owners[si]==0 and not ({sp[0],sp[3]} & attached))
    hits=[]
    for si in sorted(boundary):
        sp=cn.splines[si]
        pts=[core.bezier(cn.positions,sp,k/32.) for k in range(33)]
        screen=[edit._world_to_screen(p) for p in pts]
        for k,(a,b) in enumerate(zip(screen,screen[1:])):
            if a is None or b is None:continue
            dx,dy=b[0]-a[0],b[1]-a[1]
            t=max(0.,min(1.,((xy[0]-a[0])*dx+(xy[1]-a[1])*dy)/max(dx*dx+dy*dy,1e-12)))
            dist=(xy[0]-a[0]-t*dx)**2+(xy[1]-a[1]-t*dy)**2
            if dist<18**2:
                anchor=[pts[k][j]*(1-t)+pts[k+1][j]*t for j in range(3)]
                hits.append((dist,si,anchor))
    if not hits:return None
    _,si,anchor=min(hits,key=lambda h:h[:2])
    mapping=sorted(boundary)
    subset=RetopoGuideData.from_dict(cn.to_dict());subset.splines=[cn.splines[i] for i in mapping]
    edges=c.boundary_edges(subset,{cn.splines[si][0]},set(),normal)
    return [(a,b,mapping[i]) for a,b,i in edges],anchor


def show_boundary(node,cn,edges):
    lines=[]
    for _,_,si in edges:
        pts=[core.bezier(cn.positions,cn.splines[si],k/24.) for k in range(25)]
        for a,b in zip(pts,pts[1:]):lines.extend((a,b))
    selected_lines.clear()
    for path in overlays(node):selected_lines[path]=lines


def hover_boundary(node):
    selected_lines.clear()
    if not qt.QApplication.keyboardModifiers() & qt.Qt.ControlModifier:return
    xy=mouse()
    if xy is None:return
    guide,cn,_,_=selection(node)
    try: picked=pick_boundary(cn,edit.RetopoGuideAccessor(guide).mesh_name,patch_context.selected(node),xy)
    except ValueError:return
    if picked:show_boundary(node,cn,picked[0])


class Gesture:
    def __init__(self,node):
        self.node=node;self.pending=None;self.last=0.;self.moved=False
        self.guide,self.cn,self.matrix,selected=selection(node)
        xy=mouse()
        if xy is None:raise ValueError('ビューポートの境界EP上でCtrl＋中ドラッグしてください。')
        self.origin=xy
        self.mesh=edit.RetopoGuideAccessor(self.guide).mesh_name
        picked=pick_boundary(self.cn,self.mesh,patch_context.selected(node),xy)
        if picked is None:raise ValueError('境界カーブにカーソルを合わせてCtrl＋中ドラッグしてください。')
        self.edges,self.anchor=picked
        ep=self.edges[0][0]
        self.start=context._screen_to_view_plane(*xy,self.anchor)
        if self.start is None:raise ValueError('ドラッグの開始位置を取得できません。')
        self.signature=(cmds.getAttr(self.guide+'.outNetData'),cmds.getAttr(node+'.selectedPatches'),cmds.getAttr(self.guide+'.worldMatrix[0]'))
        _ctx.sel_ep=ep
        self.source_points=[self.cn.positions[v] for v in sorted({v for a,b,_ in self.edges for v in (a,b)})]
        highlight(node,self.source_points)
        show_boundary(node,self.cn,self.edges)
        cmds.inViewMessage(amg='押し出し：ドラッグして離すと確定 / Escでキャンセル',pos='topCenter',fade=True)

    def update(self,force=False):
        xy=mouse()
        if xy is None or (xy[0]-self.origin[0])**2+(xy[1]-self.origin[1])**2<16:
            self.reset_preview(); return
        if not force and time.monotonic()-self.last<.07:return
        self.last=time.monotonic();self.moved=True;self.pending=None
        p=context._screen_to_view_plane(*xy,self.anchor)
        if p is None:return
        cn=RetopoGuideData.from_dict(self.cn.to_dict())
        keys=c.extrude(cn,self.mesh,self.edges,[p[k]-self.start[k] for k in range(3)])
        lines=[]
        for sp in cn.splines[len(self.cn.splines):]:
            points=[core.bezier(cn.positions,sp,k/12.) for k in range(13)]
            for a,b in zip(points,points[1:]):lines.extend((a,b))
        for path in overlays(self.node):
            c.preview_lines[path]=lines
            c.preview_points[path]=[cn.positions[v] for v in cn.endpoint_indices() if v not in self.cn.endpoint_indices()]
        self.pending=(cn,keys);highlight(self.node,self.source_points);cmds.refresh(force=True)

    def finish(self):
        self.update(force=True)
        if not self.pending:return
        signature=(cmds.getAttr(self.guide+'.outNetData'),cmds.getAttr(self.node+'.selectedPatches'),cmds.getAttr(self.guide+'.worldMatrix[0]'))
        if signature!=self.signature:raise ValueError('ガイドが変更されたため押し出しを中止しました。')
        cn,keys=self.pending;inverse=self.matrix.inverse()
        new_eps=set(cn.endpoint_indices())-set(self.cn.endpoint_indices())
        for i,p in enumerate(cn.positions):
            q=om.MPoint(*p)*inverse;cn.positions[i]=[q.x,q.y,q.z]
        faces=bool(cmds.optionVar(q='aruRetopoDragExtrudeFaces')) if cmds.optionVar(exists='aruRetopoDragExtrudeFaces') else True
        with api.undo_chunk('Aru Retopo: drag extrude'):
            edit.RetopoGuideAccessor(self.guide).write(cn)
            if faces:
                cmds.setAttr(self.node+'.selectedPatches',json.dumps(sorted(patch_context.selected(self.node)|keys)),type='string')
                cmds.setAttr(self.node+'.rebuildSerial',cmds.getAttr(self.node+'.rebuildSerial')+1)
            cmds.select([self.guide+'.vtx[%d]'%i for i in sorted(new_eps)],replace=True)
        _ctx.sel_ep=min(new_eps) if new_eps else None

    def reset_preview(self):
        c.preview_lines.clear();c.preview_points.clear();self.pending=None
        cmds.refresh(force=True)

    def clear(self):
        self.reset_preview()
        selected_lines.clear()
        if cmds.objExists(self.node): highlight(self.node)
        cmds.refresh(force=True)
