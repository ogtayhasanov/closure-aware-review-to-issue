# Data availability

This public snapshot follows a data-minimization boundary.

## Included

- author-created source code and protocols;
- opaque case identifiers;
- categorical closure labels and deterministic mapping rules;
- binary human and automated judgments;
- numeric evaluation scores, hashes, and aggregate results;
- opaque paired retrieval ranks and frozen confidence scores;
- sanitized follow-up decisions and actor-category provenance, plus the shared system and judge instructions authored for the experiment.

## Not redistributed

- app-review text or source review identifiers;
- issue titles, bodies, or comments;
- generated developer-facing responses;
- filled user prompts, evidence bundles, raw tracker timelines, and provider request/response logs;
- annotation workbooks that reproduce any of that text;
- model weights or external platform exports.

The omitted source records originate from public software and app-review platforms, but public accessibility does not by itself establish a blanket downstream redistribution license. The complete internal evidence archive is retained for controlled verification; any later release will depend on source terms, author approval, and an appropriate acquisition or access mechanism.

The text-free tables in `data/derived/` preserve the pairings and decisions needed to recompute the public headline statistics without reconstructing or exposing the underlying text.

The reproduction commands recalculate statistics from archived scores, ranks, and labels. Verification of individual source texts, fresh judging, and end-to-end model runs require controlled access to the internal archives and source data. The manuscript's DeepMatcher appendix counts have a separate reported-only record. [Evidence coverage](docs/RESULTS.md)
