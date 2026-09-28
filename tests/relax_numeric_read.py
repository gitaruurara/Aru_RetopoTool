import os,sys,json,traceback
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
status=1
try:
    ref=cmds.polySphere(ch=False)[0];node=guides.create(ref)
    data={'positions':[[0,0,1],[.3,0,1],[.7,0,1],[1,0,1]],'splines':[[0,1,2,3]],'manual_handles':[1],'surface_binding':[[0,[[0,1.]]],None,None,None]}
    cmds.setAttr(node+'.netData',json.dumps(data),type='string')
    for index in range(3):
        cmds.setAttr(node+'.controlPoints[0]',index*.1,.2,0,type='double3')
        parent=cmds.listRelatives(node,parent=True)[0]
        cmds.setAttr(parent+'.translate',index,-index,.1*index,type='double3')
        cmds.setAttr(parent+'.rotateY',index*17)
        expected=json.loads(cmds.getAttr(node+'.outNetData'))
        selection=om.MSelectionList();selection.add(node);matrix=selection.getDagPath(0).inclusiveMatrix()
        expected['positions']=[[q.x,q.y,q.z] for q in (om.MPoint(*p)*matrix for p in expected['positions'])]
        actual,_=relax._world_data(node)
        assert actual.to_dict()==expected,(actual.to_dict(),expected)
        actual.surface_binding[0][1][0][1]=.25
        untouched,_=relax._world_data(node)
        assert untouched.surface_binding[0][1][0][1]==1.,'Shared parse cache mutated'
    # Numeric pair ownership, aliases and legacy binding formats.
    import copy
    pair=[3,.75]; bary=[pair,pair,(5,.25)]
    bindings=[(2,bary),(4,bary),None,(8,.2,.3),(9,{'legacy':[1,2]})]
    copied=relax._copy_surface_bindings(bindings)
    assert copied==copy.deepcopy(bindings)
    assert copied[0][1] is copied[1][1]
    assert copied[0][1][0] is copied[0][1][1]
    copied[0][1][0][1]=.1
    copied[4][1]['legacy'].clear()
    assert pair[1]==.75 and bindings[4][1]['legacy']==[1,2]
    # A numeric CP snapshot must retain the parsed graph without sharing any
    # mutable topology or binding state. Include a standalone EP and a loop.
    from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
    sample=dict(data)
    sample['positions']=data['positions']+[[2,3,4]]
    sample['standalone_eps']=[4]
    sample['splines']=data['splines']+[[3,2,1,3]]
    base=RetopoGuideData.from_dict(sample)
    values=[coordinate+.125 for p in base.positions for coordinate in p]
    clone=relax._evaluated_copy(base,values)
    expected=RetopoGuideData.from_dict(dict(base.to_dict(),positions=clone.positions),lazy_objects=True)
    assert clone.to_dict()==expected.to_dict()
    assert clone.curves==expected.curves
    assert clone._endpoint_type==expected._endpoint_type
    assert clone._endpoint_to_splines==expected._endpoint_to_splines
    assert clone.ep_at(4).position==clone.positions[4]
    original=base.to_json()
    topology=(repr(base.curves),repr(base._endpoint_type),repr(base._endpoint_to_splines))
    clone.positions[0][0]+=1
    clone.surface_binding[0][1][0][1]=.125
    clone.splines.append((0,1,2,3))
    clone.standalone_eps.clear();clone.manual_handles.clear()
    clone.curves[0].append(99)
    clone._endpoint_to_splines[0].append(99)
    clone._endpoint_type[0]='changed'
    assert base.to_json()==original
    assert (repr(base.curves),repr(base._endpoint_type),repr(base._endpoint_to_splines))==topology
    try:relax._evaluated_copy(base,values[:-1])
    except ValueError:pass
    else:raise AssertionError('Wrong evaluated point count accepted')
    print('RELAX EVALUATED TOPOLOGY COPY / LOOP / STANDALONE / MUTABLE OWNERSHIP PASSED')
    from unittest.mock import patch
    graph=relax._evaluated_copy(base,values)
    with patch.object(graph,'_rebuild_curves',wraps=graph._rebuild_curves) as rebuild:
        graph.positions[0][0]+=1
        graph.classify_endpoints()
        assert rebuild.call_count==0
        for change in ('rewire','standalone','point_count'):
            if change=='rewire':graph.splines[0]=(4,1,2,3)
            elif change=='standalone':graph.standalone_eps.add(0)
            else:graph.positions.append([0,0,0]);graph.surface_binding.append(None)
            graph.classify_endpoints()
            fresh=RetopoGuideData.from_dict(graph.to_dict(),lazy_objects=True)
            assert graph._endpoint_to_splines==fresh._endpoint_to_splines
            assert graph._endpoint_type==fresh._endpoint_type
            assert graph.curves==fresh.curves
        assert rebuild.call_count==3
    print('CLASSIFICATION REUSE / REWIRE / STANDALONE / POINT COUNT PASSED')
    import weakref
    def check_wrapper_lifetime(lazy, kind):
        owner=RetopoGuideData.from_dict(data,lazy_objects=lazy)
        if kind=='ep':
            held=owner.ep_at(0)
            assert held is owner.ep_at(0)
            assert held.neighbors[0] is owner.ep_at(3)
        else:
            held=owner.handle_at(1,0)
            assert held is owner.handle_at(1,0)
            assert held.partner is owner.handle_at(2,0)
        ref=weakref.ref(owner)
        del owner
        assert ref() is not None and held.position
        del held
        assert ref() is None,'Wrapper ownership still creates a cycle'
    for lazy in (False,True):
        for kind in ('ep','handle'):check_wrapper_lifetime(lazy,kind)
        owner=RetopoGuideData.from_dict(data,lazy_objects=lazy)
        objects=owner.eps+owner.handles
        ref=weakref.ref(owner)
        del owner,objects
        assert ref() is None,'List accessor retains owner after its caller releases it'
    print('EAGER / LAZY WRAPPER IDENTITY / EXTERNAL OWNER / IMMEDIATE RELEASE PASSED')
    import weakref
    cache=RetopoGuideData._PARSE_CACHE
    saved_cache=dict(cache)
    try:
        cache.clear()
        cached=RetopoGuideData.from_json_cached(json.dumps(sample))
        assert cached._objects_dirty and not cached._eps and not cached._handles
        eager=RetopoGuideData.from_dict(sample)
        assert cached.ep_indices==eager.ep_indices
        assert cached.handle_indices==eager.handle_indices
        assert cached._objects_dirty and not cached._eps and not cached._handles
        assert cached.to_dict()==eager.to_dict()
        cached_ref=weakref.ref(cached)
        del cached
        for index in range(RetopoGuideData._PARSE_CACHE_MAX):
            variant=dict(sample,positions=[[float(index+10),0,0]]+sample['positions'][1:])
            RetopoGuideData.from_json_cached(json.dumps(variant))
        assert cached_ref() is None,'Numeric cache eviction needs cycle collection'
        raw=json.dumps(sample)
        cached=RetopoGuideData.from_json_cached(raw)
        endpoint=cached.ep_at(0)
        assert endpoint.position==cached.positions[0]
        cached_ref=weakref.ref(cached)
        del cache[raw];del cached
        assert cached_ref() is not None,'External cached EP lost owner'
        assert endpoint.position==sample['positions'][0]
        print('NUMERIC CACHE EVICTION / LAZY WRAPPER / EXTERNAL OWNER PASSED')
    finally:
        cache.clear();cache.update(saved_cache)
    transient,_=relax._world_data(node)
    assert transient._objects_dirty and not transient._eps and not transient._handles
    ref=weakref.ref(transient)
    del transient
    assert ref() is None,'Numeric snapshot requires cycle collection'
    transient,_=relax._world_data(node)
    endpoint=transient.ep_at(0)
    assert endpoint.position==transient.positions[0]
    assert len(transient.handles_of(0))==2
    transient.classify_endpoints()
    assert transient._objects_dirty
    assert transient.ep_at(0).position==endpoint.position
    ref=weakref.ref(transient)
    del transient
    assert ref() is not None,'External EP lost its data owner'
    print('RELAX LAZY WRAPPERS / IMMEDIATE RELEASE / EXTERNAL EP OWNERSHIP PASSED')
    print('RELAX NUMERIC READ / CP / TRANSFORM / CACHE OWNERSHIP PASSED',cmds.about(version=True))
    status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
