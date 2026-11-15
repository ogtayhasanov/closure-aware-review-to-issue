from __future__ import annotations

import sys
import csv
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from closure_artifact.analysis import build_mde_rows, reproduce_all
from closure_artifact.followups import switch_arm
from closure_artifact.metrics import exact_mcnemar_p, mde_80
from closure_artifact.taxonomy import classify
import validate_public_snapshot as public_snapshot
from verify_submission import verify_manifest


class ReproductionTests(unittest.TestCase):
    def test_exact_mcnemar_primary(self) -> None:
        self.assertAlmostEqual(exact_mcnemar_p(33, 0), 2.3283064365386963e-10)

    def test_taxonomy_priority(self) -> None:
        self.assertEqual(classify("duplicate", "wontfix").level1, "REDIRECTED")
        self.assertEqual(classify("not_planned", "Stale").level1, "ABANDONED")
        self.assertEqual(classify("completed", "upstream-issue").level1, "ABANDONED")

    def test_curated_taxonomy_fields_reproduce_frozen_rules(self) -> None:
        path = ROOT / "working_artifacts" / "curated" / "taxonomy_tracker_fields_120.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 120)
        for row in rows:
            with self.subTest(case=row["case_id"]):
                predicted = classify(row["state_reason"], row["labels"])
                self.assertEqual((predicted.level1, predicted.subtype), (row["rule_l1"], row["rule_subtype"]))

    def test_curated_audit_labels_and_rank_links(self) -> None:
        base = ROOT / "working_artifacts" / "curated"
        with (base / "ai_relevance_labels_796.csv").open(encoding="utf-8", newline="") as handle:
            labels = list(csv.DictReader(handle))
        with (base / "ai_relevance_ranked_1066.csv").open(encoding="utf-8", newline="") as handle:
            ranks = list(csv.DictReader(handle))
        self.assertEqual(len(labels), 796)
        self.assertEqual(len(ranks), 1066)
        by_pair = {row["pair_id"]: row["relevant_yes_no_unsure"] for row in labels}
        self.assertEqual(len(by_pair), 796)
        self.assertEqual(sum(label == "Yes" for label in by_pair.values()), 174)
        self.assertEqual(sum(label == "No" for label in by_pair.values()), 489)
        self.assertEqual(sum(label == "Unsure" for label in by_pair.values()), 133)
        self.assertTrue(all(by_pair[row["pair_id"]] == row["label"] for row in ranks))

    def test_manuscript_prevalence_arithmetic(self) -> None:
        path = ROOT / "working_artifacts" / "curated" / "manuscript_figure1_prevalence_9.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 9)
        self.assertEqual(sum(int(row["nonresolved_count"]) for row in rows), 33662)
        self.assertEqual(sum(int(row["closed_issues"]) for row in rows), 117695)

    def test_working_artifacts_are_scanned_for_private_paths_and_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "snapshot"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            probe = copy / "working_artifacts" / "curated" / "privacy_probe.py"
            fake_key = "sk-" + "x" * 32
            fake_path = "C:" + "\\" + "Users" + "\\" + "Example" + "\\" + "Downloads"
            probe.write_text(f"key = {fake_key!r}\npath = {fake_path!r}\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(copy / "scripts" / "validate_public_snapshot.py")],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Potential OpenAI-style key", result.stdout)
            self.assertIn("Local Windows path", result.stdout)

    def test_verifier_allows_local_files_without_hiding_manifest_damage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "snapshot"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            (copy / ".DS_Store").write_bytes(b"Finder metadata")
            egg_info = copy / "src" / "closure_artifact.egg-info"
            egg_info.mkdir()
            (egg_info / "PKG-INFO").write_text("local editable install\n", encoding="utf-8")
            for destination in (copy / "recomputed", copy / "data" / "recomputed", copy / "working_artifacts" / "recomputed"):
                reproduce_all(copy, destination)

            verify_manifest(copy)
            with patch.object(public_snapshot, "ROOT", copy), patch.object(public_snapshot, "WORKING_ARTIFACTS", copy / "working_artifacts"):
                self.assertEqual(public_snapshot.main(), 0)
            with self.assertRaisesRegex(ValueError, "differ from the checksum inventory"):
                verify_manifest(copy, strict_inventory=True)

            for destination in (copy / "recomputed", copy / "data" / "recomputed", copy / "working_artifacts" / "recomputed"):
                shutil.rmtree(destination)
            verify_manifest(copy, strict_inventory=True)
            citation = copy / "CITATION.cff"
            citation.write_text(citation.read_text(encoding="utf-8") + "# modified\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                verify_manifest(copy)
            citation.unlink()
            with self.assertRaisesRegex(ValueError, "Missing or unsafe manifest path"):
                verify_manifest(copy)

    def test_mde_values(self) -> None:
        self.assertAlmostEqual(mde_80(36, 33), 0.460, places=3)
        self.assertAlmostEqual(mde_80(82, 12), 0.11888584086781229, places=10)

    def test_mde_uses_derived_pair_counts(self) -> None:
        human = {"n_pairs": 20, "paired_outcomes": {"structured_only": 5, "binary_only": 2}}
        retrieval = {"paired_tests": [{"comparison": "rrf_vs_bge_zs", "metric": "hit_at_1", "n": 8, "rrf_higher": 1, "bge_higher": 3}]}
        first, second = build_mde_rows(human, retrieval)
        self.assertEqual((first["n"], first["a_only"], first["b_only"]), (20, 5, 2))
        self.assertEqual((second["n"], second["a_only"], second["b_only"]), (8, 1, 3))

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
