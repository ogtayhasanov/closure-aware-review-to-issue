#!/usr/bin/env python3
"""
MODAL: FAIR HÄRING BGE-ZS vs FROZEN BGE-FT EPOCH-2 RETRIEVAL

Signal is intentionally EXCLUDED because it was used in synthetic fine-tuning.
External apps are Firefox, VLC, and Nextcloud only.

Primary controlled contrast:
    BGE-ZS-NOPREFIX-TITLE
    vs
    BGE-FT-E2-NOPREFIX-TITLE

Secondary reference:
    BGE-ZS-PREFIX-TITLE

This script does NOT claim semantic Hit@3/P@3 until newly retrieved
pairs receive human labels.

Expected Modal volume: splade-data
Frozen checkpoint:
    /vol/bge_ft_seed42_controlled/best_model
Checkpoint metadata:
    /vol/bge_ft_seed42_controlled/best_checkpoint.json

Häring data:
    /vol/haring_modal_pack.zip
or
    /vol/haring_data/
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

import modal

APP_NAME = "haring-bge-ft-eval"
VOLUME_NAME = "splade-data"
VOL = Path("/vol")
CHECKPOINT = VOL / "bge_ft_seed42_controlled" / "best_model"
CHECKPOINT_META = VOL / "bge_ft_seed42_controlled" / "best_checkpoint.json"
OUTPUT = VOL / "haring_bge_ft_modal"

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.4,<3",
        "transformers>=4.50,<5",
        "pandas>=2.2,<3",
        "numpy>=2,<3",
        "safetensors>=0.4,<1",
    )
)

APP_CONFIG = {
    "Firefox": {
        "package": "org.mozilla.firefox",
        "issue_hints": ["df_firefox_issues_android", "df_firefox_issues", "firefox_issues"],
        "paper_bug_count": 29941,
    },
    "VLC": {
        "package": "org.videolan.vlc",
        "issue_hints": ["df_vlc_issues", "vlc_issues"],
        "paper_bug_count": 553,
    },
    "Nextcloud": {
        "package": "com.nextcloud.client",
        "issue_hints": ["df_nextcloud_issues", "nextcloud_issues"],
        "paper_bug_count": 2462,
    },
}

MODEL_NAME = "BAAI/bge-base-en-v1.5"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_LENGTH = 128


def clean(x):
    import pandas as pd
    return "" if pd.isna(x) else str(x).strip()


def norm_id(x):
    import numpy as np
    import pandas as pd
    if pd.isna(x):
        return ""
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))
    s = str(x).strip()
    if re.fullmatch(r"-?\d+\.0", s):
        return s[:-2]
    return s


def bool_value(x):
    import numpy as np
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "1", "yes", "y", "relevant"}:
        return True
    if s in {"false", "0", "no", "n", "irrelevant"}:
        return False
    raise ValueError(f"Cannot interpret relevance value: {x!r}")


def squash(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def first_col(df, options):
    for c in options:
        if c in df.columns:
            return c
    return None


def read_any(path):
    import pandas as pd
    try:
        return pd.read_csv(path, compression="infer")
    except Exception as e1:
        try:
            return pd.read_csv(path, compression="gzip")
        except Exception:
            raise RuntimeError(f"Could not read CSV/GZ {path}: {e1}")


def prepare_haring_root():
    dir_path = VOL / "haring_data"
    zip_path = VOL / "haring_modal_pack.zip"

    if dir_path.exists() and dir_path.is_dir():
        print(f"Using Häring directory: {dir_path}", flush=True)
        return dir_path

    if zip_path.exists():
        dest = Path("/tmp/haring_modal_pack")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {zip_path} -> {dest}", flush=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
        return dest

    raise FileNotFoundError(
        "Häring data not found. Expected /vol/haring_modal_pack.zip "
        "or /vol/haring_data/."
    )


def all_candidate_files(root):
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".csv", ".gz"}
    ]


def find_coding_file(files):
    scored = []
    for p in files:
        s = squash(p.name)
        if "icse2021codingresolved" in s:
            scored.append((100, len(str(p)), p))
        elif "codingresolved" in s:
            scored.append((80, len(str(p)), p))
    if not scored:
        raise FileNotFoundError("ICSE2021-Coding-Resolved not found.")
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


def find_issue_file_by_content(files, app_name, required_judged_ids):
    """
    Identify the correct issue corpus by CONTENT, not filename.

    The selected corpus must contain ALL issue IDs that Häring originally
    judged for this app. This avoids relying on arbitrary Kaggle filenames.
    """
    candidates = []

    for p in files:
        try:
            df = read_any(p)
        except Exception:
            continue

        if df is None or len(df) == 0:
            continue

        id_col = first_col(
            df,
            [
                "id",
                "issue_id",
                "ticket_id",
                "bug_id",
                "number",
                "issue_number",
                "bugid",
                "ticket",
            ],
        )
        title_col = first_col(
            df,
            [
                "title",
                "summary",
                "issue_text",
                "subject",
                "name",
            ],
        )

        # Coding file and unrelated tables are not candidate corpora unless
        # they genuinely expose an issue-ID column plus issue title/summary.
        if id_col is None or title_col is None:
            continue

        corpus_ids = set(df[id_col].map(norm_id))
        corpus_ids.discard("")

        overlap = len(corpus_ids & required_judged_ids)
        coverage = overlap / max(1, len(required_judged_ids))

        candidates.append(
            {
                "path": p,
                "df": df,
                "id_col": id_col,
                "title_col": title_col,
                "rows": len(df),
                "overlap": overlap,
                "coverage": coverage,
            }
        )

    if not candidates:
        raise FileNotFoundError(
            f"{app_name}: no CSV/GZ file in the pack has both an "
            "ID-like column and a title/summary-like column."
        )

    candidates.sort(
        key=lambda x: (x["overlap"], x["rows"]),
        reverse=True,
    )

    print("\n" + "=" * 100)
    print(f"CONTENT-BASED CORPUS CANDIDATES — {app_name}")
    print("=" * 100)
    for c in candidates[:10]:
        print(
            f"overlap={c['overlap']:4d}/{len(required_judged_ids):4d} "
            f"coverage={c['coverage']:.4f} "
            f"rows={c['rows']:8d} "
            f"id={str(c['id_col']):18s} "
            f"title={str(c['title_col']):18s} "
            f"file={c['path']}",
            flush=True,
        )

    best = candidates[0]

    if best["overlap"] != len(required_judged_ids):
        raise RuntimeError(
            f"{app_name}: best corpus recovers only "
            f"{best['overlap']}/{len(required_judged_ids)} originally judged "
            f"issue IDs. Refusing to evaluate on a mismatched corpus."
        )

    # If multiple files have complete coverage, choose the one with the
    # largest row count (sorting above), but report the ambiguity.
    complete = [
        c for c in candidates
        if c["overlap"] == len(required_judged_ids)
    ]
    if len(complete) > 1:
        print(
            f"WARNING {app_name}: {len(complete)} files have complete judged-ID "
            "coverage; selecting the largest candidate corpus.",
            flush=True,
        )

    print(
        f"SELECTED {app_name}: {best['path']} "
        f"({best['rows']:,} rows; complete judged-ID coverage)",
        flush=True,
    )

    return best["path"], best["df"]


def load_haring(root):
    import numpy as np
    import pandas as pd

    files = all_candidate_files(root)
    print(f"Candidate CSV/GZ files found: {len(files)}", flush=True)

    coding_path = find_coding_file(files)
    coding = read_any(coding_path).copy()
    coding["_row_order"] = np.arange(len(coding))

    required = {"app", "user_feedback_id", "issue_id", "fitting_issue"}
    missing = required - set(coding.columns)
    if missing:
        raise KeyError(f"Coding file missing columns: {sorted(missing)}")

    review_text_col = first_col(
        coding,
        ["user_feedback", "review_text", "review", "content", "feedback_text"],
    )
    if review_text_col is None:
        raise KeyError("Coding file has no recognized review-text column.")

    coding["_query_id"] = coding["user_feedback_id"].map(norm_id)
    coding["_issue_id"] = coding["issue_id"].map(norm_id)
    coding["_review_text"] = coding[review_text_col].map(clean)
    coding["_relevant"] = coding["fitting_issue"].map(bool_value)

    package_to_app = {cfg["package"]: app_name for app_name, cfg in APP_CONFIG.items()}

    # The published Häring coding file still contains Signal rows.
    # Signal is intentionally excluded from THIS external evaluation because
    # it was used in our synthetic fine-tuning. Filter it out rather than
    # treating its presence in the source coding file as an error.
    original_rows = len(coding)
    coding = coding[coding["app"].astype(str).isin(package_to_app)].copy()
    removed_rows = original_rows - len(coding)
    print(
        f"Filtered coding file to external-only apps "
        f"{list(APP_CONFIG)}: kept {len(coding)} rows, removed {removed_rows} rows.",
        flush=True,
    )

    coding["_app_name"] = coding["app"].map(package_to_app)

    if set(coding["_app_name"].dropna().unique()) != set(APP_CONFIG):
        raise AssertionError(
            f"After filtering, expected apps {sorted(APP_CONFIG)} but found "
            f"{sorted(coding['_app_name'].dropna().unique())}"
        )

    qcounts = coding.groupby("_app_name")["_query_id"].nunique()
    for app_name in APP_CONFIG:
        if int(qcounts.get(app_name, 0)) != 50:
            raise AssertionError(
                f"{app_name}: expected 50 verified problem reports, "
                f"got {int(qcounts.get(app_name, 0))}"
            )

    pair_counts = coding.groupby(["_app_name", "_query_id"]).size()
    print(
        "Per-review judgment-count distribution:",
        pair_counts.value_counts().sort_index().to_dict(),
        flush=True,
    )
    if not (pair_counts == 3).all() or len(coding) != 450:
        raise AssertionError(
            f"Expected 450 rows and exactly 3 judged suggestions/review; got {len(coding)} rows."
        )

    label_counts = (
        coding.groupby(["_app_name", "_query_id", "_issue_id"])["_relevant"].nunique()
    )
    if (label_counts > 1).any():
        raise AssertionError("Contradictory relevance labels found.")

    existing_judgments = {
        (app_name, qid, iid): bool(rel)
        for (app_name, qid, iid), rel in (
            coding.groupby(["_app_name", "_query_id", "_issue_id"])["_relevant"]
            .first()
            .items()
        )
    }

    queries = (
        coding.sort_values("_row_order")
        .drop_duplicates(["_app_name", "_query_id"])
        [["_app_name", "_query_id", "_review_text"]]
        .rename(columns={
            "_app_name": "app",
            "_query_id": "query_id",
            "_review_text": "review_text",
        })
        .reset_index(drop=True)
    )
    if len(queries) != 150:
        raise AssertionError(f"Expected 150 verified problem reports, got {len(queries)}.")

    baseline_rows = []
    for app_name, sub in coding.groupby("_app_name", sort=True):
        per_review = sub.groupby("_query_id")["_relevant"].agg(["sum", "max"]).reset_index()
        baseline_rows.append({
            "app": app_name,
            "n_reviews": int(len(per_review)),
            "n_judged_pairs": int(len(sub)),
            "n_relevant_pairs": int(sub["_relevant"].sum()),
            "semantic_Hit@3": float(per_review["max"].mean()),
            "Precision@3": float((per_review["sum"] / 3.0).mean()),
        })
    baseline = pd.DataFrame(baseline_rows)

    # VERIFIED PACK: corpus identity is fixed by exact filename.
    # Never infer it from judged-ID overlap, because the coding table itself
    # contains those IDs and can masquerade as a candidate corpus.
    exact_corpora = {
        "Firefox": ("df_firefox_issues_android.csv", 29941),
        "VLC": ("df_vlc_issues.csv", 553),
        "Nextcloud": ("df_nextcloud_issues.csv", 2462),
    }

    corpora = {}
    corpus_meta = []
    for app_name, cfg in APP_CONFIG.items():
        filename, expected_raw_rows = exact_corpora[app_name]
        path = root / filename

        if not path.exists():
            raise FileNotFoundError(
                f"{app_name}: required verified corpus missing: {path}"
            )

        df = read_any(path).copy()

        if len(df) != expected_raw_rows:
            raise AssertionError(
                f"{app_name}: expected exactly {expected_raw_rows:,} raw rows "
                f"in {filename}, got {len(df):,}. Refusing to evaluate."
            )

        print(
            f"VERIFIED SOURCE {app_name:12s}: {filename} "
            f"raw_rows={len(df):,}",
            flush=True,
        )

        id_col = first_col(df, ["id", "issue_id", "ticket_id", "bug_id", "number", "issue_number", "bugid", "ticket"])
        title_col = first_col(df, ["title", "summary", "issue_text", "subject", "name"])
        body_col = first_col(df, ["body", "description", "issue_body", "clean_body"])

        df["_issue_id"] = df[id_col].map(norm_id)
        df["_title"] = df[title_col].map(clean)
        df["_body"] = df[body_col].map(clean) if body_col else ""

        df = df[(df["_issue_id"] != "") & (df["_title"] != "")].copy()

        dup = int(df["_issue_id"].duplicated().sum())
        if dup:
            print(f"WARNING {app_name}: dropping {dup} duplicate IDs.", flush=True)
            df = df.drop_duplicates("_issue_id", keep="first")

        df = df.reset_index(drop=True)

        judged_ids = set(coding.loc[coding["_app_name"] == app_name, "_issue_id"])
        absent = sorted(judged_ids - set(df["_issue_id"]))
        if absent:
            raise AssertionError(
                f"{app_name}: {len(absent)} original judged IDs absent from {path}; "
                f"examples={absent[:10]}"
            )

        corpora[app_name] = {
            "path": str(path),
            "ids": df["_issue_id"].tolist(),
            "titles": df["_title"].tolist(),
            "bodies": df["_body"].tolist(),
        }
        corpus_meta.append({
            "app": app_name,
            "file": str(path),
            "candidate_bug_reports_used": int(len(df)),
            "paper_reported_bug_reports": int(cfg["paper_bug_count"]),
            "count_difference_vs_paper": int(len(df) - cfg["paper_bug_count"]),
            "all_original_judged_issue_ids_present": True,
        })
        print(f"{app_name:12s}: {len(df):,} issues <- {path.name}", flush=True)

    # Final provenance guard: impossible to proceed with the coding table
    # or another accidental file as an issue corpus.
    expected_source_names = {
        "Firefox": "df_firefox_issues_android.csv",
        "VLC": "df_vlc_issues.csv",
        "Nextcloud": "df_nextcloud_issues.csv",
    }
    for app_name, expected_name in expected_source_names.items():
        actual_name = Path(corpora[app_name]["path"]).name
        if actual_name != expected_name:
            raise AssertionError(
                f"{app_name}: wrong corpus source {actual_name}; expected {expected_name}"
            )

    return (
        coding,
        queries,
        existing_judgments,
        corpora,
        baseline,
        pd.DataFrame(corpus_meta),
    )


class BGE:
    def __init__(self, path, device):
        from transformers import AutoModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModel.from_pretrained(path).to(device).eval()
        self.device = device

    def encode(self, texts, batch_size=128):
        import torch
        import torch.nn.functional as F

        blocks = []
        with torch.inference_mode():
            for st in range(0, len(texts), batch_size):
                batch = list(texts[st:st + batch_size])
                toks = self.tokenizer(
                    batch,
                    max_length=MAX_LENGTH,
                    truncation=True,
                    padding=True,
                    return_tensors="pt",
                )
                toks = {k: v.to(self.device, non_blocking=True) for k, v in toks.items()}

                dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
                with torch.autocast("cuda", dtype=dtype):
                    out = self.model(**toks)
                    emb = out.last_hidden_state[:, 0]

                emb = F.normalize(emb.float(), p=2, dim=1)
                blocks.append(emb.cpu())

        return torch.cat(blocks, dim=0)


def store_top3(rows, app_name, model_name, query_frame, scores, corpus, existing_judgments):
    import numpy as np

    if scores.shape != (len(query_frame), len(corpus["ids"])):
        raise AssertionError(
            f"{app_name}/{model_name}: bad score shape {scores.shape}"
        )

    for qi, qrow in enumerate(query_frame.itertuples(index=False)):
        order = np.argsort(-scores[qi], kind="stable")[:3]
        for rank, di in enumerate(order, start=1):
            di = int(di)
            iid = corpus["ids"][di]
            key = (app_name, str(qrow.query_id), str(iid))
            known = key in existing_judgments

            rows.append({
                "app": app_name,
                "model": model_name,
                "query_id": str(qrow.query_id),
                "review_text": qrow.review_text,
                "rank": rank,
                "candidate_issue_id": iid,
                "candidate_title": corpus["titles"][di],
                "candidate_body": corpus["bodies"][di],
                "score": float(scores[qi, di]),
                "already_judged_by_haring": bool(known),
                "existing_relevance_if_known": (
                    int(existing_judgments[key]) if known else None
                ),
            })


@app.function(
    image=image,
    volumes={"/vol": volume},
    gpu="A100-40GB",
    cpu=8.0,
    memory=32768,
    timeout=60 * 60,
)
def evaluate_fullrank():
    """
    SPLADE-COMPARABLE KNOWN-POSITIVE FULL-CORPUS EVALUATION.

    Unit of evaluation:
      Only Häring reviews with >=1 originally human-judged relevant issue.

    Gold for a query:
      The set of issue IDs among Häring's original 3 suggestions that were
      labeled fitting_issue=True.

    Metric:
      Rank of the BEST known-positive issue over the complete app corpus.

    Primary controlled comparison:
      BGE-ZS-NOPREFIX-TITLE vs BGE-FT-E2-NOPREFIX-TITLE.

    This is intentionally the same diagnostic interpretation used by the
    historical SPLADE external-rank experiments. It is NOT a complete semantic
    relevance evaluation because unjudged issues may also be relevant.
    """
    import gc
    import numpy as np
    import pandas as pd
    import torch

    volume.reload()

    if not CHECKPOINT.exists():
        raise FileNotFoundError(f"Frozen checkpoint missing: {CHECKPOINT}")
    if not CHECKPOINT_META.exists():
        raise FileNotFoundError(f"Checkpoint metadata missing: {CHECKPOINT_META}")

    meta = json.loads(CHECKPOINT_META.read_text(encoding="utf-8"))
    if int(meta.get("best_epoch", -1)) != 2:
        raise AssertionError(
            f"Expected frozen best_epoch=2, got {meta.get('best_epoch')}"
        )

    print(
        f"Frozen checkpoint verified: epoch=2, "
        f"internal MRR={meta.get('best_internal_dev_MRR')}",
        flush=True,
    )

    root = prepare_haring_root()
    (
        coding,
        queries,
        existing_judgments,
        corpora,
        baseline,
        corpus_meta,
    ) = load_haring(root)

    out = VOL / "haring_bge_fullrank"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Build EXACT historical known-positive query subsets.
    # ------------------------------------------------------------------
    relevant = coding[coding["_relevant"]].copy()

    gold_ids = (
        relevant.groupby(["_app_name", "_query_id"])["_issue_id"]
        .agg(lambda x: tuple(dict.fromkeys(map(str, x))))
        .to_dict()
    )

    positive_queries = queries[
        queries.apply(
            lambda r: (str(r["app"]), str(r["query_id"])) in gold_ids,
            axis=1,
        )
    ].copy()

    expected_positive_counts = {
        "Firefox": 28,
        "VLC": 21,
        "Nextcloud": 33,
    }

    observed_positive_counts = (
        positive_queries.groupby("app")["query_id"].nunique().to_dict()
    )

    print("\nKNOWN-POSITIVE QUERY COUNTS", flush=True)
    print(observed_positive_counts, flush=True)

    for app_name, expected_n in expected_positive_counts.items():
        got = int(observed_positive_counts.get(app_name, 0))
        if got != expected_n:
            raise AssertionError(
                f"{app_name}: expected {expected_n} known-positive queries "
                f"(historical SPLADE-compatible subset), got {got}."
            )

    if len(positive_queries) != sum(expected_positive_counts.values()):
        raise AssertionError(
            f"Expected {sum(expected_positive_counts.values())} total "
            f"known-positive queries, got {len(positive_queries)}."
        )

    device = torch.device("cuda")
    print("GPU:", torch.cuda.get_device_name(0), flush=True)

    per_query_rows = []

    def score_one_model(model, model_name, use_prefix=False):
        for app_name in APP_CONFIG:
            qf = (
                positive_queries[positive_queries["app"] == app_name]
                .reset_index(drop=True)
            )
            corpus = corpora[app_name]

            ids = list(map(str, corpus["ids"]))
            id_to_idx = {iid: i for i, iid in enumerate(ids)}

            # Every known-positive ID must exist in the exact verified corpus.
            for qrow in qf.itertuples(index=False):
                gids = gold_ids[(app_name, str(qrow.query_id))]
                absent = [g for g in gids if g not in id_to_idx]
                if absent:
                    raise AssertionError(
                        f"{app_name}/{qrow.query_id}: known-positive IDs absent "
                        f"from verified corpus: {absent}"
                    )

            doc_vecs = model.encode(corpus["titles"], batch_size=256)

            qtexts = qf["review_text"].tolist()
            if use_prefix:
                qtexts = [BGE_QUERY_PREFIX + x for x in qtexts]

            query_vecs = model.encode(qtexts, batch_size=64)
            scores = (query_vecs @ doc_vecs.T).numpy()

            if scores.shape != (len(qf), len(ids)):
                raise AssertionError(
                    f"{model_name}/{app_name}: score shape {scores.shape}, "
                    f"expected {(len(qf), len(ids))}"
                )

            for qi, qrow in enumerate(qf.itertuples(index=False)):
                # Stable descending full ranking, exactly as a full-corpus
                # retrieval evaluation requires.
                order = np.argsort(-scores[qi], kind="stable")
                inverse_rank = np.empty(len(order), dtype=np.int64)
                inverse_rank[order] = np.arange(1, len(order) + 1)

                gids = gold_ids[(app_name, str(qrow.query_id))]
                gold_ranks = [int(inverse_rank[id_to_idx[g]]) for g in gids]
                best_rank = int(min(gold_ranks))

                per_query_rows.append({
                    "app": app_name,
                    "tracker": {
                        "Firefox": "Bugzilla",
                        "VLC": "Trac",
                        "Nextcloud": "GitHub",
                    }[app_name],
                    "model": model_name,
                    "query_id": str(qrow.query_id),
                    "review_text": qrow.review_text,
                    "n_known_positive_issues": int(len(gids)),
                    "known_positive_issue_ids": ";".join(gids),
                    "all_known_positive_ranks": ";".join(map(str, sorted(gold_ranks))),
                    "best_gold_rank": best_rank,
                    "hit_at_1": int(best_rank <= 1),
                    "hit_at_5": int(best_rank <= 5),
                    "hit_at_10": int(best_rank <= 10),
                    "reciprocal_rank": float(1.0 / best_rank),
                })

            print(
                f"{model_name:28s} {app_name:12s}: "
                f"{len(qf)} queries x {len(ids):,} docs",
                flush=True,
            )

            del doc_vecs, query_vecs, scores
            gc.collect()
            torch.cuda.empty_cache()

    # Primary zero-shot baseline, same no-prefix preprocessing as training.
    zs = BGE(MODEL_NAME, device)
    score_one_model(zs, "BGE-ZS-NOPREFIX-TITLE", use_prefix=False)

    # Secondary standard BGE-prefix reference; kept separate from primary contrast.
    score_one_model(zs, "BGE-ZS-PREFIX-TITLE", use_prefix=True)

    del zs
    gc.collect()
    torch.cuda.empty_cache()

    # Frozen epoch-2 fine-tuned checkpoint, no prefix.
    ft = BGE(str(CHECKPOINT), device)
    score_one_model(ft, "BGE-FT-E2-NOPREFIX-TITLE", use_prefix=False)

    del ft
    gc.collect()
    torch.cuda.empty_cache()

    per_query = pd.DataFrame(per_query_rows)

    expected_models = {
        "BGE-ZS-NOPREFIX-TITLE",
        "BGE-ZS-PREFIX-TITLE",
        "BGE-FT-E2-NOPREFIX-TITLE",
    }
    if set(per_query["model"]) != expected_models:
        raise AssertionError(
            f"Unexpected models: {sorted(per_query['model'].unique())}"
        )

    expected_rows = len(positive_queries) * len(expected_models)
    if len(per_query) != expected_rows:
        raise AssertionError(
            f"Expected {expected_rows} per-query rows, got {len(per_query)}."
        )

    # ------------------------------------------------------------------
    # Summary metrics, same family as historical SPLADE table.
    # ------------------------------------------------------------------
    summary_rows = []
    for (app_name, tracker, model_name), g in per_query.groupby(
        ["app", "tracker", "model"], sort=True
    ):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append({
            "app": app_name,
            "tracker": tracker,
            "family": model_name,
            "queries": int(len(g)),
            "MRR": float(np.mean(1.0 / ranks)),
            "hit_at_1": float(np.mean(ranks <= 1)),
            "hit_at_5": float(np.mean(ranks <= 5)),
            "hit_at_10": float(np.mean(ranks <= 10)),
            "median_gold_rank": float(np.median(ranks)),
            "mean_gold_rank": float(np.mean(ranks)),
        })

    # Pooled row across all three external apps.
    for model_name, g in per_query.groupby("model", sort=True):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append({
            "app": "POOLED",
            "tracker": "Mixed",
            "family": model_name,
            "queries": int(len(g)),
            "MRR": float(np.mean(1.0 / ranks)),
            "hit_at_1": float(np.mean(ranks <= 1)),
            "hit_at_5": float(np.mean(ranks <= 5)),
            "hit_at_10": float(np.mean(ranks <= 10)),
            "median_gold_rank": float(np.median(ranks)),
            "mean_gold_rank": float(np.mean(ranks)),
        })

    summary_df = pd.DataFrame(summary_rows)

    # ------------------------------------------------------------------
    # Direct FT-vs-ZS rank movement table.
    # ------------------------------------------------------------------
    primary = per_query[
        per_query["model"].isin([
            "BGE-ZS-NOPREFIX-TITLE",
            "BGE-FT-E2-NOPREFIX-TITLE",
        ])
    ].copy()

    pivot = primary.pivot(
        index=["app", "tracker", "query_id"],
        columns="model",
        values="best_gold_rank",
    ).reset_index()

    zs_col = "BGE-ZS-NOPREFIX-TITLE"
    ft_col = "BGE-FT-E2-NOPREFIX-TITLE"

    movement_rows = []
    for (app_name, tracker), g in pivot.groupby(["app", "tracker"], sort=True):
        z = g[zs_col].to_numpy(dtype=int)
        f = g[ft_col].to_numpy(dtype=int)
        movement_rows.append({
            "app": app_name,
            "tracker": tracker,
            "queries": int(len(g)),
            "moved_into_top1": int(np.sum((z > 1) & (f <= 1))),
            "moved_out_of_top1": int(np.sum((z <= 1) & (f > 1))),
            "moved_into_top10": int(np.sum((z > 10) & (f <= 10))),
            "moved_out_of_top10": int(np.sum((z <= 10) & (f > 10))),
            "rank_improved": int(np.sum(f < z)),
            "rank_worsened": int(np.sum(f > z)),
            "rank_unchanged": int(np.sum(f == z)),
            "median_rank_change_ft_minus_zs": float(np.median(f - z)),
            "mean_rank_change_ft_minus_zs": float(np.mean(f - z)),
        })

    movement_df = pd.DataFrame(movement_rows)

    # Per-query paired primary comparison.
    paired = pivot.rename(columns={
        zs_col: "ZS_gold_rank",
        ft_col: "FT_gold_rank",
    })
    paired["delta_rank_FT_minus_ZS"] = (
        paired["FT_gold_rank"] - paired["ZS_gold_rank"]
    )
    paired["FT_improved"] = paired["FT_gold_rank"] < paired["ZS_gold_rank"]
    paired["FT_worsened"] = paired["FT_gold_rank"] > paired["ZS_gold_rank"]

    # ------------------------------------------------------------------
    # Save.
    # ------------------------------------------------------------------
    per_query.to_csv(
        out / "bge_known_positive_fullrank_per_query.csv",
        index=False,
    )
    summary_df.to_csv(
        out / "bge_known_positive_fullrank_summary.csv",
        index=False,
    )
    movement_df.to_csv(
        out / "bge_ft_vs_zs_rank_movements.csv",
        index=False,
    )
    paired.to_csv(
        out / "bge_ft_vs_zs_paired_ranks.csv",
        index=False,
    )
    corpus_meta.to_csv(out / "corpus_validation.csv", index=False)

    result = {
        "frozen_checkpoint": str(CHECKPOINT),
        "frozen_best_epoch": 2,
        "frozen_internal_dev_MRR": float(meta.get("best_internal_dev_MRR")),
        "evaluation": (
            "SPLADE-compatible known-positive full-corpus rank diagnostic"
        ),
        "positive_query_counts": observed_positive_counts,
        "primary_models": [
            "BGE-ZS-NOPREFIX-TITLE",
            "BGE-FT-E2-NOPREFIX-TITLE",
        ],
        "secondary_reference": "BGE-ZS-PREFIX-TITLE",
        "summary": summary_df.to_dict("records"),
        "rank_movements": movement_df.to_dict("records"),
        "interpretation_guard": (
            "Known-positive rank diagnostic only; unjudged corpus issues may "
            "also be semantically relevant."
        ),
    }

    (out / "BGE_FULLRANK_SUMMARY.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    archive_base = "/tmp/haring_bge_fullrank_results"
    shutil.make_archive(archive_base, "zip", root_dir=str(out))
    shutil.copy2(
        archive_base + ".zip",
        out / "haring_bge_fullrank_results.zip",
    )

    volume.commit()

    # Human-readable console tables.
    primary_summary = summary_df[
        summary_df["family"].isin([
            "BGE-ZS-NOPREFIX-TITLE",
            "BGE-FT-E2-NOPREFIX-TITLE",
        ])
    ][
        [
            "app", "tracker", "family", "queries",
            "MRR", "hit_at_1", "hit_at_10", "median_gold_rank"
        ]
    ].copy()

    print("\n" + "=" * 100)
    print("PRIMARY BGE FULL-CORPUS KNOWN-POSITIVE RESULTS")
    print("=" * 100)
    print(primary_summary.to_string(index=False), flush=True)

    print("\n" + "=" * 100)
    print("FT VS ZS RANK MOVEMENTS")
    print("=" * 100)
    print(movement_df.to_string(index=False), flush=True)

    return result


@app.local_entrypoint()
def main():
    result = evaluate_fullrank.remote()
    print("\nDONE.")
    print(
        "Results saved to "
        "/vol/haring_bge_fullrank/haring_bge_fullrank_results.zip"
    )
