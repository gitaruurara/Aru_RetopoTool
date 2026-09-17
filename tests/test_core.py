import math
import os
import random
import sys
import unittest
from collections import Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from Aru_RetopoTool.core import Plan
from Aru_RetopoTool.native import Surface, stencil


def network(points, edges):
    positions = list(points); splines = []
    for a, b in edges:
        h1 = tuple((2*points[a][i]+points[b][i])/3 for i in range(3))
        h2 = tuple((points[a][i]+2*points[b][i])/3 for i in range(3))
        splines.append((a, len(positions), len(positions)+1, b)); positions.extend([h1, h2])
    return positions, splines


def polygon(n, height=0):
    points = [(math.cos(2*math.pi*i/n), height, math.sin(2*math.pi*i/n)) for i in range(n)]
    return network(points, [(i, (i+1)%n) for i in range(n)])


class Tests(unittest.TestCase):
    def test_explicit_regions_only_and_stable_selection(self):
        from Aru_RetopoTool.core import patch_key, regions
        p,s = network([(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,1),(2,0,0)],
                      [(0,1),(1,2),(2,3),(3,0),(2,4),(4,5),(5,3)])
        normal = lambda p:(0,1,0)
        keys = [patch_key(loop) for loop in regions(p,s,normal)]
        self.assertEqual(len(keys),2)
        empty = Plan(p,s,normal,selected=set())
        self.assertEqual(empty.count,0)
        plan = Plan(p,s,normal,selected={keys[0]})
        self.assertEqual(plan.region_count,1)
        self.assertEqual(len(plan.faces),16)
        shifted = [(x+1,y,z) for x,y,z in p]
        self.assertEqual(Plan(shifted,s,normal,selected={keys[0]}).region_keys,[keys[0]])
        self.assertEqual(Plan(p,s,normal,selected={'missing'}).count,0)

    def test_wrapping_dome_keeps_large_exterior_open(self):
        from Aru_RetopoTool.core import regions, unit
        n = 12
        points = [(math.sin(a)*math.cos(2*math.pi*i/n), math.cos(a),
                   math.sin(a)*math.sin(2*math.pi*i/n))
                  for a in (.45, 1.1, 1.9) for i in range(n)]
        edges = [(r*n+i,r*n+(i+1)%n) for r in range(3) for i in range(n)]
        edges += [(r*n+i,(r+1)*n+i) for r in range(2) for i in range(n)]
        p,s = network(points, edges)
        loops = regions(p,s,unit)
        self.assertEqual(len(loops), 2*n+1)
        uses = Counter(si for loop in loops for side in loop for si,_ in side)
        self.assertTrue(all(uses[2*n+i] == 1 for i in range(n)))
        self.assertTrue(all(uses[i] == 2 for i in range(n)))

    def test_curved_quad_interior_follows_boundary(self):
        p, s = network([(0,0,0),(0,0,2),(2,0,2),(2,0,0)],
                       [(0,1),(1,2),(2,3),(3,0)])
        # Both opposite sides bow in the same direction: every row should
        # inherit that bend, without compression against the pinned boundary.
        for si in (0,2):
            for h in s[si][1:3]:
                p[h] = (p[h][0]+.6,p[h][1],p[h][2])
        plan = Plan(p,s,lambda _: (0,1,0),3)
        out = plan.evaluate(p,s,stencil)
        for sides, uv in plan.patches:
            for vertex,(u,v) in uv.items():
                self.assertAlmostEqual(out[vertex][0], 2*v+1.8*u*(1-u),places=10)
                self.assertAlmostEqual(out[vertex][2], 2*u,places=10)

    def test_ngons_all_quads_and_euler(self):
        for n in (3, 4, 5, 6, 9):
            p, s = polygon(n)
            plan = Plan(p, s, lambda _: (0, 1, 0), levels=3)
            self.assertEqual(len(plan.faces), n*16)
            edges = Counter(tuple(sorted((a, b))) for f in plan.faces for a, b in zip(f, f[1:]+f[:1]))
            self.assertTrue(all(len(set(f)) == 4 for f in plan.faces))
            self.assertTrue(all(v <= 2 for v in edges.values()))
            self.assertEqual(plan.count-len(edges)+len(plan.faces), 1)
            self.assertTrue(all(abs(sum(w[offsets[i]:offsets[i+1]])-1) < 1e-10
                                for offsets, _, w in plan.steps for i in range(len(offsets)-1)))

    def test_shared_boundary_and_dangling(self):
        p, s = network([(-1,0,-1),(0,0,-1),(1,0,-1),(-1,0,1),(0,0,1),(1,0,1),(0,0,2)],
                       [(0,1),(1,2),(2,5),(5,4),(4,3),(3,0),(1,4),(4,6)])
        plan = Plan(p, s, lambda _: (0,1,0), 2)
        self.assertEqual(plan.region_count, 2)
        self.assertEqual(len(plan.faces), 32)
        self.assertEqual(plan.count, 45)

    def test_open_graph_rejected(self):
        p, s = network([(0,0,0),(1,0,0),(2,0,0)], [(0,1),(1,2)])
        with self.assertRaisesRegex(ValueError, '閉じた'): Plan(p, s, lambda _: (0,1,0))

    def test_native_stencil_parity_and_motion(self):
        p, s = polygon(5)
        plan = Plan(p, s, lambda _: (0,1,0), 3)
        python = plan.evaluate(p, s)
        native = plan.evaluate(p, s, stencil)
        for a, b in zip(python, native):
            for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=12)
        moved = [(x+7, y-3, z+2) for x,y,z in p]
        updated = plan.evaluate(moved, s, stencil)
        for a, b in zip(native, updated):
            for x, y, d in zip(a, b, (7,-3,2)): self.assertAlmostEqual(x+d, y, places=10)

    def test_projection_and_relax(self):
        surface = Surface([(-4,0,-4),(-4,0,4),(4,0,4),(4,0,-4)], [0,1,2,0,2,3])
        p, s = polygon(5, height=2)
        plan = Plan(p, s, lambda _: (0,1,0), 3)
        out, seeds = surface.relax(plan.evaluate(p,s,stencil), plan, iterations=5)
        self.assertTrue(all(abs(v[1]) < 1e-12 for v in out))
        self.assertTrue(all(seed in (0,1) for seed in seeds))
        surface.close()

    def test_projection_guard_components(self):
        surface = Surface([(-2,0,-2),(-2,0,2),(2,0,2),(2,0,-2),
                           (-2,.1,-2),(-2,.1,2),(2,.1,2),(2,.1,-2)], [0,1,2,0,2,3,4,5,6,4,6,7])
        out, seed, _ = surface.project([(0,.01,0)])
        held, _, _ = surface.project([(0,.09,0)], seed, guard=True)
        free, _, _ = surface.project([(0,.09,0)], seed, guard=False)
        self.assertAlmostEqual(held[0][1], 0)
        self.assertAlmostEqual(free[0][1], .1)
        surface.close()

    def test_bvh_matches_brute_triangle_surfaces(self):
        rng = random.Random(33)
        points = [(rng.uniform(-3,3),rng.uniform(-3,3),rng.uniform(-3,3)) for _ in range(60)]
        whole = Surface(points, list(range(60)))
        separate = [Surface(points[i:i+3], [0,1,2]) for i in range(0,60,3)]
        queries = [(rng.uniform(-4,4),rng.uniform(-4,4),rng.uniform(-4,4)) for _ in range(20)]
        got, _, _ = whole.project(queries)
        reference = [s.project(queries)[0] for s in separate]
        for i, q in enumerate(queries):
            expected = min(sum((x-y)**2 for x,y in zip(q,r[i])) for r in reference)
            self.assertAlmostEqual(sum((x-y)**2 for x,y in zip(q,got[i])), expected, places=10)
        whole.close()
        for s in separate: s.close()


if __name__ == '__main__': unittest.main(verbosity=2)
