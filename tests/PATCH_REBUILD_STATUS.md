# Patch rebuild optimization

Plan now expands each patch's UV coordinates using only incident edges/faces,
retaining sorted edge/face insertion order. compile_stencil traces dependencies
backward from final outputs that are not overwritten by Coons interiors, and
accounts for guide overrides at every level. It preserves accumulation order.

patch_locality.py compares all Plan metadata and final CSR coefficients exactly
against the frozen pre-change source in core_before_patch_locality.py.txt: 26
cases, triangles/quads/pentagons/hexagons, levels 1-4, partial selections, dense
500-patch grids, and adjacent quad/pentagon regions. Both 2024/2027 smoke suites
passed. Grid 500 patches level 3: constructor 1151 -> 205 ms, compile 288 -> 173 ms.
This synthetic grid is not the live irregular scene and must not be used as its
speedup claim.

Live dense-scene topology attachment/release: 1239 -> 1084 ms, point median about
28.1 ms, exact final guide hash and Undo/session restoration. Recorded in
gui_stencil_dependencies_point.json. Live Plan methods updated. Remaining release
latency and regular point/relax frame time still fail the 60 FPS editing target.

Boundary coefficient memoization is now local to compile_stencil. Read-only
sample rows are reused for identical (side, t) queries; accumulation order and
coefficients remain unchanged. The same 26-case exact parity suite, 12 core unit
tests, and Maya 2024/2027 smoke suites pass. Alternating seven-run comparison
against the immediately preceding source: synthetic 500-patch level-3 grid
compile median 175.60 -> 150.53 ms. This is only stencil compilation, not whole
interaction latency. See sample_cache_benchmark.py/json. The live user session
was deliberately not reloaded while manual testing was in progress.
