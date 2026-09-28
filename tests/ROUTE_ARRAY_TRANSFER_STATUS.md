# Route array transfer experiment (not adopted)

Avoided native route output list -> NumPy conversion before surface metadata
projection. Exact coordinates, surface bindings and manual handles matched
for 400 curves; empty and degenerate cases passed. Separate mayapy processes;
no changes to the interactive artist session.

2027 median: baseline 6.105 ms, candidate 6.461 ms.
2024 median: baseline 6.122 ms, candidate 6.568 ms.
No speedup established, so both production functions were restored. Candidate
sources remain beside route_array_transfer.py for reproducibility. These are
route-stage timings, not frame times. Goal remains unmet.
