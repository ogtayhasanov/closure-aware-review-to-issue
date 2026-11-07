from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from closure_artifact.analysis import reproduce_all
from closure_artifact.followups import switch_arm
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

    def test_switch_requires_confirmed_bot_closure_and_absent_fix(self) -> None:
        bot_closed = {"tracker": "GitHub", "switch_state": "closed", "closer_type": "bot", "linked_fix": "0"}
        self.assertEqual(switch_arm(bot_closed), "TAXONOMY-ONLY")
        for change in (
            {"linked_fix": "1"}, {"linked_fix": ""}, {"switch_state": "open"},
            {"closer_type": "human"}, {"tracker": "Trac"},
        ):
            with self.subTest(change=change):
                self.assertEqual(switch_arm({**bot_closed, **change}), "RAW")

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
        followup = result["generation_followup"]
        self.assertEqual(followup["generation_rows"], 1780)
        self.assertEqual(followup["case_counts"]["audit35"], 35)
        self.assertEqual(followup["switch_cases"], {"bot_test": 50, "fair": 5})
        self.assertEqual(followup["switch_audit_cases"], 4)
        self.assertEqual(followup["human_check"]["human_labels"], 24)
        self.assertEqual(followup["human_check"]["raw_only_correct"], 8)
        self.assertEqual(followup["combined_check_requested_labels"], 8)
        gpt = followup["combined_outcome_differences"]["gpt-4o-mini-2024-07-18"]
        self.assertAlmostEqual(gpt["difference"], -2 / 35)
        self.assertEqual(gpt["paired_percentile_95"], [-6 / 35, 2 / 35])
        retrieval = result["external_retrieval"]
        rrf = next(row for row in retrieval["methods"] if row["method"] == "rrf")
        self.assertAlmostEqual(rrf["mrr"], 0.2890973404537107)
        self.assertEqual(rrf["hit_at_1_count"], 16)
        halfway = next(row for row in retrieval["primary_selective_curve"] if row["target_coverage"] == 0.5)
        self.assertEqual(halfway["accepted"], 41)
        self.assertEqual(halfway["strict_success_accepted"], 12)
        self.assertAlmostEqual(halfway["enrichment_fisher_p_holm"], 0.015771968893613576)
        tuned = next(row for row in result["synthetic_bge_development"] if row["method"] == "bge_ft")
        self.assertEqual(tuned["n"], 794)
        self.assertAlmostEqual(tuned["mrr"], 0.8351395954814675)


if __name__ == "__main__":
    unittest.main()
