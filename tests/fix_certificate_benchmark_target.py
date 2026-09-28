from pathlib import Path
p=Path('tests/gui_numeric_stroke.py');s=p.read_text()
s=s.replace('hide_guides=False):','hide_guides=False, brush_start=(1546,1145)):')
s=s.replace("'modes':{}}", "'modes':{},'brush_start':list(brush_start)}")
s=s.replace('stroke.brush(1546+4*i,1145)','stroke.brush(brush_start[0]+4*i,brush_start[1])').replace('relax.brush_relax(node,1546+4*i,1145)','relax.brush_relax(node,brush_start[0]+4*i,brush_start[1])')
s=s.replace('                    affected.update(ids)','                    assert ids, "No EP affected; invalid benchmark screen path"\n                    affected.update(ids)')
p.write_text(s)
p=Path('tests/gui_point_drag.py');s=p.read_text().replace('def run(numeric=True):','def run(numeric=True, brush_start=(1546,1145)):').replace('relax.brush_weights(node,1546,1145)','relax.brush_weights(node,*brush_start)');p.write_text(s)
p=Path('tests/gui_certificates_repeated.py');s=p.read_text()
s=s.replace('        for i in range(3):','''        from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
        cn,_=relax._world_data('aruRetopoGuideShape1')
        weights=json.loads((ROOT/'tests/relax_benchmark_weights.json').read_text())
        ep=int(max(weights,key=weights.get))
        screen=edit._world_to_screen(cn.positions[ep]);assert screen
        report['anchor_ep']=ep;report['brush_start']=list(screen)
        report['camera']={a:cmds.getAttr('persp.'+a) for a in ('translate','rotate','scale')}
        import hashlib
        report['input_hash']=hashlib.sha256(cmds.getAttr('aruRetopoGuideShape1.outNetData').encode()).hexdigest()
        for i in range(3):''')
s=s.replace('gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True)','gui_numeric_stroke.run(direct_buffer=True,gpu_controls=True,brush_start=screen)')
s=s.replace('gui_point_drag.run(numeric=True)','gui_point_drag.run(numeric=True,brush_start=screen)')
s=s.replace("        assert not report['point'].get('error'),report['point'].get('error')", "        assert not report['point'].get('error'),report['point'].get('error')\n        assert report['point']['changed'] and report['point']['restored']")
s+='''
def prepare(expected_pid=38780,mode='certificates'):
    assert os.getpid()==expected_pid
    from PySide6 import QtWidgets
    window=next(w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName()=='MayaWindow')
    window.showNormal();window.resize(2200,1400)
    cmds.setFocus('modelPanel4')
    cmds.evalDeferred(lambda:run(expected_pid,mode),lowestPriority=True)
'''
p.write_text(s)
