# Native junction branch pairing and tangent blending

Adopted in _smooth_junctions. Normal projector/build name is now
aru_retopo_maya_projector_tangents.dll, built for Maya 2024 and 2027. It retains
route/binding fusion and fused junction length iterations. The additional
numeric kernel chooses opposing branches in the tangent plane and blends
handle directions. It uses no Maya scene APIs or worker callbacks.
The existing Python algorithm remains available for older DLLs. Manual
handle filtering, hard-surface handling and subsequent length fitting retain
their previous paths. API wrapper validates buffer dimensions; the kernel
validates CSR offsets, finite inputs and overflow before publishing output.

Both Maya versions passed 1,014 integrated comparisons against the existing
Python path: valences 1-8, threshold neighbors around -0.3, equal-score pairs,
short/zero branches, zero/tiny normals, zero handles, manual exclusions and
strengths 0/0.6/2. Selected handles and touched splines were identical;
maximum direction difference 5.78e-15. Additional 2024 checks passed empty
inputs, retained array ownership, malformed dimensions/offsets, NaN and
finite overflow rejection, and old-DLL fallback.
Both integrated Maya smoke suites passed (smoke_tangents_2024/2027.log).

500-patch / 200-EP eight-dab standalone prototype comparison had zero guide
and mesh coordinate deviation and restored Undo. Last paired medians 27.377
ms Python / 25.009 ms native including outMesh but excluding drawing/picking.
See junction_directions_stroke_2027.json for all trials, not just that pair.

GUI prototype ABBA: old 41.458 / 41.637 ms, native 41.447 / 41.069 ms.
After integration, standard code with bound-versus-tangents DLL ABBA:
old 41.926 / 43.910 ms, native 40.932 / 40.565 ms. Each trial is a scripted
brush with synchronous GPU redraw; ordinary/numeric exact final guide data
and Undo checks pass. See gui_tangents_integrated.json. This is not a physical
mouse latency measurement and does not establish a guaranteed speedup across
scenes. Diagnostic Maya PID 48640 was left using tangents.dll; artist Maya was
not reloaded. No UI toggle or CUDA installation is required.

60 FPS remains unmet. Next work must reduce the remaining native mesh
projection and guide/data/render costs; this kernel alone cannot meet 16.7 ms.
