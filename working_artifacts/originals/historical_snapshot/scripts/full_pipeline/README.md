# Full-pipeline scripts

These are retained method scripts, organized by analysis stage. They are supplied for inspection and future reconstruction; they are not the dependency-free quick reproducer.

Known portability constraints:

- several scripts reference original Windows Downloads, Kaggle, or Modal paths;
- retrieval and prevalence scripts require corpora/snapshots not bundled here;
- model runs require substantial downloads, GPU resources, and pinned versions;
- generation and clean cross-tracker annotation scripts may require API access;
- historical model aliases are not immutable, so new output is a replication rather than a byte-identical reproduction;
- scripts preserve original output names and safety checks and may refuse to overwrite prior runs.

Use `scripts/quick/reproduce_all.py` for the evaluated offline path. Consult `docs/CLAIM_EVIDENCE_MATRIX.md` before assigning evidentiary status to a full-pipeline script.

