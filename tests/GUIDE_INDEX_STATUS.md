# Guide index reuse prototype

Live disposable Maya 2027 PID 48640, 500-patch recovery scene, standard
modelPanel4. Fused junction projector loaded. Current scripted draw-inclusive
point median 28.364 ms, numeric relax 43.907 ms, ordinary relax 66.010 ms.
Both restored via Undo; ordinary/numeric final guide data matched.
See gui_junction_current.json. These are not physical input latency tests.

Temporary class patch in guide_index_candidate.py tests isIndexingDirty and
skips index upload while vertex buffers remain live. Snapshot key includes
position count, topology, sampled curve layout, marker indices, active CV
selection indices, render item names and validity. Same-sized index changes
invalidate. Test always restores original methods afterward.

Paired point drag baseline 27.728 ms vs candidate 27.439 ms. 77 index-dirty
queries, 56 reused responses, 3 populate index uploads. Final guide hashes
match and Undo restores both. GUI reported no exception.

Not promoted: the ~0.29 ms difference is small; selection mode changes,
component snapping, topology edits and pixel parity still need explicit tests.
Allocation checks now reject failed vertex/selection-index acquisition before
marking the upload reusable. Headless state tests pass in Maya 2024 and 2027.

GUI capture probe completed after fixing the test refresh API. Three PNG pairs
were byte-identical, but the EP 646 pair differed. Earlier candidate captures
also remained identical across selection changes. This does not establish
visual parity: investigate stale readColorBuffer frames versus actual index
invalidation before promotion. Topology and snapping still need GUI coverage.
See gui_guide_index_pixels.json. Original class methods and EP selection were
restored after the probe.
Normal guide rendering remains unchanged. The 60 FPS objective is not met.
