# Screen hull candidate (not enabled by default)

Maya 2027 isolated GUI: 400 perspective/orthographic, camera-rotation and
random/offscreen query cases matched the existing segment search exactly.
Median search time: 1.389 ms -> 0.855 ms.

With GPU preview restored before both whole-point-handler runs:
24.769 ms baseline -> 25.469 ms candidate. Final guide hashes match and
both Undo restorations succeeded. No whole-interaction improvement was
established, so the normal configuration retains the segments DLL.
The earlier unmatched-display comparison is not a valid performance result.

Reports: gui_screen_hull.json and gui_screen_hull_unmatched_display.json.
Candidate is built only for 2027; it is not a supported/default 2024 binary.
