import os,sys,json,time,traceback
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
status=1
try:
    ref=cmds.polySphere(ch=False)[0];node=guides.create(ref)
    cmds.setAttr(node+'.netData',json.dumps({'positions':[[0,0,0]]*4268,'splines':[]}),type='string')
    for index in (0,13,4267):cmds.setAttr(node+'.controlPoints[{}]'.format(index),1.,2.,3.,type='double3')
    cmds.undoInfo(openChunk=True,chunkName="Reset tweaks")
    t=time.perf_counter();edit._reset_control_points(node,4268);elapsed=(time.perf_counter()-t)*1000
    cmds.undoInfo(closeChunk=True)
    for index in (0,13,4267):assert cmds.getAttr(node+'.controlPoints[{}]'.format(index))[0]==(0.,0.,0.)
    cmds.undo()
    for index in (0,13,4267):assert cmds.getAttr(node+'.controlPoints[{}]'.format(index))[0]==(1.,2.,3.)
    cmds.redo()
    for index in (0,13,4267):assert cmds.getAttr(node+'.controlPoints[{}]'.format(index))[0]==(0.,0.,0.)
    cmds.setAttr(node+'.controlPoints[0:4267]',*([1.,2.,3.]*4268),type='double3')
    edit._reset_control_points(node,4268)
    assert all(v==(0.,0.,0.) for v in cmds.getAttr(node+'.controlPoints[0:4267]'))
    cmds.setAttr(node+'.controlPoints[0]',1.,2.,3.,type='double3')
    cmds.setAttr(node+'.controlPoints[1]',4.,5.,6.,type='double3')
    cmds.setAttr(node+'.controlPoints[0].xValue',lock=True)
    edit._reset_control_points(node,2)
    assert cmds.getAttr(node+'.controlPoints[0]')[0]==(1.,2.,3.),'Preserve existing locked-X early exit per point'
    assert cmds.getAttr(node+'.controlPoints[1]')[0]==(0.,0.,0.)
    cmds.setAttr(node+'.controlPoints[0].xValue',lock=False)
    print('BULK CP RESET / UNDO / REDO / LOCK PARITY PASSED',cmds.about(version=True),'4268 CP ms',elapsed)
    status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
