# Data availability

The repository provides a text-free reproduction snapshot and a separate working-artifact collection.

## Text-free reproduction snapshot

- author-created source code and protocols;
- opaque case identifiers;
- categorical closure labels and deterministic mapping rules;
- binary human and automated judgments;
- numeric evaluation scores, hashes, and aggregate results;
- opaque paired retrieval ranks and frozen confidence scores;
- sanitized follow-up decisions and actor-category provenance, plus the shared system and judge instructions authored for the experiment.

The text-free tables in `data/derived/` preserve the pairings and decisions used to recompute the headline statistics. [Evidence coverage](docs/RESULTS.md)

## Working artifacts

The `working_artifacts/` directory contains original run outputs, including source text, generated responses, prompts, judge logs, and annotation workbooks. It also contains recovered execution scripts and case-level tables, with source checksums and coverage for each requested result. Third-party material is subject to the terms of its original sources. [Working artifacts inventory](working_artifacts/README.md)
