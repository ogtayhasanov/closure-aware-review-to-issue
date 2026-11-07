# Reviewer guide

This supplement accompanies *From User Reviews to Grounded Responses: Closure-Reason-Aware Response Generation over Retrieved Software Issues*. It reproduces statistical analyses from frozen categorical decisions, scores and ranks.

Extract the ZIP and open a terminal in the extracted `tosem-artifact` folder. Run the command below with Python 3.10 or later on Windows, macOS or Linux. It uses the standard library, needs a writable temporary directory, and requires no network, model weights or API credentials.

```sh
python scripts/verify_submission.py --require-manifest
```

A successful run reports verified SHA-256 checksums, the data boundary, matching generated results and passing tests. It leaves the packaged tables intact. To retain separate copies of the recomputed results, run the following command.

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

The [evidence coverage table](RESULTS.md) marks the results that can be recomputed from this snapshot. The DeepMatcher appendix and certain legacy comparisons are included as [manuscript-reported aggregates](../results/reference/manuscript_reported.json). The original human audit, selected follow-up human check and judge-only comparisons are separate endpoints. The [data statement](../DATA_AVAILABILITY.md) describes the source material held outside the package.
