from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from closure_artifact.analysis import reproduce_all
from closure_artifact.metrics import exact_mcnemar_p, mde_80
from closure_artifact.taxonomy import classify


class ReproductionTests(unittest.TestCase):
    def test_exact_mcnemar_primary(self) -> None:
        self.assertAlmostEqual(exact_mcnemar_p(33, 0), 2.3283064365386963e-10)

    def test_taxonomy_priority(self) -> None:
        self.assertEqual(classify("duplicate", "wontfix").level1, "REDIRECTED")
        self.assertEqual(classify("not_planned", "Stale").level1, "ABANDONED")
        self.assertEqual(classify("completed", "upstream-issue").level1, "ABANDONED")

    def test_mde_values(self) -> None:
        self.assertAlmostEqual(mde_80(36, 33), 0.460, places=3)
        self.assertAlmostEqual(mde_80(82, 12), 0.11888584086781229, places=10)

    def test_reproduced_headlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = reproduce_all(ROOT, Path(directory))
        human = result["human_primary"]
        self.assertEqual(human["by_system"]["closure_aware"]["correct"], 34)
        self.assertEqual(human["by_system"]["binary_state"]["correct"], 1)
        self.assertEqual(human["paired_outcomes"]["structured_only"], 33)
        self.assertEqual(human["human_llm_agreement"]["agreement_count"], 48)
        taxonomy = result["taxonomy_validation"]
        self.assertEqual(taxonomy["correct"], 117)
        self.assertAlmostEqual(taxonomy["macro_f1"], 0.9747, places=4)
        self.assertAlmostEqual(taxonomy["cohen_kappa"], 0.9667, places=4)
        action = result["generation_descriptive"]["action_routing"]
        lookup = {(row["action_dimension"], row["system"]): row["realized"] for row in action}
        self.assertEqual(lookup[("NEEDS_INFO_request", "closure_aware")], 16)
        self.assertEqual(lookup[("NEEDS_INFO_request", "raw_metadata")], 4)
        self.assertEqual(lookup[("REDIRECTED_route_elsewhere", "closure_aware")], 7)
        self.assertEqual(lookup[("REDIRECTED_route_elsewhere", "raw_metadata")], 0)


if __name__ == "__main__":
    unittest.main()
