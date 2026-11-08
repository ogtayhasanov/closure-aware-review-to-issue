#!/usr/bin/env python3
"""
MODAL: HÄRING BGE-ZS + BM25 RECIPROCAL RANK FUSION

One-shot retrieval control. No hyperparameter tuning.

External apps only:
    Firefox, VLC, Nextcloud
Signal is excluded.

Evaluation:
    82 Häring reviews with >=1 originally judged positive issue
    full app corpus
    best known-positive rank

Systems:
    BGE-ZS-NOPREFIX-TITLE
    BM25-TITLE
    RRF60-BGE-ZS+BM25-TITLE

RRF:
    score(d) = 1/(60 + rank_BGE(d)) + 1/(60 + rank_BM25(d))

This remains a known-positive rank diagnostic because Häring judgments are
pool-incomplete.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

import modal

APP_NAME = "haring-bge-bm25-rrf"
VOLUME_NAME = "splade-data"

VOL = Path("/vol")
OUTPUT = VOL / "haring_bge_bm25_rrf"

MODEL_NAME = "BAAI/bge-base-en-v1.5"
MAX_LENGTH = 128
RRF_K = 60

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
    )
)


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
        dest = Path("/tmp/haring_rrf_pack")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        return dest

    raise FileNotFoundError(
        "Expected /vol/haring_data or /vol/haring_modal_pack.zip"
    )


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
                toks = {
                    k: v.to(self.device, non_blocking=True)
                    for k, v in toks.items()
                }

                dtype = (
                    torch.bfloat16
                    if torch.cuda.is_bf16_supported()
                    else torch.float16
                )
                with torch.autocast("cuda", dtype=dtype):
                    out = self.model(**toks)
                    emb = out.last_hidden_state[:, 0]

                blocks.append(
                    F.normalize(emb.float(), p=2, dim=1).cpu()
                )

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

    package_to_app = {
        cfg["package"]: app_name
        for app_name, cfg in APP_CONFIG.items()
    }

    coding = coding[coding["app"].astype(str).isin(package_to_app)].copy()
    if len(coding) != 450:
        raise AssertionError(f"Expected 450 external judgments, got {len(coding)}")

    coding["_app_name"] = coding["app"].map(package_to_app)
    coding["_query_id"] = coding["user_feedback_id"].map(norm_id)
    coding["_issue_id"] = coding["issue_id"].map(norm_id)
    coding["_review_text"] = coding[review_col].map(clean)
    coding["_relevant"] = coding["fitting_issue"].map(bool_value)

    qcounts = coding.groupby("_app_name")["_query_id"].nunique().to_dict()
    if qcounts != {"Firefox": 50, "Nextcloud": 50, "VLC": 50}:
        raise AssertionError(f"Unexpected query counts: {qcounts}")

    queries = (
        coding.drop_duplicates(["_app_name", "_query_id"])
        [["_app_name", "_query_id", "_review_text"]]
        .rename(
            columns={
                "_app_name": "app",
                "_query_id": "query_id",
                "_review_text": "review_text",
            }
        )
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
        raise AssertionError(
            f"Known-positive query counts changed: {observed}"
        )

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
            [
                "id", "issue_id", "ticket_id", "bug_id",
                "number", "issue_number", "bugid", "ticket",
            ],
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

        judged = set(
            coding.loc[coding["_app_name"] == app_name, "_issue_id"]
        )
        absent = judged - set(df["_issue_id"])
        if absent:
            raise AssertionError(
                f"{app_name}: judged IDs absent: {list(absent)[:10]}"
            )

        corpora[app_name] = {
            "ids": df["_issue_id"].astype(str).tolist(),
            "titles": df["_title"].tolist(),
        }

        print(
            f"{app_name}: {len(df):,} candidate issues from {cfg['filename']}",
            flush=True,
        )

    return positive, gold_ids, corpora


def ranks_from_scores(scores):
    import numpy as np

    order = np.argsort(-scores, kind="stable")
    inv = np.empty(len(order), dtype=np.int64)
    inv[order] = np.arange(1, len(order) + 1)
    return inv


def append_result(
    rows,
    app_name,
    qid,
    review,
    model,
    ranks,
    id_to_idx,
    gids,
):
    gold_ranks = [int(ranks[id_to_idx[g]]) for g in gids]
    best = min(gold_ranks)

    rows.append(
        {
            "app": app_name,
            "model": model,
            "query_id": str(qid),
            "review_text": review,
            "known_positive_issue_ids": ";".join(gids),
            "all_known_positive_ranks": ";".join(
                map(str, sorted(gold_ranks))
            ),
            "best_gold_rank": int(best),
            "hit_at_1": int(best <= 1),
            "hit_at_5": int(best <= 5),
            "hit_at_10": int(best <= 10),
            "reciprocal_rank": float(1.0 / best),
        }
    )


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
    from rank_bm25 import BM25Okapi

    volume.reload()
    root = prepare_root()
    positive, gold_ids, corpora = load_data(root)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

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

        for q in qf.itertuples(index=False):
            gids = gold_ids[(app_name, str(q.query_id))]
            absent = [g for g in gids if g not in id_to_idx]
            if absent:
                raise AssertionError(
                    f"{app_name}/{q.query_id}: absent gold {absent}"
                )

        print(
            f"\n{app_name}: encoding {len(titles):,} titles",
            flush=True,
        )

        doc_vecs = bge.encode(titles, batch_size=256)
        query_vecs = bge.encode(qf["review_text"].tolist(), batch_size=64)
        dense_scores = (query_vecs @ doc_vecs.T).numpy()

        tokenized_docs = [tokenize(t) for t in titles]
        bm25 = BM25Okapi(tokenized_docs)

        for qi, q in enumerate(qf.itertuples(index=False)):
            gids = gold_ids[(app_name, str(q.query_id))]

            dense_ranks = ranks_from_scores(dense_scores[qi])
            bm25_scores = np.asarray(
                bm25.get_scores(tokenize(q.review_text)),
                dtype=np.float64,
            )
            bm25_ranks = ranks_from_scores(bm25_scores)

            rrf_scores = (
                1.0 / (RRF_K + dense_ranks.astype(np.float64))
                + 1.0 / (RRF_K + bm25_ranks.astype(np.float64))
            )
            rrf_ranks = ranks_from_scores(rrf_scores)

            append_result(
                rows, app_name, q.query_id, q.review_text,
                "BGE-ZS-NOPREFIX-TITLE",
                dense_ranks, id_to_idx, gids,
            )
            append_result(
                rows, app_name, q.query_id, q.review_text,
                "BM25-TITLE",
                bm25_ranks, id_to_idx, gids,
            )
            append_result(
                rows, app_name, q.query_id, q.review_text,
                "RRF60-BGE-ZS+BM25-TITLE",
                rrf_ranks, id_to_idx, gids,
            )

        del doc_vecs, query_vecs, dense_scores, bm25
        gc.collect()
        torch.cuda.empty_cache()

    per_query = pd.DataFrame(rows)

    if len(per_query) != 82 * 3:
        raise AssertionError(
            f"Expected 246 result rows, got {len(per_query)}"
        )

    summary_rows = []

    for (app_name, model), g in per_query.groupby(
        ["app", "model"], sort=True
    ):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append(
            {
                "app": app_name,
                "model": model,
                "n": len(g),
                "MRR": float(np.mean(1.0 / ranks)),
                "H@1": float(np.mean(ranks <= 1)),
                "H@5": float(np.mean(ranks <= 5)),
                "H@10": float(np.mean(ranks <= 10)),
                "median_gold_rank": float(np.median(ranks)),
            }
        )

    for model, g in per_query.groupby("model", sort=True):
        ranks = g["best_gold_rank"].to_numpy(dtype=float)
        summary_rows.append(
            {
                "app": "POOLED",
                "model": model,
                "n": len(g),
                "MRR": float(np.mean(1.0 / ranks)),
                "H@1": float(np.mean(ranks <= 1)),
                "H@5": float(np.mean(ranks <= 5)),
                "H@10": float(np.mean(ranks <= 10)),
                "median_gold_rank": float(np.median(ranks)),
            }
        )

    summary = pd.DataFrame(summary_rows)

    # Pairwise rank movement: RRF vs BGE.
    p = per_query[
        per_query["model"].isin(
            ["BGE-ZS-NOPREFIX-TITLE", "RRF60-BGE-ZS+BM25-TITLE"]
        )
    ].pivot(
        index=["app", "query_id"],
        columns="model",
        values="best_gold_rank",
    ).reset_index()

    b = p["BGE-ZS-NOPREFIX-TITLE"].to_numpy(dtype=int)
    r = p["RRF60-BGE-ZS+BM25-TITLE"].to_numpy(dtype=int)

    movement = {
        "queries": int(len(p)),
        "rank_improved": int(np.sum(r < b)),
        "rank_worsened": int(np.sum(r > b)),
        "rank_unchanged": int(np.sum(r == b)),
        "moved_into_top1": int(np.sum((b > 1) & (r <= 1))),
        "moved_out_of_top1": int(np.sum((b <= 1) & (r > 1))),
        "moved_into_top10": int(np.sum((b > 10) & (r <= 10))),
        "moved_out_of_top10": int(np.sum((b <= 10) & (r > 10))),
    }

    per_query.to_csv(
        OUTPUT / "rrf_known_positive_per_query.csv",
        index=False,
    )
    summary.to_csv(
        OUTPUT / "rrf_known_positive_summary.csv",
        index=False,
    )
    p.to_csv(
        OUTPUT / "rrf_vs_bge_paired_ranks.csv",
        index=False,
    )

    result = {
        "evaluation": "Häring known-positive full-corpus rank diagnostic",
        "rrf_k": RRF_K,
        "systems": [
            "BGE-ZS-NOPREFIX-TITLE",
            "BM25-TITLE",
            "RRF60-BGE-ZS+BM25-TITLE",
        ],
        "summary": summary.to_dict("records"),
        "rrf_vs_bge_movement": movement,
        "interpretation_guard": (
            "Original Häring labels are pool-incomplete. This measures rank "
            "of originally known-positive issues, not complete semantic relevance."
        ),
    }

    (OUTPUT / "RRF_SUMMARY.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    archive = "/tmp/haring_bge_bm25_rrf_results"
    shutil.make_archive(archive, "zip", root_dir=str(OUTPUT))
    shutil.copy2(
        archive + ".zip",
        OUTPUT / "haring_bge_bm25_rrf_results.zip",
    )

    volume.commit()

    print("\n" + "=" * 100)
    print("HÄRING BGE-ZS + BM25 RRF RESULTS")
    print("=" * 100)
    print(
        summary[
            ["app", "model", "n", "MRR", "H@1", "H@10", "median_gold_rank"]
        ].to_string(index=False),
        flush=True,
    )
    print("\nRRF vs BGE movement:")
    print(json.dumps(movement, indent=2), flush=True)

    return result


@app.local_entrypoint()
def main():
    evaluate.remote()
    print(
        "\nSaved on Modal volume:\n"
        "/vol/haring_bge_bm25_rrf/haring_bge_bm25_rrf_results.zip"
    )
