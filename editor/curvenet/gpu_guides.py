"""Experimental curve vertex buffers for the separate GPU guide pass."""
import ctypes
import numpy as np
import maya.api.OpenMaya as om
import maya.api.OpenMayaRender as render

NAMES=('aruRetopoCurveOutline','aruRetopoCurveColor')
GPU_CONTROLS=False  # Opt-in until viewport and interaction checks pass.
CONTROL_PREFIX='aruRetopoControlBuffer'


def sync_topology(owner, cn, *, shared_readonly=False):
    """Keep owned draw metadata across position-only DG updates."""
    # Only parsed-cache callers promise immutability. Mutable editing data must
    # still compare its contents, including same-count connectivity changes.
    if shared_readonly and getattr(owner, '_draw_readonly_source', None) is cn:
        return
    owner._draw_readonly_source = cn if shared_readonly else None
    key = (len(cn.positions), tuple(cn.splines), frozenset(cn.standalone_eps),
           tuple(cn._endpoint_type.items()))
    if getattr(owner, '_draw_topology_key', None) != key:
        owner._splines = key[1]
        owner._ep_set = cn.endpoint_indices()
        handles = set()
        for sp in cn.splines:
            handles.add(sp[1]); handles.add(sp[2])
        owner._handle_set = handles
        owner._ep_types = dict(cn._endpoint_type)
        owner._draw_topology_key = key


def configure(owner, items, enabled):
    style=owner._style
    for index,name in enumerate(NAMES):
        i=items.indexOf(name)
        if i<0:
            if not enabled:continue
            item=render.MRenderItem.create(name,render.MRenderItem.DecorationItem,render.MGeometry.kLines)
            item.setDrawMode(render.MGeometry.kAll)
            item.setSelectionMask(om.MSelectionMask(om.MSelectionMask.kSelectNurbsCurves))
            manager=render.MRenderer.getShaderManager()
            shader=manager.getStockShader(render.MShaderManager.k3dThickLineShader)
            item.setShader(shader);manager.releaseShader(shader)
            items.append(item)
        else:item=items[i]
        shader=item.getShader()
        if shader:
            color=(.025,.055,.07,1.) if index==0 else tuple(style['curve_color'])+(1.,)
            width=style['curve_width']+(2. if index==0 else 0.)
            shader.setParameter('solidColor',color)
            shader.setParameter('lineWidth',(width,width))
        item.setDepthPriority(owner._xray_priority+index)
        item.enable(enabled and owner._is_valid)
    owner._gpu_curve_active=enabled
    configure_controls(owner,items,enabled and GPU_CONTROLS)


def positions(owner):
    from .curve_net_draw import _BEZIER_N
    # Retain validated connectivity and GPU edge indices across point edits.
    key=(len(owner._positions),tuple(map(tuple,owner._splines)),_BEZIER_N)
    if getattr(owner,'_gpu_sample_key',None)!=key:
        valid=[sp for sp in key[1] if all(0<=i<key[0] for i in sp)]
        owner._gpu_sample_controls=np.asarray(valid,dtype=np.intp).reshape(-1,4)
        t=np.linspace(0.,1.,_BEZIER_N+1);u=1.-t
        owner._gpu_sample_basis=np.stack((u**3,3*u*u*t,3*u*t*t,t**3),axis=1)
        steps=_BEZIER_N+1
        starts=np.arange(len(valid),dtype=np.uint32)[:,None]*steps+np.arange(steps-1,dtype=np.uint32)
        owner._gpu_curve_indices=np.stack((starts,starts+1),axis=-1).ravel()+key[0]
        owner._gpu_sample_key=key
        owner._gpu_previous_controls=None
    controls=np.asarray(owner._positions,dtype=np.float64).reshape(-1,3)
    if not len(owner._gpu_sample_controls):return np.ascontiguousarray(controls,dtype=np.float32)
    previous=getattr(owner,'_gpu_previous_controls',None)
    if previous is None:
        dirty=np.ones(len(owner._gpu_sample_controls),dtype=bool)
        owner._gpu_curve_samples=np.empty((len(dirty),_BEZIER_N+1,3),dtype=np.float32)
    else:
        changed=np.any(controls!=previous,axis=1)
        dirty=np.any(changed[owner._gpu_sample_controls],axis=1)
    owner._gpu_resampled_count=int(np.count_nonzero(dirty))
    if owner._gpu_resampled_count:
        owner._gpu_curve_samples[dirty]=owner._gpu_sample_basis @ controls[owner._gpu_sample_controls[dirty]]
    # Own the snapshot: caller arrays/lists can change in place between draws.
    owner._gpu_previous_controls=controls.copy()
    # Return a fresh array, so previously returned buffers remain immutable.
    return np.concatenate((controls.astype(np.float32),owner._gpu_curve_samples.reshape(-1,3)))



def upload_indices(owner,items,geo):
    groups=[(NAMES,owner._gpu_curve_indices)]
    if getattr(owner,'_gpu_controls_active',False):groups.extend(owner._gpu_control_indices)
    for names,indices in groups:
        if not len(indices):continue
        buffer=geo.createIndexBuffer(render.MGeometry.kUnsignedInt32)
        address=buffer.acquire(len(indices),True)
        if not address:raise RuntimeError('Cannot allocate GPU guide indices')
        ctypes.memmove(address,indices.ctypes.data,indices.nbytes);buffer.commit(address)
        for name in names:
            index=items.indexOf(name)
            if index>=0:items[index].associateWithIndexBuffer(buffer)


def _control_batches(owner, style):
    """Batch contiguous marker styles without changing overlap/draw order."""
    pos=owner._positions; selected=owner._selected_components
    show=style['show_handles']; lines=[]
    for sp in owner._splines:
        if any(i>=len(pos) for i in sp):continue
        if show or sp[1] in selected:lines.extend((sp[0],sp[1]))
        if show or sp[2] in selected:lines.extend((sp[2],sp[3]))
    batches=[]
    green=(0.,1.,0.,1.); cyan=(0.,.8,1.,1.)
    red=(1.,.2,.2,1.); yellow=(1.,.9,0.,1.)
    warm=(1.,.75,.3,1.); handle=tuple(style['handle_color'])+(1.,)
    previous=None; points=[]
    def emit(key,values):
        batches.append((key,tuple(values)))
    # Two passes retain the original EP-before-handle order, including overlap.
    for handles,indices in ((False,owner._ep_set),(True,owner._handle_set)):
        for index in indices:
            if index>=len(pos):continue
            if handles:
                if not show and index not in selected:continue
                size=style['handle_size']
                if index in selected:key=(green,size*1.35)
                elif index in getattr(owner,'_manual_handles',()):key=(warm,size*1.15)
                else:key=(handle,size)
            else:
                size=style['point_size']
                if index in selected or owner._sel_ep==index:key=(green,size*1.75)
                elif owner._mirror_ep==index:key=(cyan,size*1.75)
                elif owner._ep_types.get(index)=='intersection':key=(red,size*1.25)
                else:key=(yellow,size)
            if previous is not None and key!=previous:
                emit(previous,points);points=[]
            previous=key;points.append(index)
        if points:emit(previous,points);points=[];previous=None
    return tuple(lines),tuple(batches)


def cached_controls(owner, style):
    """Cache marker classification; positions are read fresh for every draw."""
    key=(len(owner._positions),tuple(map(tuple,owner._splines)),
         tuple(owner._ep_set),tuple(owner._handle_set),frozenset(owner._selected_components),
         owner._sel_ep,owner._mirror_ep,tuple(owner._ep_types.items()),
         frozenset(getattr(owner,'_manual_handles',())),style['show_handles'],
         style['point_size'],style['handle_size'],tuple(style['handle_color']))
    if getattr(owner,'_gpu_control_key',None)!=key:
        owner._gpu_control_batches=_control_batches(owner,style)
        owner._gpu_control_key=key
    return owner._gpu_control_batches


def draw_controls(owner, manager, style):
    if getattr(owner,'_gpu_controls_active',False):return
    lines,batches=cached_controls(owner,style);pos=owner._positions
    manager.setColor(om.MColor((.55,.55,.55,.7)))
    manager.setLineWidth(1.);manager.outline=False
    if lines:manager.manager.lineList(om.MPointArray([pos[i] for i in lines]),False)
    for (color,size),indices in batches:
        manager.setColor(om.MColor(color));manager.setPointSize(size)
        manager.manager.points(om.MPointArray([pos[i] for i in indices]),False)


def render_control_groups(owner, style):
    """Reuse immutable index arrays while only control positions change."""
    batches=cached_controls(owner,style)
    if getattr(owner,'_gpu_render_group_source',None) is batches:
        return owner._gpu_render_groups
    lines,markers=batches
    groups=[(render.MGeometry.kLines,(.55,.55,.55,.7),1.,lines)]
    by_style={}
    for key,indices in markers:by_style.setdefault(key,[]).extend(indices)
    for (color,size),indices in sorted(by_style.items(),key=lambda pair:pair[0][0]==(0.,1.,0.,1.)):
        groups.append((render.MGeometry.kPoints,color,size,indices))
    result=[]
    for primitive,color,size,indices in groups:
        array=np.asarray(indices,dtype=np.uint32)
        array.flags.writeable=False
        result.append((primitive,color,size,array))
    owner._gpu_render_groups=tuple(result)
    owner._gpu_render_group_source=batches
    return owner._gpu_render_groups


def configure_controls(owner,items,enabled):
    """Point/tangent render items reference the shared control-vertex prefix."""
    active=enabled and owner._is_valid
    groups=render_control_groups(owner,owner._style) if active else ()
    indices_out=[]
    for number,(primitive,color,size,indices) in enumerate(groups):
        name=CONTROL_PREFIX+str(number);index=items.indexOf(name)
        if index<0:
            item=render.MRenderItem.create(name,render.MRenderItem.DecorationItem,primitive)
            item.setDrawMode(render.MGeometry.kAll)
            # Decorations cannot become vertex component hits; the existing
            # dedicated CV selection item retains that responsibility.
            item.setSelectionMask(om.MSelectionMask(om.MSelectionMask.kSelectNurbsCurves))
            manager=render.MRenderer.getShaderManager()
            kind=render.MShaderManager.k3dFatPointShader if primitive==render.MGeometry.kPoints else render.MShaderManager.k3dSolidShader
            shader=manager.getStockShader(kind)
            item.setShader(shader);manager.releaseShader(shader);items.append(item)
        else:item=items[index]
        shader=item.getShader();shader.setParameter('solidColor',color)
        if primitive==render.MGeometry.kPoints:shader.setParameter('pointSize',[float(size)])
        item.setDepthPriority(owner._xray_priority+2+number)
        item.enable(bool(len(indices)))
        indices_out.append(((name,),indices))
    for index in range(len(items)):
        item=items[index];name=item.name()
        if name.startswith(CONTROL_PREFIX) and int(name[len(CONTROL_PREFIX):])>=len(groups):item.enable(False)
    owner._gpu_control_indices=indices_out
    owner._gpu_controls_active=active
