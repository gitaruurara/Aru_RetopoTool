import ctypes,struct,unittest
from Aru_RetopoTool.native import unpack,packed,ints

class Buffers(unittest.TestCase):
    def test_binary_values_preserved(self):
        points=[(-0.0,1e-200,-1e200),(float('inf'),float('-inf'),3.125)]
        values=packed(points)
        actual=unpack(values)
        self.assertEqual(struct.pack('=6d',*(v for p in actual for v in p)),bytes(values))
    def test_prefix_and_empty_buffer(self):
        values=packed([(1,2,3),(4,5,6)])
        self.assertEqual(unpack(values,count=1),[(1.,2.,3.)])
        self.assertEqual(unpack(values,count=0),[])
        self.assertEqual(unpack((ctypes.c_double*0)()),[])
    def test_list_compatibility(self):
        self.assertEqual(unpack([1,2,3,4,5,6]),[(1,2,3),(4,5,6)])

    def test_integer_native_copy_is_independent(self):
        source=ints([-1,0,2147483647,-2147483648])
        copied=ints(source)
        self.assertEqual(bytes(source),bytes(copied))
        copied[0]=99
        self.assertEqual(source[0],-1)
        self.assertEqual(len(ints(ints([]))),0)
