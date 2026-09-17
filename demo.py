"""Add a small non-destructive demo to the current Maya scene."""
import json
import math
import os
from maya import cmds
from . import maya_api as api


def create():
    from .guides import load
    load()
    with api.undo_chunk('Aru Retopo: demo'):
        reference = cmds.polySphere(radius=3, subdivisionsX=64, subdivisionsY=32,
                                    name='retopoDemoReference#')[0]
        guide = cmds.createNode('retopoGuideNode', name='retopoDemoGuideShape#')
        points = [(1.8*math.cos(i*2*math.pi/5), 3.5, 1.8*math.sin(i*2*math.pi/5)) for i in range(5)]
        splines = []
        for a in range(5):
            b = (a+1)%5
            splines.append([a,len(points),len(points)+1,b])
            points.extend([tuple((2*points[a][k]+points[b][k])/3 for k in range(3)),
                           tuple((points[a][k]+2*points[b][k])/3 for k in range(3))])
        cmds.setAttr(guide+'.netData', json.dumps({'positions':points,'splines':splines}), type='string')
        cmds.setAttr(guide+'.meshName', reference, type='string')
        output, generator = api.create(guide, reference, subdivisions=4)
    return {'reference':reference, 'guide':guide, 'output':output, 'generator':generator}
