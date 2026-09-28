import os,sys,ctypes,traceback,copy
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMayaRender as render
from Aru_RetopoTool.tests import guide_index_candidate as candidate
from Aru_RetopoTool.editor.curvenet import curve_net_draw as draw
from types import SimpleNamespace as Obj
import numpy as np
status=1;restore=None
try:
    owner=Obj(_positions=[(0,0,0),(1,0,0)],_draw_topology_key=(2,((0,0,1,1),)),
              _gpu_curve_active=False,_gpu_control_indices=[(('markers',),np.array([0,1],dtype=np.uint32))],
              _active_indices=[0,1],_is_valid=True)
    base=candidate.index_key(owner,('selection',))
    owner._positions[0]=(3,4,5);assert candidate.index_key(owner,('selection',))==base
    for field,value in [('_positions',[(0,0,0)]),('_draw_topology_key',(2,((1,0,1,0),))),
                        ('_active_indices',[1]),('_is_valid',False),('_gpu_curve_active',True)]:
        changed=copy.deepcopy(owner);setattr(changed,field,value)
        assert candidate.index_key(changed,('selection',))!=base,field
    changed=copy.deepcopy(owner);changed._gpu_control_indices[0][1][:]=[1,0]
    assert candidate.index_key(changed,('selection',))!=base
    assert candidate.index_key(owner,('recreated',))!=base
    class Buffer:
        def __init__(self,fail):self.fail=fail
        def acquire(self,count,write):
            self.data=(ctypes.c_float*(count*3))()
            return 0 if self.fail else ctypes.addressof(self.data)
        def commit(self,address):pass
    class Geometry:
        def __init__(self,vertex=False,index=False):self.vertex=vertex;self.index=index;self.buffers=[];self.indices=0
        def createVertexBuffer(self,desc):
            b=Buffer(self.vertex);self.buffers.append(b);return b
        def createIndexBuffer(self,kind):
            self.indices+=1;b=Buffer(self.index);self.buffers.append(b);return b
    class Item:
        def name(self):return draw._VERTEX_SEL_ITEM
        def associateWithIndexBuffer(self,b):self.buffer=b
    requirements=Obj(vertexRequirements=lambda:[Obj(semantic=render.MGeometry.kPosition)])
    stats,restore=candidate.install();populate=draw.RetopoGuideGeometryOverride.populateGeometry
    for vertex,index in [(True,False),(False,True)]:
        o=copy.deepcopy(owner);o._candidate_index_dirty=True;o._candidate_index_key=base
        try:populate(o,requirements,[Item()],Geometry(vertex,index))
        except RuntimeError:pass
        else:raise AssertionError('Allocation failure ignored')
        assert not hasattr(o,'_candidate_uploaded_key')
    owner._candidate_index_dirty=True;owner._candidate_index_key=base
    geo=Geometry();populate(owner,requirements,[Item()],geo)
    assert owner._candidate_uploaded_key==base and geo.indices==1
    owner._candidate_index_dirty=False;geo=Geometry();populate(owner,requirements,[Item()],geo)
    assert geo.indices==0 and len(geo.buffers)==1
    owner._candidate_index_dirty=True;owner._active_indices=[]
    owner._candidate_index_key=candidate.index_key(owner,('selection',))
    populate(owner,requirements,[Item()],Geometry())
    assert owner._candidate_uploaded_key==owner._candidate_index_key
    print('PASS position reuse, topology/selection/visibility invalidation, allocation failures, vertex streaming and empty selection');status=0
except BaseException:traceback.print_exc()
finally:
    if restore:restore()
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
