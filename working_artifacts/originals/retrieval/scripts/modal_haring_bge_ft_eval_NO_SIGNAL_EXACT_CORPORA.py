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
def evaluate():
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

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    baseline.to_csv(OUTPUT / "original_deepmatcher_human_baseline.csv", index=False)
    queries.to_csv(OUTPUT / "haring_150_external_problem_reports.csv", index=False)
    corpus_meta.to_csv(OUTPUT / "corpus_validation.csv", index=False)

    device = torch.device("cuda")
    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    rows = []

    # Zero-shot BGE loaded once.
    zs = BGE(MODEL_NAME, device)

    for app_name in APP_CONFIG:
        qf = queries[queries["app"] == app_name].reset_index(drop=True)
        corpus = corpora[app_name]

        dv = zs.encode(corpus["titles"], batch_size=256)

        qv_no = zs.encode(qf["review_text"].tolist(), batch_size=64)
        scores_no = (qv_no @ dv.T).numpy()
        store_top3(
            rows, app_name, "BGE-ZS-NOPREFIX-TITLE",
            qf, scores_no, corpus, existing_judgments
        )

        qv_pre = zs.encode(
            [BGE_QUERY_PREFIX + x for x in qf["review_text"]],
            batch_size=64,
        )
        scores_pre = (qv_pre @ dv.T).numpy()
        store_top3(
            rows, app_name, "BGE-ZS-PREFIX-TITLE",
            qf, scores_pre, corpus, existing_judgments
        )

        print(f"ZS {app_name:12s}: 50 x {len(corpus['ids']):,}", flush=True)

        del dv, qv_no, qv_pre, scores_no, scores_pre
        gc.collect()
        torch.cuda.empty_cache()

    del zs
    gc.collect()
    torch.cuda.empty_cache()

    # Frozen epoch-2 BGE-FT, no prefix only.
    ft = BGE(str(CHECKPOINT), device)

    for app_name in APP_CONFIG:
        qf = queries[queries["app"] == app_name].reset_index(drop=True)
        corpus = corpora[app_name]

        qv = ft.encode(qf["review_text"].tolist(), batch_size=64)
        dv = ft.encode(corpus["titles"], batch_size=256)
        scores = (qv @ dv.T).numpy()

        store_top3(
            rows, app_name, "BGE-FT-E2-NOPREFIX-TITLE",
            qf, scores, corpus, existing_judgments
        )

        print(f"FT {app_name:12s}: 50 x {len(corpus['ids']):,}", flush=True)

        del qv, dv, scores
        gc.collect()
        torch.cuda.empty_cache()

    del ft
    gc.collect()
    torch.cuda.empty_cache()

    retrieval = pd.DataFrame(rows)

    expected_models = {
        "BGE-ZS-NOPREFIX-TITLE",
        "BGE-ZS-PREFIX-TITLE",
        "BGE-FT-E2-NOPREFIX-TITLE",
    }
    if set(retrieval["model"]) != expected_models:
        raise AssertionError(
            f"Unexpected models: {sorted(retrieval['model'].unique())}"
        )

    counts = retrieval.groupby(["model", "app", "query_id"]).size()
    if not (counts == 3).all():
        raise AssertionError("Top-3 structure incomplete.")

    expected_rows = 3 * 3 * 50 * 3
    if len(retrieval) != expected_rows:
        raise AssertionError(
            f"Expected {expected_rows} rows, got {len(retrieval)}."
        )

    retrieval.to_csv(OUTPUT / "bge_modal_top3_all_pairs.csv", index=False)

    reuse = (
        retrieval.groupby(["model", "app"])["already_judged_by_haring"]
        .agg(["sum", "count"])
        .reset_index()
    )
    reuse["reuse_fraction"] = reuse["sum"] / reuse["count"]
    reuse.to_csv(OUTPUT / "judgment_reuse_by_model_app.csv", index=False)

    new = retrieval[~retrieval["already_judged_by_haring"]].copy()
    annotation_rows = []

    for (app_name, qid, iid), g in new.groupby(
        ["app", "query_id", "candidate_issue_id"], sort=False
    ):
        first = g.iloc[0]
        methods = "; ".join(
            f"{r.model}@{int(r.rank)}"
            for r in g.sort_values(["model", "rank"]).itertuples(index=False)
        )

        annotation_rows.append({
            "pair_key": f"{app_name}|||{qid}|||{iid}",
            "app": app_name,
            "query_id": qid,
            "review_text": first["review_text"],
            "candidate_issue_id": iid,
            "candidate_title": first["candidate_title"],
            "candidate_body": first["candidate_body"],
            "retrieved_by": methods,
            "annotator1_same_feature": "",
            "annotator1_same_behavior": "",
            "annotator1_relevant": "",
            "annotator2_same_feature": "",
            "annotator2_same_behavior": "",
            "annotator2_relevant": "",
            "resolved_relevant": "",
            "resolution_notes": "",
        })

    annotation = pd.DataFrame(annotation_rows)
    annotation.to_csv(OUTPUT / "ANNOTATE_BGE_new_pairs.csv", index=False)

    def top3_sets(model_name):
        x = retrieval[retrieval["model"] == model_name]
        result = {}
        for (app_name, qid), g in x.groupby(["app", "query_id"]):
            result[(app_name, str(qid))] = set(
                g["candidate_issue_id"].astype(str)
            )
        return result

    zs_sets = top3_sets("BGE-ZS-NOPREFIX-TITLE")
    ft_sets = top3_sets("BGE-FT-E2-NOPREFIX-TITLE")
    overlaps = [
        len(zs_sets[k] & ft_sets[k])
        for k in sorted(zs_sets)
    ]

    summary = {
        "frozen_checkpoint": str(CHECKPOINT),
        "frozen_best_epoch": 2,
        "frozen_internal_dev_MRR": float(meta.get("best_internal_dev_MRR")),
        "queries": 150,
        "original_haring_judgments": int(len(coding)),
        "original_haring_relevant_pairs": int(coding["_relevant"].sum()),
        "models": sorted(expected_models),
        "retrieval_rows": int(len(retrieval)),
        "unique_new_pairs_needing_annotation": int(len(annotation)),
        "zs_no_prefix_vs_ft_top3_overlap": {
            "mean_shared_of_3": float(np.mean(overlaps)),
            "median_shared_of_3": float(np.median(overlaps)),
            "queries_same_top3_set": int(sum(x == 3 for x in overlaps)),
            "queries_zero_shared": int(sum(x == 0 for x in overlaps)),
        },
        "IMPORTANT": (
            "Do NOT report BGE semantic Hit@3/P@3 until all newly retrieved "
            "pairs have resolved human relevance labels."
        ),
    }

    (OUTPUT / "BGE_MODAL_SUMMARY.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    archive = "/tmp/haring_bge_ft_modal_results"
    shutil.make_archive(archive, "zip", root_dir=str(OUTPUT))
    shutil.copy2(
        archive + ".zip",
        OUTPUT / "haring_bge_ft_modal_results.zip",
    )

    volume.commit()

    print("\n" + "=" * 100)
    print("MODAL HÄRING BGE RETRIEVAL COMPLETE")
    print("=" * 100)
    print(json.dumps(summary, indent=2), flush=True)

    return summary


@app.local_entrypoint()
def main():
    result = evaluate.remote()
    print("\nFINAL SUMMARY")
    print(json.dumps(result, indent=2))
