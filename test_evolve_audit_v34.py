import unittest
from evolve_audit_v34 import classify, HOLDS, ALLOCATIONS
class AuditTests(unittest.TestCase):
    def test_regimes_use_past_only(self):
        self.assertEqual(classify([100]*90+[1000], 90), 'sideways')
        self.assertEqual(classify([100]*89+[120]+[120], 90), 'bull')
    def test_predeclared_cases(self):
        self.assertEqual(HOLDS, (30, 60))
        self.assertEqual(ALLOCATIONS, (.25, .5))
if __name__ == '__main__':
    unittest.main()
