import os,json,traceback
from pathlib import Path
import maya.api.OpenMayaRender as r
ROOT=Path(__file__).resolve().parent

def run():
 assert os.getpid()==38780
 try:
  m=r.MRenderer.getFragmentManager()
  names=m.fragmentList()
  (ROOT/'point_fragments.json').write_text(json.dumps({'names':names,'api':dir(m)}))
  for name in names:
   if 'point' in name.lower():
    (ROOT/('fragment_'+name+'.xml')).write_text(m.getFragmentXML(name) or 'UNAVAILABLE')
 except BaseException:(ROOT/'point_fragments_error.txt').write_text(traceback.format_exc())
