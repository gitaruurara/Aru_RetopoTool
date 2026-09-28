# Two-variable junction inverse: not adopted

A regularized 2x2 Gram inverse reduces the 500-curve matrix operation from
0.584 to 0.160 ms (2027), 0.562 to 0.148 ms (2024). Random unit directions,
parallel/opposite pairs and sphere/cube projected fits differ by <1e-12.
Both Maya smoke suites passed while the candidate was enabled.

However, a 500-patch continuous 200-EP stroke with native mesh output showed
28.399 ms SVD vs 30.375 ms analytic after alternating warmups. Initial paired
runs were order-sensitive; they do not establish a speedup. Guide differences
were <=2.23e-15, mesh positions matched exactly, metadata passed tolerance and
Undo restored the original scene. These timings exclude viewport and picking.

Production remains SVD. Candidate is isolated in junction_inverse_candidate.py.
Reports: junction_inverse_2024/2027.json, junction_stroke_2027.json and
junction_stroke_2027_reverse.json (the latter predates added warmup repeats).
Do not infer GUI FPS improvement from the isolated matrix timings.
