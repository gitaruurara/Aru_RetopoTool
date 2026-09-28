# Path sample coefficient preparation — not adopted

Candidate caches sample t/u, Bernstein c1/c2, and pow(u,3)/pow(t,3) once per fit before iterative rounds. Reuses precisely the original floating operations. It does not change rounds, sampling, or convergence tolerances. Standard path_fit.cpp remains unchanged.

2027 sphere/cube, reflected nonuniform transforms, empty/1/15/16/500 routes, draft and final: exact route and binding parity passed. Isolated large batches were mixed: untransformed sphere draft 11.84 -> 13.56 ms, transformed sphere final 124.57 -> 118.64 ms, transformed cube draft 13.92 -> 11.38 ms.

500-patch GUI same 1600x1000 viewport/brush841,688 ABBA trial medians: [(4, 36.37929999968037), (8, 37.59089999948628), (8, 37.95670000545215), (4, 37.32709999894723)]. Labels 4=standard compact, 8=basis candidate, both four workers. Mean trial medians: {4: 36.8531999993138, 8: 37.773800002469216}. Exact guide/mesh hashes and Undo restored. Whole-interaction regression, therefore not promoted and no 2024 rollout.

Reproduction: cpp/build_basis_candidate.ps1, tests/run_basis_cases.bat, tests/gui_basis.py. Candidate source copies current projector and includes path_fit_basis_candidate.cpp. A later source revision must regenerate those copies rather than treating this stale trial as a new standard build.
