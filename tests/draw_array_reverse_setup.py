from pathlib import Path
p=Path('tests/gui_draw_array.py');s=p.read_text().replace('def run():',"def run(reverse=False):").replace("for mode in ('baseline','candidate','candidate','baseline'):","for mode in (('candidate','baseline','baseline','candidate') if reverse else ('baseline','candidate','candidate','baseline')):")
s=s.replace("        (ROOT/'tests/gui_draw_array.json').write_text(json.dumps(report,indent=2))", "        (ROOT/'tests'/('gui_draw_array_reverse.json' if reverse else 'gui_draw_array.json')).write_text(json.dumps(report,indent=2))")
p.write_text(s)
