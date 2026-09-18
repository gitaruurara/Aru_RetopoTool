"""Absolute, position-only soft EP movement with fixed stroke weights."""
import maya.api.OpenMaya as om
from . import curve_net_relax as relax, curve_net_edit as edit, curve_net_symmetry as sym
from . import brush, symmetry_constraints


class SoftMove:
    def __init__(self,node,anchor,screen):
        self.node=node;self.anchor=anchor
        self.base,self.matrix=relax._world_data(node)
        self.mesh=edit.RetopoGuideAccessor(node).mesh_name
        self.weights=relax.brush_weights(node,*screen,brush.radius(),_world=(self.base,self.matrix))
        self.weights[anchor]=1.
        self.pairs={}
        if sym.is_enabled():
            from . import curve_net_context as context
            side=sym.plane_coord(self.base.positions[anchor],self.mesh)
            if side and abs(side)>1e-8:
                self.weights={v:w for v,w in self.weights.items() if sym.plane_coord(self.base.positions[v],self.mesh)*side>=-1e-10}
            # A center stroke has one driver per mirrored pair. Preserve the
            # strongest weight so projection never overwrites a pair twice.
            if side is not None and abs(side)<=1e-8:
                for v,w in list(self.weights.items()):
                    if sym.plane_coord(self.base.positions[v],self.mesh)<-1e-8:
                        pair=sym.find_mirror_ep(self.base,self.mesh,v,context._mirror_tol(self.mesh))
                        if pair is not None:
                            self.weights[pair]=max(w,self.weights.get(pair,0.))
                            self.weights.pop(v,None)
            for v in self.weights:
                pair=sym.find_mirror_ep(self.base,self.mesh,v,context._mirror_tol(self.mesh))
                if pair is not None and pair!=v:self.pairs[v]=pair
        self.target=None

    def move(self,target,draft=True):
        from . import curve_net_context as context
        self.target=list(target)
        base=self.base
        cn=relax._evaluated_copy(base,[v for p in base.positions for v in p])
        delta=[target[k]-base.positions[self.anchor][k] for k in range(3)]
        if sym.is_enabled() and abs(sym.plane_coord(base.positions[self.anchor],self.mesh))<1e-8:
            constrained=sym.project_to_plane(target,self.mesh)
            delta=[constrained[k]-base.positions[self.anchor][k] for k in range(3)]
        affected=set(self.weights)|set(self.pairs.values())
        for ep,weight in self.weights.items():
            start=base.positions[ep]
            candidate=[start[k]+delta[k]*weight for k in range(3)]
            side=sym.plane_coord(start,self.mesh) if sym.is_enabled() else None
            if side is not None and abs(side)<1e-8:
                p,face,bary=context._snap_pos_to_plane(self.mesh,candidate)
            else:
                p,face,bary,_=context._apply_symmetry_constraint(self.mesh,candidate,side=side)
            cn.positions[ep]=p;cn.surface_binding[ep]=(face,bary)
            pair=self.pairs.get(ep)
            if pair is not None:
                p,face,bary=context._project_on_mesh(self.mesh,sym.mirror_point(p,self.mesh))
                cn.positions[pair]=p;cn.surface_binding[pair]=(face,bary)
        for a,h,j,b in cn.splines:
            for ep,handle in ((a,h),(b,j)):
                if ep in affected:
                    cn.positions[handle]=[base.positions[handle][k]+cn.positions[ep][k]-base.positions[ep][k] for k in range(3)]
        for ep in sorted(affected):context._recompute_handles_for_ep(cn,ep,self.mesh,draft=draft)
        context._smooth_moved_ep_routes(cn,affected,self.mesh)
        symmetry_constraints.constrain(cn,self.mesh)
        if self.matrix!=om.MMatrix():
            inverse=self.matrix.inverse()
            cn.positions=[list(om.MPoint(*p)*inverse)[:3] for p in cn.positions]
        return cn
