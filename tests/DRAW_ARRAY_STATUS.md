# Owned NumPy guide draw snapshot — adopted 2026-09-18

curve_net_draw.updateDG now owns a contiguous float64 NumPy position array
instead of constructing Python coordinate tuples. GPU sampling uses asarray
views of this snapshot, eliminating redundant list-to-array conversions.
Each update allocates its own snapshot; older snapshots remain unchanged.
The outPositions API and all topology/selection behavior remain unchanged.
Legacy JSON fallback remains supported. No GPU buffer lifetime is extended.

Isolated Maya 2027 PID 38780, native certificate solver, xray enabled,
1600x1000 viewport, same 500-patch / 46,528-face scene and EP-645 brush path.
Measured real brush handlers + synchronous redraw, eight dabs per trial,
443 EP affected in the initial dab. Not physical mouse latency.

ABBA trial medians (ms): baseline 45.254, candidate 43.087,
candidate 44.666, baseline 44.017.
Reverse BAAB: candidate 42.149, baseline 43.767,
baseline 44.511, candidate 42.528.
Mean of the four trial medians: baseline 44.387, candidate 43.108 ms.
The distributions overlap; do not promise a fixed 1.28 ms gain on other scenes.
All final guide and complete mesh-coordinate hashes match; Undo restored the
input. Test scripts restore original callback implementations after each run.
Reports: gui_draw_array.json and gui_draw_array_reverse.json.

Production implementation replaces the prototype's dynamic import with a
module import; the numerical conversion is the same. Integration smoke tests
include the real GeometryOverride.updateDG, exact evaluated coordinates,
GPU sample/index parity, same-count topology changes, immutable previously
returned buffers, and newly-added retained draw snapshot ownership assertions.
See smoke_draw_array_2024.log and smoke_draw_array_2027.log.

No new point-drag timing claim. No Maya 2024 GUI FPS claim. No claim of 60 FPS;
this removes a small measured cost, not the remaining whole-frame bottleneck.
