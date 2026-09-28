from pathlib import Path
p=Path('tests/gui_numeric_stroke.py');s=p.read_text()
s=s.replace('import json,time,statistics,traceback','import json,time,statistics,traceback,hashlib,struct')
s=s.replace("                outputs[mode]=cmds.getAttr(node+'.netData')", """                outputs[mode]=cmds.getAttr(node+'.netData')
                mesh_values=list(om.MFnDoubleArrayData(plug.asMObject()).array())
                guide_hash=hashlib.sha256(outputs[mode].encode()).hexdigest()
                mesh_hash=hashlib.sha256(struct.pack('='+str(len(mesh_values))+'d',*mesh_values)).hexdigest()""")
s=s.replace("'release_ms':release}", "'release_ms':release,'guide_hash':guide_hash,'mesh_hash':mesh_hash}")
p.write_text(s)
