# Reviewer guide

This supplement accompanies *From User Reviews to Grounded Responses: Closure-Reason-Aware Response Generation over Retrieved Software Issues*. It reproduces statistical analyses from frozen categorical decisions, scores and ranks.

Run the command below from the repository root with Python 3.10 or later on Windows, macOS or Linux. It uses the standard library, needs a writable temporary directory, and runs offline.

```sh
python scripts/verify_submission.py
```

A successful run verifies `MANIFEST.sha256`, the curated working-artifact checksums, the text-free data boundary, the generated results and the tests. Additional local files are scanned but are not covered by the manifest. To require the whole-snapshot manifest explicitly, run `python scripts/verify_submission.py --require-manifest`. Add `--strict-inventory` when validating an exact distribution with no additional non-ignored files. To retain separate copies of the recomputed results, run the following command.

```sh
python scripts/reproduce_all.py --output ../tosem-recomputed
```

| Manuscript result | Artifact output | Expected checkpoint |
| --- | --- | --- |
| Closure taxonomy validation (Table 1) | [Taxonomy summary](../results/generated/taxonomy_validation_summary.json) | 117/120, macro-F1 0.9747, Cohen's kappa 0.9667 |
| Original human status audit | [Human status summary](../results/generated/human_status_summary.json) | 34/36 closure-aware vs 1/36 binary, exact paired p = 2.33e-10 |
| External retrieval and abstention | [Retrieval rates](../results/generated/retrieval_rates.csv), [paired tests](../results/generated/retrieval_paired_tests.csv), [selective curve](../results/generated/retrieval_selective.csv) | RRF MRR 0.289 vs 0.205 for BGE-ZS. At 50% coverage, 12 strict successes in 41 accepted cases |
| Follow-up generation | [Per-arm rates](../results/generated/followup_rates.csv), [paired tests](../results/generated/followup_paired_tests.csv) | GPT bot-probe judge-coded DECLINED 50/50 raw, 12/50 taxonomy only and 50/50 raw + meaning |
| Switch and selected human check | [Reproduction summary](../results/generated/reproduction_summary.json), [agreement](../results/generated/followup_agreement.csv) | Five fair inputs switched. The 24 selected responses give 18/24 judge–human agreement |
| GitHub provenance sensitivity | [Prevalence results](../results/generated/followup_prevalence.csv) | V1 and V2 aggregate rates for seven GitHub projects |

The original human audit, selected follow-up human check and judge-only comparisons are separate endpoints. The evidence coverage table identifies the files supporting each result and the known Firefox input and prevalence limitations. The working artifacts include text-free DeepMatcher audit decisions, the 8 November RAW METADATA re-annotation decisions, and the 82 BGE-FT ranks. [Evidence coverage](RESULTS.md) · [Working artifacts inventory](../working_artifacts/README.md)
