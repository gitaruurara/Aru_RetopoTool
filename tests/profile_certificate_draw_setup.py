from pathlib import Path
p=Path('tests/gui_draw_profile.py');s=p.read_text().replace('def run():','def run(brush_start=(1546,1145)):').replace('gpu_controls=True)','gpu_controls=True,brush_start=brush_start)');p.write_text(s)
p=Path('tests/gui_certificates_repeated.py');s=p.read_text()+'''
def profile():
    assert os.getpid()==38780
    import importlib
    from Aru_RetopoTool.tests import gui_draw_profile
    report=json.loads((ROOT/'tests/gui_certificates_repeated_certificates.json').read_text())
    importlib.reload(gui_draw_profile).run(brush_start=report['brush_start'])
''';p.write_text(s)
