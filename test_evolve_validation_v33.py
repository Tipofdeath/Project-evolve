import unittest
from evolve_validation_v33 import HOLDS, ALLOCATIONS, SYMBOLS
class ValidationTests(unittest.TestCase):
    def test_scenarios(self):
        self.assertEqual(HOLDS, (7, 14, 30, 60))
        self.assertEqual(ALLOCATIONS, (.25, .5))
        self.assertEqual(len(SYMBOLS), 3)
if __name__ == '__main__':
    unittest.main()
