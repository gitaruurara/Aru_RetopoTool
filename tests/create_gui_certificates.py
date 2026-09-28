from pathlib import Path
p=Path('tests/gui_isolated_current.py');s=p.read_text()
s=s.replace("STATUS=ROOT/'tests/gui_isolated_current_status.json'", "VERSION=os.environ.get('ARU_TEST_BUFFER_VERSION','certificates')\nSTATUS=ROOT/'tests'/('gui_certificates_'+VERSION+'_status.json')")
s=s.replace("        cmds.file('D:/Dropbox", """        binary='aru_retopo_mesh_buffer_'+VERSION+'.mll'
        for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/2027/'+binary):
            cmds.loadPlugin(str(ROOT/plugin),quiet=True)
        from Aru_RetopoTool import viewport_session,native_backend
        viewport_session.BINARY=binary;native_backend.BINARY_NAME=binary
        cmds.file('D:/Dropbox""")
s=s.replace("        panel='modelPanel4'", """        owners=[p for p in cmds.pluginInfo(q=True,listPlugins=True) or [] if 'aruRetopoMeshBuffer' in (cmds.pluginInfo(p,q=True,dependNode=True) or [])]
        assert len(owners)==1,owners
        loaded=cmds.pluginInfo(owners[0],q=True,path=True)
        assert Path(loaded).name==binary,loaded
        panel='modelPanel4'""")
s=s.replace("status('ready',panel=panel,width=view.portWidth(),height=view.portHeight())", "status('ready',loaded_plugin=loaded,panel=panel,width=view.portWidth(),height=view.portHeight())")
s=s.replace("ROOT/'tests/gui_isolated_current_relax.json'", "ROOT/'tests'/('gui_certificates_'+VERSION+'_relax.json')")
s=s.replace("ROOT/'tests/gui_isolated_current_point.json'", "ROOT/'tests'/('gui_certificates_'+VERSION+'_point.json')")
Path('tests/gui_certificates.py').write_text(s)
s=Path('tests/run_gui_isolated_current.bat').read_text().replace('gui_isolated_current','gui_certificates').replace('50017','50018')
Path('tests/run_gui_certificates.bat').write_text(s)
