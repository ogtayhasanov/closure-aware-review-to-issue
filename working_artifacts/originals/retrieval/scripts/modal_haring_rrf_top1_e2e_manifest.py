#!/usr/bin/env python3
"""
MODAL: Export the frozen RRF60 top-1 issue for the 82 Häring known-positive reviews.

This reruns EXACTLY the already-evaluated retrieval configuration:
  BGE-ZS-NOPREFIX-TITLE
  BM25-TITLE
  RRF k=60
  full corpus per app
  title-only retrieval documents

No tuning. No generation.

Output on Modal volume:
  /vol/haring_rrf_top1_e2e/
      rrf_top1_manifest_82.csv
      rrf_top1_retrieval_summary.json
      haring_rrf_top1_e2e_manifest.zip
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

import modal

APP_NAME = "haring-rrf-top1-e2e"
VOLUME_NAME = "splade-data"

VOL = Path("/vol")
OUTPUT = VOL / "haring_rrf_top1_e2e"

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
        dest = Path("/tmp/haring_rrf_top1_pack")
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

        df = df[
            (df["_issue_id"] != "")
            & (df["_title"] != "")
        ].copy()

        if df["_issue_id"].duplicated().any():
            df = df.drop_duplicates("_issue_id", keep="first")

        df = df.reset_index(drop=True)

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
            "frame": df,
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


def raw_field(row, names):
    for name in names:
        if name in row.index:
            value = clean(row.get(name))
            if value:
                return value
    return ""


@app.function(
    image=image,
    volumes={"/vol": volume},
    gpu="A100-40GB",
    cpu=8.0,
    memory=32768,
    timeout=60 * 60,
)
def export_top1():
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

    manifest_rows = []
    rank_rows = []

    for app_name in APP_CONFIG:
        qf = positive[positive["app"] == app_name].reset_index(drop=True)
        corpus = corpora[app_name]

        ids = corpus["ids"]
        titles = corpus["titles"]
        frame = corpus["frame"]
        id_to_idx = {iid: i for i, iid in enumerate(ids)}

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
            rrf_order = np.argsort(-rrf_scores, kind="stable")
            rrf_ranks = np.empty(len(rrf_order), dtype=np.int64)
            rrf_ranks[rrf_order] = np.arange(1, len(rrf_order) + 1)

            top_idx = int(rrf_order[0])
            top_id = ids[top_idx]
            top_row = frame.iloc[top_idx]

            gold_ranks = [int(rrf_ranks[id_to_idx[g]]) for g in gids]
            best_gold_rank = min(gold_ranks)
            hit1 = int(top_id in gids)

            rank_rows.append(
                {
                    "app": app_name,
                    "query_id": str(q.query_id),
                    "best_gold_rank": best_gold_rank,
                    "reciprocal_rank": 1.0 / best_gold_rank,
                    "hit_at_1": int(best_gold_rank <= 1),
                    "hit_at_5": int(best_gold_rank <= 5),
                    "hit_at_10": int(best_gold_rank <= 10),
                }
            )

            manifest_rows.append(
                {
                    "app": app_name,
                    "query_id": str(q.query_id),
                    "review_text": q.review_text,
                    "known_positive_issue_ids": ";".join(gids),
                    "known_positive_hit_at_1": bool(hit1),
                    "best_known_positive_rank": int(best_gold_rank),
                    "rrf_top1_issue_id": top_id,
                    "rrf_top1_score": float(rrf_scores[top_idx]),
                    "bge_rank_of_rrf_top1": int(dense_ranks[top_idx]),
                    "bm25_rank_of_rrf_top1": int(bm25_ranks[top_idx]),
                    "retrieval_model": "RRF60-BGE-ZS+BM25-TITLE",
                    "retrieval_document_representation": "issue_title_only",
                    "issue_title": clean(top_row.get("_title")),
                    "issue_body": raw_field(
                        top_row,
                        ["body", "description", "text", "issue_body", "content"],
                    ),
                    "status": raw_field(top_row, ["status", "state"]),
                    "resolution": raw_field(top_row, ["resolution"]),
                    "labels": raw_field(top_row, ["labels"]),
                    "closed_at": raw_field(top_row, ["closed_at"]),
                    "cf_last_resolved": raw_field(
                        top_row,
                        ["cf_last_resolved", "last_resolved"],
                    ),
                    "history": raw_field(top_row, ["history"]),
                    "issue_url": raw_field(
                        top_row,
                        ["html_url", "url", "issue_url", "web_url"],
                    ),
                    "issue_number": raw_field(
                        top_row,
                        ["number", "issue_number", "bug_id", "ticket_id"],
                    ),
                }
            )

        del doc_vecs, query_vecs, dense_scores, bm25
        gc.collect()
        torch.cuda.empty_cache()

    manifest = pd.DataFrame(manifest_rows)
    ranks = pd.DataFrame(rank_rows)

    if len(manifest) != 82 or manifest["query_id"].isna().any():
        raise AssertionError(f"Bad manifest size: {len(manifest)}")

    app_counts = manifest.groupby("app").size().astype(int).to_dict()
    if app_counts != {"Firefox": 28, "Nextcloud": 33, "VLC": 21}:
        raise AssertionError(f"Unexpected app counts: {app_counts}")

    hit1 = int(manifest["known_positive_hit_at_1"].astype(bool).sum())
    h10 = int(ranks["hit_at_10"].sum())
    mrr = float(ranks["reciprocal_rank"].mean())
    median_rank = float(ranks["best_gold_rank"].median())

    # Hard reproduction guards from the completed RRF experiment.
    if hit1 != 16:
        raise AssertionError(f"Expected RRF known-positive Hit@1 = 16, got {hit1}")
    if h10 != 42:
        raise AssertionError(f"Expected RRF H@10 = 42, got {h10}")
    if abs(mrr - 0.289097) > 5e-6:
        raise AssertionError(f"Expected pooled MRR≈0.289097, got {mrr}")
    if median_rank != 9.0:
        raise AssertionError(f"Expected median known-positive rank=9.0, got {median_rank}")

    manifest_path = OUTPUT / "rrf_top1_manifest_82.csv"
    ranks_path = OUTPUT / "rrf_top1_rank_check_82.csv"

    manifest.to_csv(manifest_path, index=False)
    ranks.to_csv(ranks_path, index=False)

    summary = {
        "evaluation": "Häring known-positive full-corpus RRF top-1 export",
        "retriever": "RRF60-BGE-ZS+BM25-TITLE",
        "rrf_k": RRF_K,
        "document_representation": "title-only",
        "rows": 82,
        "known_positive_hit_at_1": hit1,
        "known_positive_hit_at_1_rate": hit1 / 82,
        "hit_at_10": h10 / 82,
        "MRR": mrr,
        "median_known_positive_rank": median_rank,
        "benchmark_caveat": (
            "Häring judgments are pool-incomplete. A non-hit at top-1 is not "
            "proof of semantic irrelevance."
        ),
    }

    (OUTPUT / "rrf_top1_retrieval_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    archive_base = "/tmp/haring_rrf_top1_e2e_manifest"
    shutil.make_archive(archive_base, "zip", root_dir=str(OUTPUT))
    shutil.copy2(
        archive_base + ".zip",
        OUTPUT / "haring_rrf_top1_e2e_manifest.zip",
    )

    volume.commit()

    print("\n" + "=" * 100)
    print("RRF TOP-1 E2E MANIFEST EXPORTED")
    print("=" * 100)
    print("Rows:", len(manifest))
    print("Known-positive Hit@1:", f"{hit1}/82 = {hit1/82:.6f}")
    print("H@10:", f"{h10}/82 = {h10/82:.6f}")
    print("MRR:", f"{mrr:.6f}")
    print("Median known-positive rank:", median_rank)
    print("\nSaved on Modal volume:")
    print(" ", manifest_path)
    print(" ", OUTPUT / "haring_rrf_top1_e2e_manifest.zip")

    return summary


@app.local_entrypoint()
def main():
    export_top1.remote()
    print(
        "\nDownload with:\n"
        "modal volume get -e main splade-data "
        "haring_rrf_top1_e2e/haring_rrf_top1_e2e_manifest.zip "
        r"C:\Users\Ogtay\Downloads\haring_rrf_top1_e2e_manifest.zip"
    )
