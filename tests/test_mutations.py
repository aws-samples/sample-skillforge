from __future__ import annotations

import unittest

from skillforge import mutations, validate


class MutationHarnessTests(unittest.TestCase):
    def test_every_validation_gate_has_exactly_one_checked_in_mutation(self) -> None:
        gates = [mutation.gate for mutation in mutations.MUTATIONS]
        self.assertEqual(len(gates), len(set(gates)))
        self.assertEqual(set(gates), set(validate.gate_names()))
        for mutation in mutations.MUTATIONS:
            self.assertTrue(mutation.expected)
            self.assertTrue(mutation.id)


if __name__ == "__main__":
    unittest.main()
