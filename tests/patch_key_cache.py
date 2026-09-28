"""Boundary key parity across rotations, grouping, mutable inputs and eviction."""
import json,random
from Aru_RetopoTool import core

def run():
    rng=random.Random(716)
    def legacy(loop):
        walk=tuple(h for side in loop for h in side)
        canonical=min(walk[i:]+walk[:i] for i in range(len(walk)))
        return json.dumps(canonical,separators=(',',':'))
    core._patch_key_for_walk.cache_clear()
    for n in range(1,25):
        walk=[(rng.randrange(12),rng.choice((-1,1))) for _ in range(n)]
        for shift in range(n):
            rotated=walk[shift:]+walk[:shift]
            loop=[rotated[:n//2],rotated[n//2:]]
            assert core.patch_key(loop)==legacy(loop)==legacy([walk])
            mutable=[[list(p) for p in side] for side in loop]
            assert core.patch_key(mutable)==legacy(mutable)
            mutable[-1][-1][0]+=1
            assert core.patch_key(mutable)==legacy(mutable)
    try:core.patch_key([])
    except ValueError:pass
    else:raise AssertionError('Empty boundary must remain invalid')
    for i in range(4200):core.patch_key([[(i,1)]])
    assert core._patch_key_for_walk.cache_info().currsize==4096
    print('PASS patch key identity, mutable inputs, rotations, bounded cache')
