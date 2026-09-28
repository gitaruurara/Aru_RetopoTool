from pathlib import Path
p=Path('tests/gui_certificates_repeated.py');s=p.read_text()
s=s.replace("        report['viewport']=[view.portWidth(),view.portHeight()]", "        report['viewport']=[view.portWidth(),view.portHeight()]\n        report['guide_xray']=cmds.getAttr('aruRetopoGuideShape1.xray')")
s=s.replace("    window.showNormal();window.resize(2200,1400)", """    window.showNormal();window.resize(2200,1400)
    for control in ('AttributeEditor','ChannelBoxLayerEditor'):
        if cmds.workspaceControl(control,exists=True):cmds.workspaceControl(control,e=True,visible=False)
    cmds.setAttr('aruRetopoGuideShape1.xray',True)""")
p.write_text(s)
