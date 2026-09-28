# Current relax stage findings

500-patch scene, 200 fixed EP weights, eight consecutive dabs with native
outMesh, no viewport or brush picking. Median after two warmup strokes:
world read 2.148 ms; route fit including bindings 4.261 ms (native fit 2.394);
junction smoothing 5.564 ms (length fit 3.798, native point queries 1.597);
all Python/edit work 14.973 ms, plus native mesh output for 29.021 ms total.
Nested timings must not be summed. See relax_stages_current.json and .txt.

A bindings-only Python conversion avoids unused position/normal lists and
matches outputs exactly (transformed sphere/cube, empty, fallback, ownership).
But continuous stroke comparison after explicit pre-stroke GC gave baseline
27.027 ms vs candidate 27.971 ms. Before explicit GC: 27.404 vs 29.694.
This does not establish an interaction improvement. Production is unchanged;
candidate and repeatable checks are retained only under tests/.

No GUI 60 FPS result. Next substantial work should target the complete guide
solver/transfer or guide rendering, rather than another small matrix or list
conversion optimization. The normal GPU display still costs roughly 14 ms
in the earlier GUI capture, on top of the editing and mesh calculation.


Reprofile after fused junction integration (2027, same 200-EP replay): world
read 2.120 ms, route fit including bindings 4.835 ms, junction smoothing
4.395 ms (length fitting 2.450), editing 14.389 ms, total outMesh 27.917 ms.
These include instrumentation and no viewport. Updated relax_stages_current
reports supersede the previous stage numbers above. Snapshot reuse was tested
separately and not adopted; see OWNED_SNAPSHOT_STATUS.md.
