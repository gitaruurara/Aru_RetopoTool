# Owned fromiter draw transfer candidate — not adopted

Replace list(MDoubleArray) followed by numpy.array with numpy.fromiter(count=len(array)), retaining newly owned float64 snapshots and the same coordinate checks. Evaluated only in disposable Maya 2027 PID 38780; callback restored in finally.

500-patch / 46,528-face GUI, 1600x1000, brush (841,688), eight dabs, ABBA:
- existing list conversion: 39.426, 42.166 ms
- fromiter: 40.367, 40.765 ms

All guide/complete mesh hashes identical, nonempty brush, Undo restored. Mean trial median 40.796 vs 40.566 ms, with overlapping range and clear order variation. This does not demonstrate a useful speedup; production remains unchanged.

Fresh draw profile (gui_draw_profile.txt): 18 calls, updateDG 21 ms cumulative, populateGeometry 11 ms, GPU positions 7 ms nested, NumPy array 4 ms nested. The former redundant ndarray conversion cost is already removed. Buffer preview source confirms triangulation only on changed connectivity/vertex count; prior native callback timing is about 1 ms updateDG and 0.05 ms upload. Optimizing Python array conversion alone cannot close the ~23 ms gap to 60 FPS.
