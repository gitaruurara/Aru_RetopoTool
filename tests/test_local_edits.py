"""Pure topology and persistent field invariants."""
import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from Aru_RetopoTool import core,density,local_fields
from Aru_RetopoTool.native import stencil
from Aru_RetopoTool.tests.test_core import polygon,network


class Tests(unittest.TestCase):
    def test_coordinates_all_patch_types(self):
        for n in (3,4,5,6):
            for level in (1,2,3):
                p,s=polygon(n);plan=core.Plan(p,s,lambda p:(0,1,0),level)
                fields=plan.edit_coordinates();self.assertEqual(len(fields),1)
                coords=next(iter(fields.values()))
                self.assertEqual(set(coords),set(range(plan.count)))
                self.assertTrue(all(-1e-8<=x<=1+1e-8 for uv in coords.values() for x in uv))
                if n==4:self.assertEqual(coords,plan.patches[0][1])

    def test_open_strip_and_compiled_rows(self):
        p,s=polygon(4);plan=core.Plan(p,s,lambda p:(0,1,0),3)
        uv=next(iter(plan.edit_coordinates().values()));topology=density.Topology(plan.faces)
        e=next(e for e in topology.owners if all(abs(uv[v][0]-.5)<1e-8 for v in e))
        loop=topology.loop(e);self.assertEqual(len(loop),8)
        request=density.describe(plan,e);reduced=density.apply(plan,[request])
        self.assertEqual(len(reduced.faces),56);self.assertEqual(reduced.count,72)
        self.assertFalse(reduced.rejected)
        actual=stencil.compile(*reduced.compile_stencil(s))(p)
        expected=reduced.evaluate(p,s,stencil)
        self.assertLess(max(abs(a-b) for p,q in zip(actual,expected) for a,b in zip(p,q)),1e-10)
        # Moving the guide preserves the exact connectivity and reduction request.
        moved=[(x*1.3,y+.2,z*.7) for x,y,z in p]
        other=core.Plan(moved,s,lambda p:(0,1,0),3)
        self.assertEqual(density.apply(other,[request]).faces,reduced.faces)
        # Higher base density resolves the saved parameter line, not stale ids.
        high=core.Plan(p,s,lambda p:(0,1,0),4)
        self.assertEqual(len(density.apply(high,[request]).faces),256-16)

    def test_closed_cylinder_loop(self):
        count=8
        pts=[(math.cos(2*math.pi*i/count),y,math.sin(2*math.pi*i/count)) for y in (0,1,2) for i in range(count)]
        edges=[(r*count+i,r*count+(i+1)%count) for r in range(3) for i in range(count)]
        edges += [(r*count+i,(r+1)*count+i) for r in range(2) for i in range(count)]
        p,s=network(pts,edges);plan=core.Plan(p,s,lambda p:(p[0],0,p[2]),2)
        topology=density.Topology(plan.faces);positions=plan.evaluate(p,s,stencil)
        # Circumferential interior row at y=.5.
        e=next(e for e in topology.owners if all(abs(positions[v][1]-.5)<1e-7 for v in e))
        loop=topology.loop(e);self.assertEqual(len(loop),count*4)
        reduced=density.apply(plan,[density.describe(plan,e)])
        self.assertFalse(reduced.rejected)
        self.assertEqual(len(reduced.faces),len(plan.faces)-count*4)
        self.assertEqual(reduced.count,plan.count-count*4)
        owners=density.Topology(reduced.faces).owners
        self.assertTrue(all(len(v)<=2 for v in owners.values()))

    def test_poles_are_rejected(self):
        p,s=polygon(5);plan=core.Plan(p,s,lambda p:(0,1,0),2)
        topology=density.Topology(plan.faces)
        center=next(v for v,n in topology.neighbors.items() if len(n)==5)
        with self.assertRaises(ValueError):topology.loop((center,next(iter(topology.neighbors[center]))))

    def test_field_default_locality_and_density(self):
        p,s=polygon(4);plan=core.Plan(p,s,lambda p:(0,1,0),3)
        self.assertEqual(local_fields.weights(plan,{}),[1. if i in plan.guide_vertices else 0. for i in range(plan.count)])
        key=plan.region_keys[0];field={}
        local_fields.paint(field,.5,.5,.75,1.)
        weights=local_fields.weights(plan,{key:field})
        uv=plan.edit_coordinates()[key]
        middle=next(v for v,p in uv.items() if p==(.5,.5))
        self.assertEqual(weights[middle],.75)
        corner=next(v for v,p in uv.items() if p==(0.,0.));self.assertEqual(weights[corner],1.)
        for level in (2,4):
            other=core.Plan(p,s,lambda p:(0,1,0),level)
            middle=next(v for v,p in other.edit_coordinates()[key].items() if p==(.5,.5))
            self.assertEqual(local_fields.weights(other,{key:field})[middle],.75)

if __name__=='__main__':unittest.main()
