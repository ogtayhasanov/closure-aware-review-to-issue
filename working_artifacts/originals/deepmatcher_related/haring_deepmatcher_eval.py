# ============================================================
# HARING / DEEPMATCHER-STYLE REPLICATION + MODERN EXTENSION
# ============================================================
#
# EXPECTS an existing `apps` dict in the Kaggle notebook.
#
# Required per app:
#   query_texts
#   document_texts
#   gold_sets
#
# Strongly preferred:
#   query_ids
#   document_ids
#   document_titles
#
# If document_titles is missing, the script extracts the first
# non-empty line from document_texts. This matches our current
# "title\n\nbody\n\nLabels" issue formatting.
#
# Outputs:
#   haring_summary.csv
#   haring_per_query_exact_ranks.csv
#   haring_top3_annotation_sheet.csv
#   haring_detected_schema.json
#
# Primary comparison:
#   - DeepMatcher-DistilBERT-NOUNS / TITLE
#   - BGE-Base / TITLE and FULL
#   - SPLADE-ZS / TITLE and FULL
#   - MPNet / TITLE and FULL
#   - BM25 / TITLE and FULL
#
# NO TRAINING.
# NO DEEPMATCHER DATA USED FOR MODEL SELECTION.
# ============================================================

import os
import sys
import re
import gc
import json
import math
import random
import subprocess
from pathlib import Path
from collections import defaultdict

# Kaggle normally has most of these. Install missing lightweight deps.
subprocess.run(
    [
        sys.executable, "-m", "pip", "install", "-q",
        "sentence-transformers",
        "rank-bm25",
        "nltk",
    ],
    check=True,
)

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

import nltk
from nltk import pos_tag
from nltk.tokenize import TreebankWordTokenizer

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from transformers import (
    AutoTokenizer,
    AutoModel,
    AutoModelForMaskedLM,
)

# NLTK changed tagger resource names across versions.
for resource in [
    "averaged_perceptron_tagger_eng",
    "averaged_perceptron_tagger",
]:
    try:
        nltk.download(resource, quiet=True)
    except Exception:
        pass

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
OUTPUT = Path("/kaggle/working/haring_deepmatcher_eval")
OUTPUT.mkdir(parents=True, exist_ok=True)

print("DEVICE:", DEVICE)

if "apps" not in globals():
    raise RuntimeError(
        "This script expects the existing `apps` dict from your DeepMatcher "
        "dataset-building/evaluation notebook. Run that cell first, then this one."
    )

# ============================================================
# 0. Schema adaptation
# ============================================================

def first_present(d, keys, required=False):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k], k
    if required:
        raise KeyError(f"None of these keys are present: {keys}. Available: {list(d.keys())}")
    return None, None


def clean_text(x):
    return "" if x is None else str(x).strip()


def extract_title_from_full(text):
    """
    Current corpus formatting is usually:
        title
        <blank>
        body
        <blank>
        Labels: ...
    so the first non-empty line is the title.
    """
    s = clean_text(text)
    if not s:
        return ""
    lines = [x.strip() for x in s.splitlines() if x.strip()]
    if not lines:
        return ""
    title = lines[0]
    title = re.sub(r"^\s*(title|summary)\s*:\s*", "", title, flags=re.I)
    return title.strip()


def normalize_doc_ids(values, n):
    if values is None:
        return [f"DOCIDX-{i}" for i in range(n)]
    out = [str(x) for x in list(values)]
    if len(out) != n:
        raise ValueError(f"document_ids length {len(out)} != n_documents {n}")
    return out


def normalize_query_ids(values, n):
    if values is None:
        return [f"Q{i}" for i in range(n)]
    out = [str(x) for x in list(values)]
    if len(out) != n:
        raise ValueError(f"query_ids length {len(out)} != n_queries {n}")
    return out


def normalize_gold_sets(raw_gold, doc_ids):
    """
    Supports:
      - list[set[int]]
      - list[list[int]]
      - list[set[str]] / IDs
      - scalar int/string per query
    Returns list[set[int]] aligned to candidate indices.
    """
    id_to_idx = {str(d): i for i, d in enumerate(doc_ids)}
    n_docs = len(doc_ids)

    out = []
    for g in raw_gold:
        if isinstance(g, (set, list, tuple, np.ndarray)):
            vals = list(g)
        else:
            vals = [g]

        idxs = set()
        for x in vals:
            # Integer candidate index.
            if isinstance(x, (int, np.integer)) and 0 <= int(x) < n_docs:
                idxs.add(int(x))
                continue

            # String that might be an ID.
            sx = str(x)
            if sx in id_to_idx:
                idxs.add(id_to_idx[sx])
                continue

            # Numeric-looking string may also be a candidate index.
            try:
                ix = int(float(sx))
                if 0 <= ix < n_docs:
                    idxs.add(ix)
                    continue
            except Exception:
                pass

        out.append(idxs)

    return out


prepared = {}
schema = {}

for app_name, d in apps.items():
    query_texts, qk = first_present(
        d,
        ["query_texts", "queries", "review_texts", "reviews"],
        required=True,
    )
    full_docs, dk = first_present(
        d,
        ["document_texts", "documents", "doc_texts", "issue_texts"],
        required=True,
    )
    raw_gold, gk = first_present(
        d,
        ["gold_sets", "golds", "gold", "gold_indices"],
        required=True,
    )

    query_ids_raw, qidk = first_present(
        d,
        ["query_ids", "review_ids", "ids"],
        required=False,
    )
    doc_ids_raw, didk = first_present(
        d,
        ["document_ids", "doc_ids", "issue_ids", "candidate_ids"],
        required=False,
    )
    titles_raw, tk = first_present(
        d,
        ["document_titles", "doc_titles", "issue_titles", "titles"],
        required=False,
    )

    query_texts = [clean_text(x) for x in list(query_texts)]
    full_docs = [clean_text(x) for x in list(full_docs)]

    n_q = len(query_texts)
    n_d = len(full_docs)

    query_ids = normalize_query_ids(query_ids_raw, n_q)
    doc_ids = normalize_doc_ids(doc_ids_raw, n_d)

    if titles_raw is None:
        titles = [extract_title_from_full(x) for x in full_docs]
        title_source = "first_nonempty_line_from_document_texts"
    else:
        titles = [clean_text(x) for x in list(titles_raw)]
        if len(titles) != n_d:
            raise ValueError(
                f"{app_name}: document_titles length {len(titles)} != docs {n_d}"
            )
        title_source = tk

    gold_sets = normalize_gold_sets(raw_gold, doc_ids)
    evaluable = [i for i, g in enumerate(gold_sets) if len(g) > 0]

    prepared[app_name] = {
        "query_texts": query_texts,
        "query_ids": query_ids,
        "full_docs": full_docs,
        "titles": titles,
        "doc_ids": doc_ids,
        "gold_sets": gold_sets,
        "evaluable": evaluable,
    }

    schema[app_name] = {
        "query_key": qk,
        "document_key": dk,
        "gold_key": gk,
        "query_id_key": qidk,
        "document_id_key": didk,
        "title_key_or_fallback": title_source,
        "n_queries": n_q,
        "n_documents": n_d,
        "n_evaluable": len(evaluable),
        "n_missing_gold": n_q - len(evaluable),
    }

    print(
        f"{app_name:12s} queries={n_q:4d} docs={n_d:6d} "
        f"evaluable={len(evaluable):4d} titles={title_source}",
        flush=True,
    )

(OUTPUT / "haring_detected_schema.json").write_text(
    json.dumps(schema, indent=2),
    encoding="utf-8",
)

# ============================================================
# 1. Evaluation
# ============================================================

def rank_metrics(scores, gold_sets, evaluable_indices=None):
    if evaluable_indices is None:
        evaluable_indices = list(range(len(gold_sets)))

    ranks = []
    per_query = []

    for qi in evaluable_indices:
        gold = gold_sets[qi]
        order = np.argsort(-scores[qi], kind="stable")

        rank = None
        for r, di in enumerate(order, start=1):
            if int(di) in gold:
                rank = r
                break

        if rank is None:
            rank = len(order) + 1

        ranks.append(rank)
        per_query.append((qi, rank))

    ranks_arr = np.asarray(ranks, dtype=np.int64)
    n = len(ranks_arr)

    if n == 0:
        return {
            "n_queries": 0,
            "H@1": np.nan,
            "H@3": np.nan,
            "H@5": np.nan,
            "H@10": np.nan,
            "H@100": np.nan,
            "MRR": np.nan,
            "NDCG@10": np.nan,
            "median_gold_rank": np.nan,
        }, per_query

    rr = 1.0 / ranks_arr
    ndcg10 = np.where(
        ranks_arr <= 10,
        1.0 / np.log2(ranks_arr + 1),
        0.0,
    )

    return {
        "n_queries": int(n),
        "H@1": float(np.mean(ranks_arr <= 1)),
        "H@3": float(np.mean(ranks_arr <= 3)),
        "H@5": float(np.mean(ranks_arr <= 5)),
        "H@10": float(np.mean(ranks_arr <= 10)),
        "H@100": float(np.mean(ranks_arr <= 100)),
        "MRR": float(np.mean(rr)),
        "NDCG@10": float(np.mean(ndcg10)),
        "median_gold_rank": float(np.median(ranks_arr)),
    }, per_query


def add_top3_rows(
    rows,
    app_name,
    model_name,
    corpus_mode,
    scores,
    pdata,
):
    for qi in pdata["evaluable"]:
        order = np.argsort(-scores[qi], kind="stable")[:3]
        gold = pdata["gold_sets"][qi]

        for rank, di in enumerate(order, start=1):
            rows.append({
                "app": app_name,
                "model": model_name,
                "corpus_mode": corpus_mode,
                "query_index": qi,
                "query_id": pdata["query_ids"][qi],
                "review_text": pdata["query_texts"][qi],
                "retrieved_rank": rank,
                "candidate_index": int(di),
                "candidate_id": pdata["doc_ids"][int(di)],
                "candidate_title": pdata["titles"][int(di)],
                "score": float(scores[qi, int(di)]),
                "is_exact_linked_gold": int(int(di) in gold),

                # Fill these later during Häring-style human judging:
                "same_feature": "",
                "same_behavior": "",
                "semantic_relevant_yes_no": "",
                "annotator_notes": "",
            })


summary_rows = []
per_query_rows = []
top3_rows = []


def record_result(app_name, model_name, corpus_mode, scores, pdata):
    metrics, pq = rank_metrics(
        scores,
        pdata["gold_sets"],
        pdata["evaluable"],
    )

    summary_rows.append({
        "app": app_name,
        "model": model_name,
        "corpus_mode": corpus_mode,
        **metrics,
    })

    for qi, rank in pq:
        per_query_rows.append({
            "app": app_name,
            "model": model_name,
            "corpus_mode": corpus_mode,
            "query_index": qi,
            "query_id": pdata["query_ids"][qi],
            "best_exact_gold_rank": int(rank),
            "RR": 1.0 / rank,
            "H@3": int(rank <= 3),
            "H@10": int(rank <= 10),
        })

    add_top3_rows(
        top3_rows,
        app_name,
        model_name,
        corpus_mode,
        scores,
        pdata,
    )

    print(
        f"{app_name:12s} {model_name:30s} {corpus_mode:6s} "
        f"H3={metrics['H@3']:.4f} H10={metrics['H@10']:.4f} "
        f"MRR={metrics['MRR']:.4f} median={metrics['median_gold_rank']:.1f}",
        flush=True,
    )


# ============================================================
# 2. Häring / DeepMatcher-style DistilBERT noun-only vectors
# ============================================================
#
# Operational reproduction:
#   - DistilBERT contextual embeddings
#   - identify nouns using an English POS tagger
#   - mean-pool only noun token embeddings
#   - cosine similarity
#   - bug report TITLE/SUMMARY only
#
# NOTE:
# This reproduces the published mechanism, but it is not claimed
# to be byte-identical to the authors' original POS pipeline.
# ============================================================

TREEBANK = TreebankWordTokenizer()
DISTIL_NAME = "distilbert-base-uncased"


def safe_pos_tag(words):
    try:
        return pos_tag(words, lang="eng")
    except Exception:
        return pos_tag(words)


@torch.inference_mode()
def encode_distilbert_nouns(
    texts,
    tokenizer,
    model,
    batch_size=32,
    max_length=256,
):
    vectors = []
    fallback_count = 0

    for st in range(0, len(texts), batch_size):
        batch_texts = texts[st:st+batch_size]

        batch_words = []
        batch_noun_word_ids = []

        for text in batch_texts:
            words = TREEBANK.tokenize(clean_text(text))
            if not words:
                words = ["empty"]

            tags = safe_pos_tag(words)
            noun_ids = {
                i for i, (_, tag) in enumerate(tags)
                if str(tag).startswith("NN")
            }

            batch_words.append(words)
            batch_noun_word_ids.append(noun_ids)

        enc = tokenizer(
            batch_words,
            is_split_into_words=True,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )

        enc_device = {
            k: v.to(DEVICE, non_blocking=True)
            for k, v in enc.items()
        }

        out = model(**enc_device)
        hidden = out.last_hidden_state.float()

        for bi in range(len(batch_words)):
            word_ids = enc.word_ids(batch_index=bi)

            selected = []
            for ti, wid in enumerate(word_ids):
                if wid is None:
                    continue
                if wid in batch_noun_word_ids[bi]:
                    selected.append(ti)

            # If POS finds no noun or all noun tokens were truncated,
            # fall back to all content tokens so the query/document
            # still receives a vector. We report the fallback count.
            if not selected:
                fallback_count += 1
                selected = [
                    ti for ti, wid in enumerate(word_ids)
                    if wid is not None
                ]

            if not selected:
                # pathological empty case
                vec = hidden[bi, 0]
            else:
                vec = hidden[bi, selected].mean(dim=0)

            vec = torch.nn.functional.normalize(
                vec,
                p=2,
                dim=0,
            )
            vectors.append(vec.cpu())

    return torch.stack(vectors, dim=0), fallback_count


print("\n" + "=" * 90)
print("DEEPMATCHER-STYLE DISTILBERT NOUN-ONLY / TITLE-ONLY")
print("=" * 90)

distil_tok = AutoTokenizer.from_pretrained(
    DISTIL_NAME,
    use_fast=True,
)
distil_model = AutoModel.from_pretrained(
    DISTIL_NAME
).to(DEVICE).eval()

for app_name, pdata in prepared.items():
    print(f"\nEncoding DeepMatcher-style: {app_name}", flush=True)

    qv, q_fallback = encode_distilbert_nouns(
        pdata["query_texts"],
        distil_tok,
        distil_model,
        batch_size=32,
        max_length=256,
    )
    dv, d_fallback = encode_distilbert_nouns(
        pdata["titles"],
        distil_tok,
        distil_model,
        batch_size=64,
        max_length=64,
    )

    scores = (qv @ dv.T).numpy()

    print(
        f"noun-pooling fallback: queries={q_fallback}/{len(qv)}, "
        f"titles={d_fallback}/{len(dv)}"
    )

    record_result(
        app_name,
        "DeepMatcher-DistilBERT-NOUNS",
        "TITLE",
        scores,
        pdata,
    )

    del qv, dv, scores
    gc.collect()

del distil_model, distil_tok
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()


# ============================================================
# 3. Sentence-transformer baselines: BGE + MPNet
# ============================================================

@torch.inference_mode()
def st_encode(model, texts, batch_size=64, prompt=None):
    if prompt:
        texts = [prompt + x for x in texts]

    return model.encode(
        texts,
        batch_size=batch_size,
        convert_to_tensor=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).float().cpu()


ST_MODELS = [
    (
        "BGE-Base",
        "BAAI/bge-base-en-v1.5",
        "Represent this sentence for searching relevant passages: ",
    ),
    (
        "MPNet",
        "sentence-transformers/all-mpnet-base-v2",
        None,
    ),
]

for model_label, model_name, query_prompt in ST_MODELS:
    print("\n" + "=" * 90)
    print(model_label)
    print("=" * 90)

    model = SentenceTransformer(
        model_name,
        device=str(DEVICE),
    )

    for app_name, pdata in prepared.items():
        qv = st_encode(
            model,
            pdata["query_texts"],
            batch_size=64,
            prompt=query_prompt,
        )

        for mode, docs in [
            ("TITLE", pdata["titles"]),
            ("FULL", pdata["full_docs"]),
        ]:
            dv = st_encode(
                model,
                docs,
                batch_size=64,
                prompt=None,
            )
            scores = (qv @ dv.T).numpy()

            record_result(
                app_name,
                model_label,
                mode,
                scores,
                pdata,
            )

            del dv, scores
            gc.collect()

        del qv
        gc.collect()

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ============================================================
# 4. SPLADE-ZS: TITLE vs FULL
# ============================================================

SPLADE_NAME = "naver/splade-cocondenser-ensembledistil"


class Splade(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        self.model = AutoModelForMaskedLM.from_pretrained(checkpoint)

    def forward(self, tokens):
        moved = {
            k: v.to(DEVICE, non_blocking=True)
            for k, v in tokens.items()
        }
        logits = self.model(**moved).logits
        vals = (
            torch.log1p(torch.relu(logits))
            * moved["attention_mask"].unsqueeze(-1)
        )
        return torch.max(vals, dim=1).values


@torch.inference_mode()
def splade_encode(model, tokenizer, texts, batch_size=32):
    blocks = []

    use_amp = DEVICE.type == "cuda"
    amp_dtype = (
        torch.bfloat16
        if use_amp and torch.cuda.is_bf16_supported()
        else torch.float16
    )

    for st in range(0, len(texts), batch_size):
        tok = tokenizer(
            list(texts[st:st+batch_size]),
            max_length=128,
            truncation=True,
            padding=True,
            return_tensors="pt",
        )

        if use_amp:
            with torch.autocast("cuda", dtype=amp_dtype):
                v = model(tok)
        else:
            v = model(tok)

        blocks.append(v.float().cpu())

    return torch.cat(blocks, dim=0)


print("\n" + "=" * 90)
print("SPLADE-ZS")
print("=" * 90)

splade_tok = AutoTokenizer.from_pretrained(SPLADE_NAME)
splade_model = Splade(SPLADE_NAME).to(DEVICE).eval()

for app_name, pdata in prepared.items():
    qv = splade_encode(
        splade_model,
        splade_tok,
        pdata["query_texts"],
        batch_size=32,
    )

    for mode, docs in [
        ("TITLE", pdata["titles"]),
        ("FULL", pdata["full_docs"]),
    ]:
        dv = splade_encode(
            splade_model,
            splade_tok,
            docs,
            batch_size=32,
        )
        scores = (qv @ dv.T).numpy()

        record_result(
            app_name,
            "SPLADE-ZS",
            mode,
            scores,
            pdata,
        )

        del dv, scores
        gc.collect()

    del qv
    gc.collect()

del splade_model, splade_tok
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()


# ============================================================
# 5. BM25: TITLE vs FULL
# ============================================================

def bm25_tokens(text):
    return re.findall(r"[A-Za-z0-9_+-]+", clean_text(text).lower())


print("\n" + "=" * 90)
print("BM25")
print("=" * 90)

for app_name, pdata in prepared.items():
    qtok = [bm25_tokens(x) for x in pdata["query_texts"]]

    for mode, docs in [
        ("TITLE", pdata["titles"]),
        ("FULL", pdata["full_docs"]),
    ]:
        corpus_tok = [bm25_tokens(x) for x in docs]
        bm25 = BM25Okapi(corpus_tok)

        scores = np.vstack(
            [
                np.asarray(bm25.get_scores(q), dtype=np.float32)
                for q in qtok
            ]
        )

        record_result(
            app_name,
            "BM25",
            mode,
            scores,
            pdata,
        )

        del bm25, scores, corpus_tok
        gc.collect()


# ============================================================
# 6. Save outputs
# ============================================================

summary = pd.DataFrame(summary_rows)
per_query = pd.DataFrame(per_query_rows)
top3 = pd.DataFrame(top3_rows)

summary.to_csv(
    OUTPUT / "haring_summary.csv",
    index=False,
)
per_query.to_csv(
    OUTPUT / "haring_per_query_exact_ranks.csv",
    index=False,
)
top3.to_csv(
    OUTPUT / "haring_top3_annotation_sheet.csv",
    index=False,
)

# Macro-average across applications.
metric_cols = [
    "H@1",
    "H@3",
    "H@5",
    "H@10",
    "H@100",
    "MRR",
    "NDCG@10",
]

macro = (
    summary
    .groupby(["model", "corpus_mode"])[metric_cols]
    .mean()
    .reset_index()
    .sort_values(["H@3", "MRR"], ascending=False)
)

macro.to_csv(
    OUTPUT / "haring_macro_average.csv",
    index=False,
)

print("\n\n" + "=" * 105)
print("HARING / DEEPMATCHER EXPERIMENT — PER APP")
print("=" * 105)

display_cols = [
    "app",
    "model",
    "corpus_mode",
    "n_queries",
    "H@1",
    "H@3",
    "H@5",
    "H@10",
    "MRR",
    "median_gold_rank",
]

print(
    summary[display_cols]
    .sort_values(["app", "H@3", "MRR"], ascending=[True, False, False])
    .to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)

print("\n" + "=" * 105)
print("MACRO AVERAGE")
print("=" * 105)

print(
    macro.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)

# TITLE vs FULL delta for modern methods.
modern = summary[
    summary["model"].isin(["BGE-Base", "MPNet", "SPLADE-ZS", "BM25"])
].copy()

pivot = modern.pivot_table(
    index=["app", "model"],
    columns="corpus_mode",
    values=["H@3", "H@10", "MRR", "median_gold_rank"],
    aggfunc="first",
)

delta_rows = []
for (app_name, model_name), row in pivot.iterrows():
    rec = {
        "app": app_name,
        "model": model_name,
    }

    for metric in ["H@3", "H@10", "MRR"]:
        try:
            rec[f"{metric}_TITLE"] = float(row[(metric, "TITLE")])
            rec[f"{metric}_FULL"] = float(row[(metric, "FULL")])
            rec[f"{metric}_TITLE_minus_FULL"] = (
                rec[f"{metric}_TITLE"] - rec[f"{metric}_FULL"]
            )
        except Exception:
            pass

    try:
        rec["median_rank_TITLE"] = float(row[("median_gold_rank", "TITLE")])
        rec["median_rank_FULL"] = float(row[("median_gold_rank", "FULL")])
    except Exception:
        pass

    delta_rows.append(rec)

delta = pd.DataFrame(delta_rows)
delta.to_csv(
    OUTPUT / "haring_title_vs_full_delta.csv",
    index=False,
)

print("\n" + "=" * 105)
print("TITLE-ONLY vs FULL-TEXT DELTA")
print("=" * 105)

print(
    delta.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}",
    )
)

print("\nSaved outputs:")
for p in [
    OUTPUT / "haring_summary.csv",
    OUTPUT / "haring_macro_average.csv",
    OUTPUT / "haring_title_vs_full_delta.csv",
    OUTPUT / "haring_per_query_exact_ranks.csv",
    OUTPUT / "haring_top3_annotation_sheet.csv",
    OUTPUT / "haring_detected_schema.json",
]:
    print(" ", p)

print(
    "\nIMPORTANT: `haring_top3_annotation_sheet.csv` is the next-stage "
    "Häring-style human semantic-relevance sheet. Do not annotate it yet "
    "until we inspect these exact-link/title-only results."
)
