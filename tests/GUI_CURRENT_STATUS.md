# Latest isolated GUI measurement

Separate Maya 2027 PID 29032, 500-patch saved test scene copy, standard
modelPanel4 at 2941 x 1598. Native numeric pipeline, normal-only projector,
stable-index buffer preview, GPU controls and render group cache. Artist Maya
PID 49428 was not edited/reloaded.

Scripted point handler median 27.339 ms; numeric relax brush + synchronous redraw
42.623 ms. Point EP 645, final guide hash matches earlier runs exactly; both
benchmarks restore the guide via Undo, numeric vs ordinary relax data matches.
60 FPS editing remains unmet. These are handler measurements, not physical mouse
latency. Earlier custom-window run used 4407 x 2063 and is not comparable.

New GUI exposed project PYTHONPATH shadowing Maya 2027 NumPy with an incompatible
shared package. Package startup now imports Maya's ABI-compatible bundled NumPy
when no per-version _deps exists and Maya is loaded; temporary search-path
priority is restored afterward. Fresh-interpreter shadow-package tests pass
2024 and 2027. Standard 2027 smoke passes. Existing loaded NumPy is not replaced.

Reproduction: run_gui_isolated_current.bat loads the test module after startup;
Maya may request permission for test callbacks. No security settings disabled.
