from pathlib import Path
p=Path('tests/projection_certificates_stroke.py')
s=p.read_text().replace('    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)', '''    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(20,repeat=False)
    print('CERTIFICATE CLEANUP scene clear',flush=True)
    cmds.file(new=True,force=True)
    print('CERTIFICATE CLEANUP uninitialize',flush=True)
    maya.standalone.uninitialize()
    print('CERTIFICATE CLEANUP complete',flush=True)
    faulthandler.cancel_dump_traceback_later()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)''')
p.write_text(s)
