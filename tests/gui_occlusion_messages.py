import os,traceback
from pathlib import Path
import maya.api.OpenMaya as om
from Aru_RetopoTool.tests import gui_occlusion_reopen
ROOT=Path(__file__).resolve().parent
_callback=None

def message(text,kind,*args):
 with (ROOT/'occlusion_maya_messages.txt').open('a',encoding='utf-8') as f:f.write(str(kind)+': '+text+'\n')

def run():
 global _callback
 assert os.getpid()==38780
 _callback=om.MCommandMessage.addCommandOutputCallback(message)
 try:gui_occlusion_reopen.run()
 finally:om.MMessage.removeCallback(_callback);_callback=None
