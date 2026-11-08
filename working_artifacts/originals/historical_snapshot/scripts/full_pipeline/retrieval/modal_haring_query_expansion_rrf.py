#!/usr/bin/env python3
"""
Frozen Häring query-expansion retrieval experiment on Modal.

No training, parameter sweep, or tuning. The local entrypoint reads the frozen
82-query expansion CSV and passes it to the remote evaluator.

Systems:
  RRF2-ORIGINAL = BGE(original) + BM25(original)
  RRF2-EXPANDED = BGE(original+expansion) + BM25(original+expansion)
  RRF3-QUERYEXP = BGE(original) + BM25(original) + BGE(original+expansion)

All RRF terms use k=60. Issue documents are title-only.
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
import zipfile
from pathlib import Path

import modal

APP_NAME = "haring-query-expansion-rrf"
VOLUME_NAME = "splade-data"
VOL = Path("/vol")
OUTPUT = VOL / "haring_query_expansion_rrf"
MODEL_NAME = "BAAI/bge-base-en-v1.5"
MAX_LENGTH = 128
RRF_K = 60

SYSTEMS = ["RRF2-ORIGINAL", "RRF2-EXPANDED", "RRF3-QUERYEXP"]

APP_CONFIG = {
    "Firefox": {
        "package": "org.mozilla.firefox",
        "filename": "df_firefox_issues_android.csv",
        "raw_rows": 29941,
    },
    "VLC": {
        "package": "org.videolan.vlc",
        "filename": "df_vlc_issues.csv",
        "raw_rows": 553,
    },
    "Nextcloud": {
        "package": "com.nextcloud.client",
        "filename": "df_nextcloud_issues.csv",
        "raw_rows": 2462,
    },
}

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.4,<3",
        "transformers>=4.50,<5",
        "pandas>=2.2,<3",
        "numpy>=2,<3",
        "rank-bm25>=0.2.2,<1",
        "scipy>=1.14,<2",
    )
)


def clean(x):
    import pandas as pd
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()


def norm_id(x):
    import numpy as np
    import pandas as pd
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))
    s = str(x).strip()
    return s[:-2] if re.fullmatch(r"-?\d+\.0", s) else s


def bool_value(x):
    import numpy as np
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = clean(x).lower()
    if s in {"true", "1", "yes", "y", "relevant"}:
        return True
    if s in {"false", "0", "no", "n", "irrelevant"}:
        return False
    raise ValueError(f"Cannot parse relevance value {x!r}")


def first_col(df, names):
    for c in names:
        if c in df.columns:
            return c
    return None


def prepare_root():
    d = VOL / "haring_data"
    z = VOL / "haring_modal_pack.zip"
    if d.exists():
        return d
    if z.exists():
        dest = Path("/tmp/haring_query_expansion_pack")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        return dest
    raise FileNotFoundError("Expected /vol/haring_data or /vol/haring_modal_pack.zip")


def find_coding(root):
    candidates = list(root.rglob("*Coding*Resolved*.csv"))
    if not candidates:
        candidates = [
            p for p in root.rglob("*.csv")
            if "coding" in p.name.lower() and "resolved" in p.name.lower()
        ]
    if not candidates:
        raise FileNotFoundError("Häring coding CSV not found")
    return candidates[0]


def tokenize(text):
    return re.findall(r"[a-z0-9]+", clean(text).lower())


def review_key(app_name, query_id):
    return (str(app_name), norm_id(query_id))


class BGE:
    def __init__(self, path, device):
        from transformers import AutoModel, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModel.from_pretrained(path).to(device).eval()
        self.device = device

    def encode(self, texts, batch_size=256):
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
                blocks.append(F.normalize(emb.float(), p=2, dim=1).cpu())
        return torch.cat(blocks, dim=0)


def load_data(root):
    import pandas as pd

    coding_path = find_coding(root)
    coding = pd.read_csv(coding_path, low_memory=False).copy()

    required = {"app", "user_feedback_id", "issue_id", "fitting_issue"}
    missing = required - set(coding.columns)
    if missing:
        raise KeyError(f"Coding file missing: {sorted(missing)}")

    review_col = first_col(
        coding,
        ["user_feedback", "review_text", "review", "content", "feedback_text"],
    )
    if review_col is None:
        raise KeyError("No review text column")

    package_to_app = {cfg["package"]: app_name for app_name, cfg in APP_CONFIG.items()}
    coding = coding[coding["app"].astype(str).isin(package_to_app)].copy()
    if len(coding) != 450:
        raise AssertionError(f"Expected 450 external judgments, got {len(coding)}")

    coding["_app_name"] = coding["app"].map(package_to_app)
    coding["_query_id"] = coding["user_feedback_id"].map(norm_id)
    coding["_issue_id"] = coding["issue_id"].map(norm_id)
    coding["_review_text"] = coding[review_col].map(clean)
    coding["_relevant"] = coding["fitting_issue"].map(bool_value)

    queries = (
        coding.drop_duplicates(["_app_name", "_query_id"])
        [["_app_name", "_query_id", "_review_text"]]
        .rename(columns={
            "_app_name": "app",
            "_query_id": "query_id",
            "_review_text": "review_text",
        })
        .reset_index(drop=True)
    )

    relevant = coding[coding["_relevant"]].copy()
    gold_ids = (
        relevant.groupby(["_app_name", "_query_id"])["_issue_id"]
        .agg(lambda x: tuple(dict.fromkeys(map(str, x))))
        .to_dict()
    )

    positive = queries[
        queries.apply(
            lambda r: (str(r["app"]), str(r["query_id"])) in gold_ids,
            axis=1,
        )
    ].copy()

    expected = {"Firefox": 28, "Nextcloud": 33, "VLC": 21}
    observed = positive.groupby("app")["query_id"].nunique().to_dict()
    if observed != expected:
        raise AssertionError(f"Known-positive query counts changed: {observed}")

    corpora = {}
    for app_name, cfg in APP_CONFIG.items():
        path = root / cfg["filename"]
        if not path.exists():
            raise FileNotFoundError(path)

        df = pd.read_csv(path, low_memory=False).copy()
        if len(df) != cfg["raw_rows"]:
            raise AssertionError(
                f"{app_name}: expected {cfg['raw_rows']} raw rows, got {len(df)}"
            )

        id_col = first_col(
            df,
            ["id", "issue_id", "ticket_id", "bug_id", "number", "issue_number", "bugid", "ticket"],
        )
        title_col = first_col(
            df,
            ["title", "summary", "issue_text", "subject", "name"],
        )
        if id_col is None or title_col is None:
            raise KeyError(f"{app_name}: missing ID/title column")

        df["_issue_id"] = df[id_col].map(norm_id)
        df["_title"] = df[title_col].map(clean)
        df = df[(df["_issue_id"] != "") & (df["_title"] != "")].copy()

        if df["_issue_id"].duplicated().any():
            df = df.drop_duplicates("_issue_id", keep="first")

        judged = set(coding.loc[coding["_app_name"] == app_name, "_issue_id"])
        absent = judged - set(df["_issue_id"])
        if absent:
            raise AssertionError(f"{app_name}: judged IDs absent: {list(absent)[:10]}")

        corpora[app_name] = {
            "ids": df["_issue_id"].astype(str).tolist(),
            "titles": df["_title"].tolist(),
        }

        print(f"{app_name}: {len(df):,} candidate issues", flush=True)

    return positive, gold_ids, corpora


def ranks_from_scores(scores):
    import numpy as np
    order = np.argsort(-scores, kind="stable")
    inv = np.empty(len(order), dtype=np.int64)
    inv[order] = np.arange(1, len(order) + 1)
    return inv


def append_result(rows, app_name, query_id, review_text, expansion, expanded_query,
                  system, ranks, id_to_idx, gold_issue_ids):
    gold_ranks = [int(ranks[id_to_idx[g]]) for g in gold_issue_ids]
    best = min(gold_ranks)
    rows.append({
        "app": app_name,
        "system": system,
        "query_id": str(query_id),
        "review_text": review_text,
        "expansion": expansion,
        "expanded_query": expanded_query,
        "known_positive_issue_ids": ";".join(gold_issue_ids),
        "all_known_positive_ranks": ";".join(map(str, sorted(gold_ranks))),
        "best_gold_rank": int(best),
        "hit_at_1": int(best <= 1),
        "hit_at_5": int(best <= 5),
        "hit_at_10": int(best <= 10),
        "reciprocal_rank": float(1.0 / best),
    })


def exact_mcnemar_p(a_only, b_only):
    n = int(a_only + b_only)
    if n == 0:
        return 1.0
    k = min(int(a_only), int(b_only))
    lower = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * lower)


def holm_adjust(p_values):
    import numpy as np
    p = np.asarray(p_values, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj_sorted = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order):
        val = min(1.0, (m - rank) * p[idx])
        running = max(running, val)
        adj_sorted[rank] = running
    adjusted = np.empty(m, dtype=float)
    for rank, idx in enumerate(order):
        adjusted[idx] = adj_sorted[rank]
    return adjusted


def sign_test_two_sided(improved, worsened):
    n = int(improved + worsened)
    if n == 0:
        return 1.0
    k = min(int(improved), int(worsened))
    lower = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * lower)


@app.function(
    image=image,
    volumes={"/vol": volume},
    gpu="A100-40GB",
    cpu=8.0,
    memory=32768,
    timeout=60 * 60,
)
def evaluate(expansion_rows):
    import gc
    import numpy as np
    import pandas as pd
    import torch
    from rank_bm25 import BM25Okapi
    from scipy.stats import wilcoxon

    volume.reload()
    root = prepare_root()
    positive, gold_ids, corpora = load_data(root)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    exp = pd.DataFrame(expansion_rows).copy()
    required = {"app", "query_id", "review_text", "expansion", "expanded_query", "prompt_version"}
    missing = required - set(exp.columns)
    if missing:
        raise KeyError(f"Expansion file missing: {sorted(missing)}")
    if len(exp) != 82:
        raise AssertionError(f"Expected 82 expansion rows, got {len(exp)}")

    exp["query_id"] = exp["query_id"].map(norm_id)
    for c in ["app", "review_text", "expansion", "expanded_query"]:
        exp[c] = exp[c].map(clean)

    if exp.duplicated(["app", "query_id"]).any():
        raise AssertionError("Duplicate app/query_id in expansion file")

    exp_map = {
        review_key(r.app, r.query_id): {
            "review_text": r.review_text,
            "expansion": r.expansion,
            "expanded_query": r.expanded_query,
        }
        for r in exp.itertuples(index=False)
    }

    benchmark_keys = {
        review_key(r.app, r.query_id)
        for r in positive.itertuples(index=False)
    }
    if set(exp_map) != benchmark_keys:
        raise AssertionError("Expansion query keys do not match the 82 benchmark queries")

    for q in positive.itertuples(index=False):
        key = review_key(q.app, q.query_id)
        if clean(q.review_text) != exp_map[key]["review_text"]:
            raise AssertionError(f"Original review mismatch for {q.app}/{q.query_id}")
        expected_expanded = (clean(q.review_text) + " " + exp_map[key]["expansion"]).strip()
        if expected_expanded != exp_map[key]["expanded_query"]:
            raise AssertionError(f"Expanded query mismatch for {q.app}/{q.query_id}")

    device = torch.device("cuda")
    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    bge = BGE(MODEL_NAME, device)

    rows = []

    for app_name in APP_CONFIG:
        qf = positive[positive["app"] == app_name].reset_index(drop=True)
        corpus = corpora[app_name]
        ids = corpus["ids"]
        titles = corpus["titles"]
        id_to_idx = {iid: i for i, iid in enumerate(ids)}

        print(f"\n{app_name}: encoding {len(titles):,} issue titles", flush=True)

        doc_vecs = bge.encode(titles, batch_size=256)
        original_queries = qf["review_text"].map(clean).tolist()
        expanded_queries = [
            exp_map[review_key(app_name, q.query_id)]["expanded_query"]
            for q in qf.itertuples(index=False)
        ]
        expansions = [
            exp_map[review_key(app_name, q.query_id)]["expansion"]
            for q in qf.itertuples(index=False)
        ]

        original_vecs = bge.encode(original_queries, batch_size=64)
        expanded_vecs = bge.encode(expanded_queries, batch_size=64)
        original_dense_scores = (original_vecs @ doc_vecs.T).numpy()
        expanded_dense_scores = (expanded_vecs @ doc_vecs.T).numpy()

        tokenized_docs = [tokenize(t) for t in titles]
        bm25 = BM25Okapi(tokenized_docs)

        for qi, q in enumerate(qf.itertuples(index=False)):
            gids = gold_ids[(app_name, str(q.query_id))]

            original_bge_ranks = ranks_from_scores(original_dense_scores[qi])
            expanded_bge_ranks = ranks_from_scores(expanded_dense_scores[qi])

            original_bm25_scores = np.asarray(
                bm25.get_scores(tokenize(original_queries[qi])),
                dtype=np.float64,
            )
            expanded_bm25_scores = np.asarray(
                bm25.get_scores(tokenize(expanded_queries[qi])),
                dtype=np.float64,
            )

            original_bm25_ranks = ranks_from_scores(original_bm25_scores)
            expanded_bm25_ranks = ranks_from_scores(expanded_bm25_scores)

            rrf2_original = (
                1.0 / (RRF_K + original_bge_ranks.astype(np.float64))
                + 1.0 / (RRF_K + original_bm25_ranks.astype(np.float64))
            )
            rrf2_expanded = (
                1.0 / (RRF_K + expanded_bge_ranks.astype(np.float64))
                + 1.0 / (RRF_K + expanded_bm25_ranks.astype(np.float64))
            )
            rrf3_queryexp = (
                1.0 / (RRF_K + original_bge_ranks.astype(np.float64))
                + 1.0 / (RRF_K + original_bm25_ranks.astype(np.float64))
                + 1.0 / (RRF_K + expanded_bge_ranks.astype(np.float64))
            )

            for system, scores in {
                "RRF2-ORIGINAL": rrf2_original,
                "RRF2-EXPANDED": rrf2_expanded,
                "RRF3-QUERYEXP": rrf3_queryexp,
            }.items():
                append_result(
                    rows, app_name, q.query_id, original_queries[qi],
                    expansions[qi], expanded_queries[qi], system,
                    ranks_from_scores(scores), id_to_idx, gids,
                )

        del doc_vecs, original_vecs, expanded_vecs, original_dense_scores, expanded_dense_scores, bm25
        gc.collect()
        torch.cuda.empty_cache()

    per_query = pd.DataFrame(rows)
    if len(per_query) != 246:
        raise AssertionError(f"Expected 246 result rows, got {len(per_query)}")

    per_query.to_csv(OUTPUT / "query_expansion_per_query.csv", index=False)

    summary_rows = []
    for (app_name, system), g in per_query.groupby(["app", "system"], sort=True):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append({
            "app": app_name,
            "system": system,
            "n": len(g),
            "MRR": float(np.mean(1.0 / ranks)),
            "H@1": float(np.mean(ranks <= 1)),
            "H@5": float(np.mean(ranks <= 5)),
            "H@10": float(np.mean(ranks <= 10)),
            "H@50": float(np.mean(ranks <= 50)),
            "median_gold_rank": float(np.median(ranks)),
        })

    for system, g in per_query.groupby("system", sort=True):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append({
            "app": "POOLED",
            "system": system,
            "n": len(g),
            "MRR": float(np.mean(1.0 / ranks)),
            "H@1": float(np.mean(ranks <= 1)),
            "H@5": float(np.mean(ranks <= 5)),
            "H@10": float(np.mean(ranks <= 10)),
            "H@50": float(np.mean(ranks <= 50)),
            "median_gold_rank": float(np.median(ranks)),
        })

    summary = pd.DataFrame(summary_rows)

    base = summary[
        (summary["app"] == "POOLED")
        & (summary["system"] == "RRF2-ORIGINAL")
    ].iloc[0]

    if int(round(base["H@1"] * 82)) != 16:
        raise AssertionError(f"Baseline H@1 reproduction failed: {base['H@1']}")
    if int(round(base["H@10"] * 82)) != 42:
        raise AssertionError(f"Baseline H@10 reproduction failed: {base['H@10']}")
    if abs(float(base["MRR"]) - 0.289097) > 5e-6:
        raise AssertionError(f"Baseline MRR reproduction failed: {base['MRR']}")
    if float(base["median_gold_rank"]) != 9.0:
        raise AssertionError(f"Baseline median reproduction failed: {base['median_gold_rank']}")

    summary.to_csv(OUTPUT / "query_expansion_summary.csv", index=False)

    comparisons = [
        ("PRIMARY_RRF3_QUERYEXP_vs_RRF2_ORIGINAL", "RRF3-QUERYEXP", "RRF2-ORIGINAL"),
        ("SECONDARY_RRF2_EXPANDED_vs_RRF2_ORIGINAL", "RRF2-EXPANDED", "RRF2-ORIGINAL"),
    ]

    paired_rows = []

    for comparison_name, candidate_system, baseline_system in comparisons:
        c = (
            per_query[per_query["system"] == candidate_system]
            .set_index(["app", "query_id"]).sort_index()
        )
        b = (
            per_query[per_query["system"] == baseline_system]
            .set_index(["app", "query_id"]).sort_index()
        )
        if not c.index.equals(b.index):
            raise AssertionError(f"Pairing mismatch in {comparison_name}")

        for metric_name, field in [
            ("reciprocal_rank", "reciprocal_rank"),
            ("hit_at_1", "hit_at_1"),
            ("hit_at_10", "hit_at_10"),
        ]:
            x = c[field].to_numpy(dtype=float)
            y = b[field].to_numpy(dtype=float)
            diff = x - y

            if np.allclose(diff, 0):
                w_stat, w_p = 0.0, 1.0
            else:
                w = wilcoxon(x, y, alternative="two-sided", zero_method="wilcox", method="auto")
                w_stat, w_p = float(w.statistic), float(w.pvalue)

            row = {
                "comparison": comparison_name,
                "candidate_system": candidate_system,
                "baseline_system": baseline_system,
                "metric": metric_name,
                "n": len(x),
                "candidate_mean": float(np.mean(x)),
                "baseline_mean": float(np.mean(y)),
                "mean_difference": float(np.mean(diff)),
                "candidate_higher": int(np.sum(diff > 0)),
                "baseline_higher": int(np.sum(diff < 0)),
                "ties": int(np.sum(diff == 0)),
                "wilcoxon_statistic": w_stat,
                "wilcoxon_p": w_p,
                "candidate_only_successes": np.nan,
                "baseline_only_successes": np.nan,
                "exact_mcnemar_p": np.nan,
            }

            if field in {"hit_at_1", "hit_at_10"}:
                xb, yb = x.astype(bool), y.astype(bool)
                candidate_only = int(np.sum(xb & ~yb))
                baseline_only = int(np.sum(~xb & yb))
                row["candidate_only_successes"] = candidate_only
                row["baseline_only_successes"] = baseline_only
                row["exact_mcnemar_p"] = exact_mcnemar_p(candidate_only, baseline_only)

            paired_rows.append(row)

    paired = pd.DataFrame(paired_rows)
    paired["wilcoxon_p_holm_6tests"] = holm_adjust(paired["wilcoxon_p"].to_numpy())
    paired.to_csv(OUTPUT / "query_expansion_paired_tests.csv", index=False)

    movement_rows = []
    for comparison_name, candidate_system, baseline_system in comparisons:
        p = (
            per_query[per_query["system"].isin([candidate_system, baseline_system])]
            .pivot(index=["app", "query_id"], columns="system", values="best_gold_rank")
            .reset_index()
        )
        b_rank = p[baseline_system].to_numpy(dtype=int)
        c_rank = p[candidate_system].to_numpy(dtype=int)
        improved = int(np.sum(c_rank < b_rank))
        worsened = int(np.sum(c_rank > b_rank))
        unchanged = int(np.sum(c_rank == b_rank))

        movement_rows.append({
            "comparison": comparison_name,
            "candidate_system": candidate_system,
            "baseline_system": baseline_system,
            "n": len(p),
            "improved": improved,
            "worsened": worsened,
            "unchanged": unchanged,
            "two_sided_sign_test_p": sign_test_two_sided(improved, worsened),
            "baseline_median_rank": float(np.median(b_rank)),
            "candidate_median_rank": float(np.median(c_rank)),
            "moved_into_top1": int(np.sum((b_rank > 1) & (c_rank <= 1))),
            "moved_out_of_top1": int(np.sum((b_rank <= 1) & (c_rank > 1))),
            "moved_into_top10": int(np.sum((b_rank > 10) & (c_rank <= 10))),
            "moved_out_of_top10": int(np.sum((b_rank <= 10) & (c_rank > 10))),
        })

    movement = pd.DataFrame(movement_rows)
    movement.to_csv(OUTPUT / "query_expansion_rank_movement.csv", index=False)
    exp.sort_values(["app", "query_id"]).to_csv(
        OUTPUT / "query_expansions_82_FROZEN.csv", index=False
    )

    result = {
        "experiment": "Häring frozen LLM query expansion over RRF",
        "rrf_k": RRF_K,
        "document_representation": "issue title only",
        "systems": SYSTEMS,
        "summary": summary.to_dict("records"),
        "paired_tests": paired.to_dict("records"),
        "rank_movement": movement.to_dict("records"),
        "baseline_reproduction": {
            "MRR": float(base["MRR"]),
            "H@1": float(base["H@1"]),
            "H@10": float(base["H@10"]),
            "H@50": float(base["H@50"]),
            "median_gold_rank": float(base["median_gold_rank"]),
        },
        "interpretation_guard": (
            "Häring labels are pool-incomplete. Metrics rank originally "
            "human-judged known-positive issues, not complete semantic relevance."
        ),
        "no_tuning": True,
    }

    (OUTPUT / "QUERY_EXPANSION_SUMMARY.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    archive_base = "/tmp/haring_query_expansion_rrf_results"
    shutil.make_archive(archive_base, "zip", root_dir=str(OUTPUT))
    shutil.copy2(
        archive_base + ".zip",
        OUTPUT / "haring_query_expansion_rrf_results.zip",
    )
    volume.commit()

    print("\n" + "=" * 112)
    print("HÄRING FROZEN QUERY-EXPANSION RRF RESULTS")
    print("=" * 112)

    print("\nPOOLED SUMMARY")
    print(
        summary[summary["app"] == "POOLED"][
            ["system", "n", "MRR", "H@1", "H@10", "H@50", "median_gold_rank"]
        ].to_string(index=False),
        flush=True,
    )

    print("\nPAIRED TESTS")
    print(
        paired[
            [
                "comparison", "metric", "candidate_mean", "baseline_mean",
                "mean_difference", "candidate_higher", "baseline_higher", "ties",
                "wilcoxon_p", "wilcoxon_p_holm_6tests",
                "candidate_only_successes", "baseline_only_successes",
                "exact_mcnemar_p",
            ]
        ].to_string(index=False),
        flush=True,
    )

    print("\nRANK MOVEMENT")
    print(movement.to_string(index=False), flush=True)

    print(
        "\nSaved on Modal volume:\n"
        "/vol/haring_query_expansion_rrf/haring_query_expansion_rrf_results.zip",
        flush=True,
    )

    return result


@app.local_entrypoint()
def main():
    local_csv = Path(
        r"C:\Users\Ogtay\Downloads\haring_query_expansion_20260808\query_expansions_82.csv"
    )
    if not local_csv.exists():
        raise FileNotFoundError(
            f"Missing frozen expansion CSV: {local_csv}\n"
            "Run generate_haring_query_expansions.py first."
        )

    with local_csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 82:
        raise AssertionError(f"Expected 82 expansion rows, got {len(rows)}")

    result = evaluate.remote(rows)

    print("\nREMOTE RUN COMPLETE.")
    print(
        "Baseline reproduction:",
        json.dumps(result["baseline_reproduction"], indent=2),
    )
    print(
        "\nDownload results with:\n"
        "modal volume get -e main splade-data "
        "haring_query_expansion_rrf/haring_query_expansion_rrf_results.zip "
        r"C:\Users\Ogtay\Downloads\haring_query_expansion_rrf_results.zip"
    )
