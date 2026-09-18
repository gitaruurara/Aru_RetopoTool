"""Shared brush settings and screen-space drag connection tolerance."""
from maya import cmds
RADIUS='aruRetopoBrushRadius'
SOFT='aruRetopoSoftMove'
MERGE='aruRetopoAutoConnect'
SNAP='aruRetopoConnectPixels'


def radius():return float(cmds.optionVar(q=RADIUS)) if cmds.optionVar(exists=RADIUS) else 80.
def set_radius(value):
    value=max(4.,min(1000.,float(value)))
    cmds.optionVar(fv=(RADIUS,value));return value

def soft():return bool(cmds.optionVar(q=SOFT)) if cmds.optionVar(exists=SOFT) else False
def auto_connect():return bool(cmds.optionVar(q=MERGE)) if cmds.optionVar(exists=MERGE) else False
def snap_radius():return float(cmds.optionVar(q=SNAP)) if cmds.optionVar(exists=SNAP) else 12.


def endpoint_target(cn,mesh,sx,sy,exclude):
    from . import curve_net_edit as edit
    visible=edit.make_visibility_test(mesh)
    candidates=[];limit=snap_radius()**2
    for ep in cn.endpoint_indices():
        if ep in exclude:continue
        screen=edit._world_to_screen(cn.positions[ep])
        if screen is None:continue
        distance=(screen[0]-sx)**2+(screen[1]-sy)**2
        if distance<limit and (visible is None or visible(cn.positions[ep])):
            candidates.append((distance,ep))
    return min(candidates)[1] if candidates else None
