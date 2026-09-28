from pathlib import Path
p=Path('editor/curvenet/curve_net_draw.py');s=p.read_text(encoding='utf-8')
old='positions=list(zip(values[0::3],values[1::3],values[2::3]))'
assert old in s
s=s.replace('import json as _json','import json as _json\nimport numpy as _np')
s=s.replace(old,'''# Own the draw snapshot once; GPU sampling can view it directly.
                # Avoid rebuilding Python tuples and converting them back to NumPy.
                positions=_np.array(values,dtype=_np.float64).reshape(-1,3)''')
p.write_text(s,encoding='utf-8')
p=Path('tests/gpu_guide_buffers.py');s=p.read_text(encoding='utf-8')
s=s.replace('        for amount in (0.,.1,-.3):','        snapshots=[]\n        for amount in (0.,.1,-.3):')
s=s.replace('            assert override._is_valid','''            assert override._is_valid
            assert isinstance(override._positions,np.ndarray)
            assert override._positions.flags.c_contiguous
            for retained,copy in snapshots:np.testing.assert_array_equal(retained,copy)
            snapshots.append((override._positions,override._positions.copy()))''')
p.write_text(s,encoding='utf-8')
