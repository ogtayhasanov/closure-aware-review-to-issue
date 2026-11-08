#!/usr/bin/env python3
"""
Frozen Häring experiment: RRF60(BGE-ZS + BM25) -> Cross-Encoder top-50 reranking.

NO TRAINING.
NO MODEL SWEEP.
NO TOP-K SWEEP.
NO SCORE INTERPOLATION.
NO QUERY EXPANSION.

Benchmark:
  - Firefox, VLC, Nextcloud only (Signal excluded)
  - 82 Häring reviews with >=1 originally human-judged positive issue
  - full issue corpus per app
  - issue TITLE ONLY
  - pool-incomplete known-positive rank diagnostic

First stage (must reproduce existing result):
  RRF2-ORIGINAL =
      1/(60 + rank_BGE-ZS)
    + 1/(60 + rank_BM25)

Expected pooled baseline:
  MRR    = 0.2890973404537107
  H@1    = 16/82 = 0.1951219512
  H@10   = 42/82 = 0.5121951220
  H@50   = 63/82 = 0.7682926829
  median = 9.0

Reranker:
  cross-encoder/ms-marco-MiniLM-L12-v2

Reranking protocol:
  - Take exactly the top 50 documents from frozen RRF.
  - Score (original review, issue title) pairs with the CE.
  - Sort ONLY those 50 by descending CE score.
  - Append original RRF ranks 51..N unchanged.
  - Evaluate the resulting full ranking.

Primary comparison:
  RRF50-CE vs RRF2-ORIGINAL

Outputs:
  /vol/haring_rrf_ce_top50/
"""

from __future__ import annotations

import json
import math
import re
import shutil
import zipfile
from pathlib import Path

import modal


# ---------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------

APP_NAME = "haring-rrf-ce-top50"
VOLUME_NAME = "splade-data"

VOL = Path("/vol")
OUTPUT = VOL / "haring_rrf_ce_top50"

BGE_MODEL = "BAAI/bge-base-en-v1.5"
CE_MODEL = "cross-encoder/ms-marco-MiniLM-L12-v2"

BGE_MAX_LENGTH = 128
CE_MAX_LENGTH = 256

RRF_K = 60
CE_TOP_K = 50

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

volume = modal.Volume.from_name(
    VOLUME_NAME,
    create_if_missing=False,
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch>=2.4,<3",
        "transformers>=4.50,<5",
        "sentence-transformers>=4,<6",
        "pandas>=2.2,<3",
        "numpy>=2,<3",
        "rank-bm25>=0.2.2,<1",
        "scipy>=1.14,<2",
    )
)


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------

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

    raise ValueError(
        f"Cannot interpret fitting_issue value: {x!r}"
    )


def first_col(df, names):
    for c in names:
        if c in df.columns:
            return c
    return None


def tokenize(text):
    return re.findall(
        r"[a-z0-9]+",
        clean(text).lower(),
    )


def prepare_root():
    data_dir = VOL / "haring_data"
    pack_zip = VOL / "haring_modal_pack.zip"

    if data_dir.exists():
        return data_dir

    if pack_zip.exists():
        dest = Path("/tmp/haring_rrf_ce_pack")

        if dest.exists():
            shutil.rmtree(dest)

        dest.mkdir(parents=True)

        with zipfile.ZipFile(pack_zip) as zf:
            zf.extractall(dest)

        return dest

    raise FileNotFoundError(
        "Expected /vol/haring_data or /vol/haring_modal_pack.zip"
    )


def find_coding(root):
    candidates = list(
        root.rglob("*Coding*Resolved*.csv")
    )

    if not candidates:
        candidates = [
            p
            for p in root.rglob("*.csv")
            if "coding" in p.name.lower()
            and "resolved" in p.name.lower()
        ]

    if not candidates:
        raise FileNotFoundError(
            "Häring coding CSV not found"
        )

    candidates.sort(
        key=lambda p: len(str(p))
    )

    return candidates[0]


# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------

class BGE:
    def __init__(self, model_name, device):
        from transformers import (
            AutoModel,
            AutoTokenizer,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name
        )

        self.model = (
            AutoModel.from_pretrained(model_name)
            .to(device)
            .eval()
        )

        self.device = device

    def encode(
        self,
        texts,
        batch_size=256,
    ):
        import torch
        import torch.nn.functional as F

        blocks = []

        with torch.inference_mode():
            for start in range(
                0,
                len(texts),
                batch_size,
            ):
                batch = list(
                    texts[
                        start:start + batch_size
                    ]
                )

                toks = self.tokenizer(
                    batch,
                    max_length=BGE_MAX_LENGTH,
                    truncation=True,
                    padding=True,
                    return_tensors="pt",
                )

                toks = {
                    k: v.to(
                        self.device,
                        non_blocking=True,
                    )
                    for k, v in toks.items()
                }

                dtype = (
                    torch.bfloat16
                    if torch.cuda.is_bf16_supported()
                    else torch.float16
                )

                with torch.autocast(
                    "cuda",
                    dtype=dtype,
                ):
                    out = self.model(**toks)
                    emb = (
                        out.last_hidden_state[:, 0]
                    )

                blocks.append(
                    F.normalize(
                        emb.float(),
                        p=2,
                        dim=1,
                    ).cpu()
                )

        return torch.cat(
            blocks,
            dim=0,
        )


# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------

def load_data(root):
    import pandas as pd

    coding_path = find_coding(root)

    coding = pd.read_csv(
        coding_path,
        low_memory=False,
    ).copy()

    required = {
        "app",
        "user_feedback_id",
        "issue_id",
        "fitting_issue",
    }

    missing = required - set(coding.columns)

    if missing:
        raise KeyError(
            f"Coding file missing: {sorted(missing)}"
        )

    review_col = first_col(
        coding,
        [
            "user_feedback",
            "review_text",
            "review",
            "content",
            "feedback_text",
        ],
    )

    if review_col is None:
        raise KeyError(
            "No recognized review text column"
        )

    package_to_app = {
        cfg["package"]: app_name
        for app_name, cfg
        in APP_CONFIG.items()
    }

    coding = coding[
        coding["app"]
        .astype(str)
        .isin(package_to_app)
    ].copy()

    if len(coding) != 450:
        raise AssertionError(
            "Expected exactly 450 non-Signal "
            f"Häring judgments, got {len(coding)}"
        )

    coding["_app_name"] = (
        coding["app"]
        .astype(str)
        .map(package_to_app)
    )

    coding["_query_id"] = (
        coding["user_feedback_id"]
        .map(norm_id)
    )

    coding["_issue_id"] = (
        coding["issue_id"]
        .map(norm_id)
    )

    coding["_review_text"] = (
        coding[review_col]
        .map(clean)
    )

    coding["_relevant"] = (
        coding["fitting_issue"]
        .map(bool_value)
    )

    positive_rows = (
        coding[
            coding["_relevant"]
        ].copy()
    )

    gold_ids = (
        positive_rows
        .groupby(
            [
                "_app_name",
                "_query_id",
            ]
        )["_issue_id"]
        .agg(
            lambda s:
            tuple(
                dict.fromkeys(
                    map(str, s)
                )
            )
        )
        .to_dict()
    )

    queries = (
        coding
        .drop_duplicates(
            [
                "_app_name",
                "_query_id",
            ]
        )[
            [
                "_app_name",
                "_query_id",
                "_review_text",
            ]
        ]
        .rename(
            columns={
                "_app_name": "app",
                "_query_id": "query_id",
                "_review_text": "review_text",
            }
        )
        .reset_index(drop=True)
    )

    positive = queries[
        queries.apply(
            lambda r:
            (
                str(r["app"]),
                str(r["query_id"]),
            )
            in gold_ids,
            axis=1,
        )
    ].copy()

    expected_counts = {
        "Firefox": 28,
        "Nextcloud": 33,
        "VLC": 21,
    }

    observed_counts = (
        positive
        .groupby("app")["query_id"]
        .nunique()
        .to_dict()
    )

    if observed_counts != expected_counts:
        raise AssertionError(
            "Known-positive query counts changed. "
            f"Expected {expected_counts}, "
            f"got {observed_counts}"
        )

    if len(positive) != 82:
        raise AssertionError(
            f"Expected 82 positive queries, got {len(positive)}"
        )

    corpora = {}

    for app_name, cfg in APP_CONFIG.items():
        path = root / cfg["filename"]

        if not path.exists():
            raise FileNotFoundError(path)

        df = pd.read_csv(
            path,
            low_memory=False,
        ).copy()

        if len(df) != cfg["raw_rows"]:
            raise AssertionError(
                f"{app_name}: expected "
                f"{cfg['raw_rows']} raw rows, "
                f"got {len(df)}"
            )

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

        if id_col is None:
            raise KeyError(
                f"{app_name}: no issue ID column"
            )

        if title_col is None:
            raise KeyError(
                f"{app_name}: no issue title column"
            )

        df["_issue_id"] = (
            df[id_col]
            .map(norm_id)
        )

        df["_title"] = (
            df[title_col]
            .map(clean)
        )

        df = df[
            (df["_issue_id"] != "")
            & (df["_title"] != "")
        ].copy()

        if df[
            "_issue_id"
        ].duplicated().any():
            df = (
                df
                .drop_duplicates(
                    "_issue_id",
                    keep="first",
                )
                .copy()
            )

        known_ids = set(
            coding.loc[
                coding["_app_name"]
                == app_name,
                "_issue_id",
            ]
        )

        absent = (
            known_ids
            - set(df["_issue_id"])
        )

        if absent:
            raise AssertionError(
                f"{app_name}: judged issue IDs "
                f"missing from corpus: "
                f"{list(absent)[:10]}"
            )

        corpora[app_name] = {
            "ids": (
                df["_issue_id"]
                .astype(str)
                .tolist()
            ),
            "titles": (
                df["_title"]
                .tolist()
            ),
        }

        print(
            f"{app_name:10s}: "
            f"{len(df):,} candidate issue titles",
            flush=True,
        )

    return (
        positive.reset_index(drop=True),
        gold_ids,
        corpora,
    )


# ---------------------------------------------------------------------
# Ranking helpers
# ---------------------------------------------------------------------

def ranks_from_scores(scores):
    import numpy as np

    order = np.argsort(
        -scores,
        kind="stable",
    )

    ranks = np.empty(
        len(order),
        dtype=np.int64,
    )

    ranks[order] = np.arange(
        1,
        len(order) + 1,
    )

    return ranks


def order_to_ranks(order):
    import numpy as np

    ranks = np.empty(
        len(order),
        dtype=np.int64,
    )

    ranks[order] = np.arange(
        1,
        len(order) + 1,
    )

    return ranks


def append_query_result(
    output_rows,
    app_name,
    query_id,
    review_text,
    system,
    ranks,
    id_to_idx,
    gold_issue_ids,
):
    gold_ranks = [
        int(
            ranks[
                id_to_idx[g]
            ]
        )
        for g in gold_issue_ids
    ]

    best = min(gold_ranks)

    output_rows.append(
        {
            "app": app_name,
            "query_id": str(query_id),
            "review_text": review_text,
            "system": system,
            "known_positive_issue_ids": (
                ";".join(gold_issue_ids)
            ),
            "all_known_positive_ranks": (
                ";".join(
                    map(
                        str,
                        sorted(gold_ranks),
                    )
                )
            ),
            "best_gold_rank": int(best),
            "reciprocal_rank": float(
                1.0 / best
            ),
            "hit_at_1": int(
                best <= 1
            ),
            "hit_at_5": int(
                best <= 5
            ),
            "hit_at_10": int(
                best <= 10
            ),
            "hit_at_50": int(
                best <= 50
            ),
        }
    )


# ---------------------------------------------------------------------
# Exact / paired statistics
# ---------------------------------------------------------------------

def exact_mcnemar_p(
    candidate_only,
    baseline_only,
):
    n = int(
        candidate_only
        + baseline_only
    )

    if n == 0:
        return 1.0

    k = min(
        int(candidate_only),
        int(baseline_only),
    )

    lower_tail = (
        sum(
            math.comb(n, i)
            for i in range(
                k + 1
            )
        )
        / (2 ** n)
    )

    return min(
        1.0,
        2.0 * lower_tail,
    )


def sign_test_two_sided(
    improved,
    worsened,
):
    n = int(
        improved
        + worsened
    )

    if n == 0:
        return 1.0

    k = min(
        int(improved),
        int(worsened),
    )

    lower_tail = (
        sum(
            math.comb(n, i)
            for i in range(
                k + 1
            )
        )
        / (2 ** n)
    )

    return min(
        1.0,
        2.0 * lower_tail,
    )


def holm_adjust(p_values):
    import numpy as np

    p = np.asarray(
        p_values,
        dtype=float,
    )

    m = len(p)

    order = np.argsort(p)

    sorted_adjusted = (
        np.empty(
            m,
            dtype=float,
        )
    )

    running = 0.0

    for rank, idx in enumerate(order):
        adjusted_here = min(
            1.0,
            (m - rank) * p[idx],
        )

        running = max(
            running,
            adjusted_here,
        )

        sorted_adjusted[
            rank
        ] = running

    adjusted = np.empty(
        m,
        dtype=float,
    )

    for rank, idx in enumerate(order):
        adjusted[idx] = (
            sorted_adjusted[
                rank
            ]
        )

    return adjusted


# ---------------------------------------------------------------------
# Remote experiment
# ---------------------------------------------------------------------

@app.function(
    image=image,
    volumes={
        "/vol": volume,
    },
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

    from rank_bm25 import (
        BM25Okapi,
    )

    from scipy.stats import (
        wilcoxon,
    )

    from sentence_transformers import (
        CrossEncoder,
    )

    volume.reload()

    root = prepare_root()

    (
        positive,
        gold_ids,
        corpora,
    ) = load_data(root)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    OUTPUT.mkdir(
        parents=True,
    )

    print(
        "\nGPU:",
        torch.cuda.get_device_name(0),
        flush=True,
    )

    print(
        "BGE model:",
        BGE_MODEL,
        flush=True,
    )

    print(
        "Cross-encoder:",
        CE_MODEL,
        flush=True,
    )

    print(
        f"Frozen CE cutoff: top {CE_TOP_K}",
        flush=True,
    )

    bge = BGE(
        BGE_MODEL,
        torch.device("cuda"),
    )

    ce = CrossEncoder(
        CE_MODEL,
        device="cuda",
        max_length=CE_MAX_LENGTH,
    )

    result_rows = []
    candidate_rows = []

    # -------------------------------------------------------------
    # Per-app retrieval then top-50 reranking
    # -------------------------------------------------------------

    for app_name in APP_CONFIG:
        qf = (
            positive[
                positive["app"]
                == app_name
            ]
            .reset_index(drop=True)
        )

        ids = (
            corpora[
                app_name
            ]["ids"]
        )

        titles = (
            corpora[
                app_name
            ]["titles"]
        )

        id_to_idx = {
            iid: i
            for i, iid
            in enumerate(ids)
        }

        print(
            f"\n{app_name}: "
            f"encoding {len(titles):,} titles",
            flush=True,
        )

        document_vectors = bge.encode(
            titles,
            batch_size=256,
        )

        review_texts = (
            qf["review_text"]
            .map(clean)
            .tolist()
        )

        query_vectors = bge.encode(
            review_texts,
            batch_size=64,
        )

        dense_scores = (
            query_vectors
            @ document_vectors.T
        ).numpy()

        bm25 = BM25Okapi(
            [
                tokenize(title)
                for title in titles
            ]
        )

        for qi, q in enumerate(
            qf.itertuples(
                index=False
            )
        ):
            review = (
                review_texts[qi]
            )

            gids = gold_ids[
                (
                    app_name,
                    str(q.query_id),
                )
            ]

            # -----------------------------------------------------
            # Frozen first stage
            # -----------------------------------------------------

            bge_ranks = (
                ranks_from_scores(
                    dense_scores[qi]
                )
            )

            bm25_scores = (
                np.asarray(
                    bm25.get_scores(
                        tokenize(review)
                    ),
                    dtype=np.float64,
                )
            )

            bm25_ranks = (
                ranks_from_scores(
                    bm25_scores
                )
            )

            rrf_scores = (
                1.0
                / (
                    RRF_K
                    + bge_ranks.astype(
                        np.float64
                    )
                )
                + 1.0
                / (
                    RRF_K
                    + bm25_ranks.astype(
                        np.float64
                    )
                )
            )

            rrf_order = np.argsort(
                -rrf_scores,
                kind="stable",
            )

            rrf_ranks = (
                order_to_ranks(
                    rrf_order
                )
            )

            if len(
                rrf_order
            ) < CE_TOP_K:
                raise AssertionError(
                    f"{app_name}: corpus smaller "
                    f"than CE_TOP_K={CE_TOP_K}"
                )

            # Save baseline result.
            append_query_result(
                output_rows=result_rows,
                app_name=app_name,
                query_id=q.query_id,
                review_text=review,
                system="RRF2-ORIGINAL",
                ranks=rrf_ranks,
                id_to_idx=id_to_idx,
                gold_issue_ids=gids,
            )

            # -----------------------------------------------------
            # Cross-encoder reranks exactly RRF top 50
            # -----------------------------------------------------

            top50_idx = (
                rrf_order[
                    :CE_TOP_K
                ]
            )

            ce_pairs = [
                (
                    review,
                    titles[int(doc_idx)],
                )
                for doc_idx
                in top50_idx
            ]

            ce_scores = np.asarray(
                ce.predict(
                    ce_pairs,
                    batch_size=128,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ),
                dtype=np.float64,
            ).reshape(-1)

            if len(
                ce_scores
            ) != CE_TOP_K:
                raise AssertionError(
                    "Cross-encoder returned "
                    f"{len(ce_scores)} scores "
                    f"for {CE_TOP_K} pairs"
                )

            if not np.isfinite(
                ce_scores
            ).all():
                raise AssertionError(
                    "Cross-encoder produced "
                    "non-finite scores"
                )

            ce_local_order = (
                np.argsort(
                    -ce_scores,
                    kind="stable",
                )
            )

            reranked_top50 = (
                top50_idx[
                    ce_local_order
                ]
            )

            # IMPORTANT:
            # Documents outside the top 50 preserve their exact original
            # RRF order. Therefore CE can only reorder candidates it saw.
            final_order = (
                np.concatenate(
                    [
                        reranked_top50,
                        rrf_order[
                            CE_TOP_K:
                        ],
                    ]
                )
            )

            if len(
                np.unique(final_order)
            ) != len(ids):
                raise AssertionError(
                    "Final ranking is not "
                    "a permutation of corpus"
                )

            ce_ranks = (
                order_to_ranks(
                    final_order
                )
            )

            # Membership in top 50 MUST be invariant.
            baseline_top50 = set(
                map(
                    int,
                    rrf_order[
                        :CE_TOP_K
                    ],
                )
            )

            ce_top50 = set(
                map(
                    int,
                    final_order[
                        :CE_TOP_K
                    ],
                )
            )

            if (
                baseline_top50
                != ce_top50
            ):
                raise AssertionError(
                    "CE changed top-50 membership; "
                    "protocol violation"
                )

            append_query_result(
                output_rows=result_rows,
                app_name=app_name,
                query_id=q.query_id,
                review_text=review,
                system="RRF50-CE",
                ranks=ce_ranks,
                id_to_idx=id_to_idx,
                gold_issue_ids=gids,
            )

            # Candidate-level audit.
            ce_rank_within50 = (
                np.empty(
                    CE_TOP_K,
                    dtype=np.int64,
                )
            )

            ce_rank_within50[
                ce_local_order
            ] = np.arange(
                1,
                CE_TOP_K + 1,
            )

            gold_set = set(gids)

            for local_idx, doc_idx in enumerate(
                top50_idx
            ):
                doc_idx = int(
                    doc_idx
                )

                candidate_rows.append(
                    {
                        "app": app_name,
                        "query_id": str(
                            q.query_id
                        ),
                        "review_text": review,
                        "issue_id": (
                            ids[
                                doc_idx
                            ]
                        ),
                        "issue_title": (
                            titles[
                                doc_idx
                            ]
                        ),
                        "is_original_known_positive": (
                            int(
                                ids[
                                    doc_idx
                                ]
                                in gold_set
                            )
                        ),
                        "rrf_rank": (
                            int(
                                rrf_ranks[
                                    doc_idx
                                ]
                            )
                        ),
                        "bge_rank": (
                            int(
                                bge_ranks[
                                    doc_idx
                                ]
                            )
                        ),
                        "bm25_rank": (
                            int(
                                bm25_ranks[
                                    doc_idx
                                ]
                            )
                        ),
                        "rrf_score": (
                            float(
                                rrf_scores[
                                    doc_idx
                                ]
                            )
                        ),
                        "ce_score": (
                            float(
                                ce_scores[
                                    local_idx
                                ]
                            )
                        ),
                        "ce_rank_within_rrf_top50": (
                            int(
                                ce_rank_within50[
                                    local_idx
                                ]
                            )
                        ),
                    }
                )

        del (
            document_vectors,
            query_vectors,
            dense_scores,
            bm25,
        )

        gc.collect()
        torch.cuda.empty_cache()

    # -------------------------------------------------------------
    # Results
    # -------------------------------------------------------------

    per_query = pd.DataFrame(
        result_rows
    )

    candidates = pd.DataFrame(
        candidate_rows
    )

    if len(per_query) != 164:
        raise AssertionError(
            "Expected 164 per-query rows "
            "(82 x 2 systems), got "
            f"{len(per_query)}"
        )

    if len(candidates) != (
        82 * CE_TOP_K
    ):
        raise AssertionError(
            "Expected 4100 CE candidate rows, "
            f"got {len(candidates)}"
        )

    per_query.to_csv(
        OUTPUT
        / "rrf_ce_per_query.csv",
        index=False,
    )

    candidates.to_csv(
        OUTPUT
        / "rrf_top50_ce_scores.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Summary metrics
    # -------------------------------------------------------------

    summary_rows = []

    for (
        app_name,
        system,
    ), g in (
        per_query
        .groupby(
            [
                "app",
                "system",
            ],
            sort=True,
        )
    ):
        ranks = (
            g[
                "best_gold_rank"
            ]
            .to_numpy(
                dtype=float
            )
        )

        summary_rows.append(
            {
                "app": app_name,
                "system": system,
                "n": len(g),
                "MRR": float(
                    np.mean(
                        1.0 / ranks
                    )
                ),
                "H@1": float(
                    np.mean(
                        ranks <= 1
                    )
                ),
                "H@5": float(
                    np.mean(
                        ranks <= 5
                    )
                ),
                "H@10": float(
                    np.mean(
                        ranks <= 10
                    )
                ),
                "H@50": float(
                    np.mean(
                        ranks <= 50
                    )
                ),
                "median_gold_rank": float(
                    np.median(
                        ranks
                    )
                ),
            }
        )

    for system, g in (
        per_query
        .groupby(
            "system",
            sort=True,
        )
    ):
        ranks = (
            g[
                "best_gold_rank"
            ]
            .to_numpy(
                dtype=float
            )
        )

        summary_rows.append(
            {
                "app": "POOLED",
                "system": system,
                "n": len(g),
                "MRR": float(
                    np.mean(
                        1.0 / ranks
                    )
                ),
                "H@1": float(
                    np.mean(
                        ranks <= 1
                    )
                ),
                "H@5": float(
                    np.mean(
                        ranks <= 5
                    )
                ),
                "H@10": float(
                    np.mean(
                        ranks <= 10
                    )
                ),
                "H@50": float(
                    np.mean(
                        ranks <= 50
                    )
                ),
                "median_gold_rank": float(
                    np.median(
                        ranks
                    )
                ),
            }
        )

    summary = pd.DataFrame(
        summary_rows
    )

    summary.to_csv(
        OUTPUT
        / "rrf_ce_summary.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Hard first-stage reproduction guard
    # -------------------------------------------------------------

    base = summary[
        (
            summary["app"]
            == "POOLED"
        )
        & (
            summary["system"]
            == "RRF2-ORIGINAL"
        )
    ]

    if len(base) != 1:
        raise AssertionError(
            "Missing pooled RRF2-ORIGINAL row"
        )

    base = base.iloc[0]

    expected = {
        "MRR": (
            0.2890973404537107
        ),
        "H@1": (
            0.1951219512195122
        ),
        "H@10": (
            0.5121951219512195
        ),
        "H@50": (
            0.7682926829268293
        ),
        "median_gold_rank": 9.0,
    }

    for metric in [
        "MRR",
        "H@1",
        "H@10",
        "H@50",
    ]:
        if abs(
            float(
                base[
                    metric
                ]
            )
            - expected[
                metric
            ]
        ) > 5e-6:
            raise AssertionError(
                "RRF baseline reproduction "
                f"failed for {metric}: "
                f"expected "
                f"{expected[metric]}, "
                f"got {base[metric]}"
            )

    if float(
        base[
            "median_gold_rank"
        ]
    ) != 9.0:
        raise AssertionError(
            "RRF baseline reproduction "
            "failed for median rank: "
            f"{base['median_gold_rank']}"
        )

    # CE top-50 reranking cannot change H@50.
    ce_pooled = summary[
        (
            summary["app"]
            == "POOLED"
        )
        & (
            summary["system"]
            == "RRF50-CE"
        )
    ].iloc[0]

    if abs(
        float(
            ce_pooled[
                "H@50"
            ]
        )
        - float(
            base[
                "H@50"
            ]
        )
    ) > 1e-12:
        raise AssertionError(
            "CE changed H@50, but top-50 "
            "membership should be frozen"
        )

    # -------------------------------------------------------------
    # One pre-specified paired comparison
    # -------------------------------------------------------------

    candidate = (
        per_query[
            per_query["system"]
            == "RRF50-CE"
        ]
        .set_index(
            [
                "app",
                "query_id",
            ]
        )
        .sort_index()
    )

    baseline = (
        per_query[
            per_query["system"]
            == "RRF2-ORIGINAL"
        ]
        .set_index(
            [
                "app",
                "query_id",
            ]
        )
        .sort_index()
    )

    if not candidate.index.equals(
        baseline.index
    ):
        raise AssertionError(
            "Paired query indices do not match"
        )

    paired_rows = []

    metric_specs = [
        (
            "reciprocal_rank",
            "reciprocal_rank",
        ),
        (
            "hit_at_1",
            "hit_at_1",
        ),
        (
            "hit_at_10",
            "hit_at_10",
        ),
    ]

    for metric_name, field in metric_specs:
        x = candidate[
            field
        ].to_numpy(
            dtype=float
        )

        y = baseline[
            field
        ].to_numpy(
            dtype=float
        )

        diff = x - y

        if np.allclose(
            diff,
            0,
        ):
            w_stat = 0.0
            w_p = 1.0
        else:
            w = wilcoxon(
                x,
                y,
                alternative="two-sided",
                zero_method="wilcox",
                method="auto",
            )

            w_stat = float(
                w.statistic
            )

            w_p = float(
                w.pvalue
            )

        row = {
            "comparison": (
                "RRF50-CE_vs_RRF2-ORIGINAL"
            ),
            "metric": metric_name,
            "n": len(x),
            "candidate_mean": float(
                np.mean(x)
            ),
            "baseline_mean": float(
                np.mean(y)
            ),
            "mean_difference": float(
                np.mean(diff)
            ),
            "candidate_higher": int(
                np.sum(
                    diff > 0
                )
            ),
            "baseline_higher": int(
                np.sum(
                    diff < 0
                )
            ),
            "ties": int(
                np.sum(
                    diff == 0
                )
            ),
            "wilcoxon_statistic": (
                w_stat
            ),
            "wilcoxon_p": (
                w_p
            ),
            "candidate_only_successes": (
                np.nan
            ),
            "baseline_only_successes": (
                np.nan
            ),
            "exact_mcnemar_p": (
                np.nan
            ),
        }

        if field in {
            "hit_at_1",
            "hit_at_10",
        }:
            xb = x.astype(bool)
            yb = y.astype(bool)

            candidate_only = int(
                np.sum(
                    xb
                    & ~yb
                )
            )

            baseline_only = int(
                np.sum(
                    ~xb
                    & yb
                )
            )

            row[
                "candidate_only_successes"
            ] = candidate_only

            row[
                "baseline_only_successes"
            ] = baseline_only

            row[
                "exact_mcnemar_p"
            ] = exact_mcnemar_p(
                candidate_only,
                baseline_only,
            )

        paired_rows.append(row)

    paired = pd.DataFrame(
        paired_rows
    )

    # Only three pre-specified Wilcoxon tests in this experiment.
    paired[
        "wilcoxon_p_holm_3tests"
    ] = holm_adjust(
        paired[
            "wilcoxon_p"
        ].to_numpy()
    )

    paired.to_csv(
        OUTPUT
        / "rrf_ce_paired_tests.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Rank movement
    # -------------------------------------------------------------

    baseline_rank = (
        baseline[
            "best_gold_rank"
        ]
        .to_numpy(
            dtype=int
        )
    )

    candidate_rank = (
        candidate[
            "best_gold_rank"
        ]
        .to_numpy(
            dtype=int
        )
    )

    improved = int(
        np.sum(
            candidate_rank
            < baseline_rank
        )
    )

    worsened = int(
        np.sum(
            candidate_rank
            > baseline_rank
        )
    )

    unchanged = int(
        np.sum(
            candidate_rank
            == baseline_rank
        )
    )

    movement = pd.DataFrame(
        [
            {
                "comparison": (
                    "RRF50-CE_vs_RRF2-ORIGINAL"
                ),
                "n": 82,
                "improved": improved,
                "worsened": worsened,
                "unchanged": unchanged,
                "two_sided_sign_test_p": (
                    sign_test_two_sided(
                        improved,
                        worsened,
                    )
                ),
                "baseline_median_rank": (
                    float(
                        np.median(
                            baseline_rank
                        )
                    )
                ),
                "candidate_median_rank": (
                    float(
                        np.median(
                            candidate_rank
                        )
                    )
                ),
                "moved_into_top1": int(
                    np.sum(
                        (
                            baseline_rank
                            > 1
                        )
                        & (
                            candidate_rank
                            <= 1
                        )
                    )
                ),
                "moved_out_of_top1": int(
                    np.sum(
                        (
                            baseline_rank
                            <= 1
                        )
                        & (
                            candidate_rank
                            > 1
                        )
                    )
                ),
                "moved_into_top10": int(
                    np.sum(
                        (
                            baseline_rank
                            > 10
                        )
                        & (
                            candidate_rank
                            <= 10
                        )
                    )
                ),
                "moved_out_of_top10": int(
                    np.sum(
                        (
                            baseline_rank
                            <= 10
                        )
                        & (
                            candidate_rank
                            > 10
                        )
                    )
                ),
            }
        ]
    )

    movement.to_csv(
        OUTPUT
        / "rrf_ce_rank_movement.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Conditional top-50 diagnostic (not a separate experiment)
    # -------------------------------------------------------------

    within50_mask = (
        baseline_rank
        <= CE_TOP_K
    )

    conditional = {
        "queries_with_known_positive_in_rrf_top50": (
            int(
                np.sum(
                    within50_mask
                )
            )
        ),
        "total_queries": 82,
        "candidate_recall_at_50": (
            float(
                np.mean(
                    within50_mask
                )
            )
        ),
        "baseline_hit1_within_reachable_63": (
            float(
                np.mean(
                    baseline_rank[
                        within50_mask
                    ]
                    <= 1
                )
            )
        ),
        "ce_hit1_within_reachable_63": (
            float(
                np.mean(
                    candidate_rank[
                        within50_mask
                    ]
                    <= 1
                )
            )
        ),
        "baseline_mrr_within_reachable_63": (
            float(
                np.mean(
                    1.0
                    / baseline_rank[
                        within50_mask
                    ]
                )
            )
        ),
        "ce_mrr_within_reachable_63": (
            float(
                np.mean(
                    1.0
                    / candidate_rank[
                        within50_mask
                    ]
                )
            )
        ),
    }

    (
        OUTPUT
        / "rrf_ce_conditional_top50.json"
    ).write_text(
        json.dumps(
            conditional,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------------------
    # Protocol + archive
    # -------------------------------------------------------------

    protocol = {
        "experiment": (
            "Frozen RRF top-50 "
            "cross-encoder reranking"
        ),
        "external_apps": [
            "Firefox",
            "VLC",
            "Nextcloud",
        ],
        "signal_excluded": True,
        "queries": 82,
        "first_stage": (
            "RRF60(BGE-ZS original review "
            "+ BM25 original review)"
        ),
        "bge_model": BGE_MODEL,
        "rrf_k": RRF_K,
        "ce_model": CE_MODEL,
        "ce_top_k": CE_TOP_K,
        "ce_input": (
            "original review + issue title"
        ),
        "ce_max_length": (
            CE_MAX_LENGTH
        ),
        "document_representation": (
            "issue title only"
        ),
        "post_top50_order": (
            "original RRF ranks 51+ unchanged"
        ),
        "score_interpolation": False,
        "model_sweep": False,
        "cutoff_sweep": False,
        "parameter_tuning": False,
        "primary_comparison": (
            "RRF50-CE vs RRF2-ORIGINAL"
        ),
        "primary_metrics": [
            "MRR",
            "H@1",
            "H@10",
        ],
        "multiple_test_correction": (
            "Holm over 3 pre-specified "
            "paired Wilcoxon tests"
        ),
        "label_caveat": (
            "Häring labels are pool-incomplete; "
            "metrics track originally "
            "human-judged known-positive "
            "issue ranks, not complete "
            "semantic relevance."
        ),
    }

    (
        OUTPUT
        / "protocol.json"
    ).write_text(
        json.dumps(
            protocol,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = {
        "protocol": protocol,
        "summary": (
            summary.to_dict(
                "records"
            )
        ),
        "paired_tests": (
            paired.to_dict(
                "records"
            )
        ),
        "rank_movement": (
            movement.to_dict(
                "records"
            )
        ),
        "conditional_top50": (
            conditional
        ),
        "baseline_reproduction": {
            "MRR": float(
                base[
                    "MRR"
                ]
            ),
            "H@1": float(
                base[
                    "H@1"
                ]
            ),
            "H@10": float(
                base[
                    "H@10"
                ]
            ),
            "H@50": float(
                base[
                    "H@50"
                ]
            ),
            "median_gold_rank": (
                float(
                    base[
                        "median_gold_rank"
                    ]
                )
            ),
        },
    }

    (
        OUTPUT
        / "RUN_SUMMARY.json"
    ).write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    archive_base = (
        "/tmp/"
        "haring_rrf_ce_top50_results"
    )

    shutil.make_archive(
        archive_base,
        "zip",
        root_dir=str(OUTPUT),
    )

    shutil.copy2(
        archive_base + ".zip",
        OUTPUT
        / "haring_rrf_ce_top50_results.zip",
    )

    volume.commit()

    # -------------------------------------------------------------
    # Terminal report
    # -------------------------------------------------------------

    print(
        "\n"
        + "=" * 112
    )

    print(
        "HÄRING RRF60 -> CROSS-ENCODER "
        "TOP-50 RESULTS"
    )

    print(
        "=" * 112
    )

    print(
        "\nPOOLED SUMMARY"
    )

    print(
        summary[
            summary["app"]
            == "POOLED"
        ][
            [
                "system",
                "n",
                "MRR",
                "H@1",
                "H@10",
                "H@50",
                "median_gold_rank",
            ]
        ]
        .to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nPAIRED TESTS"
    )

    print(
        paired[
            [
                "comparison",
                "metric",
                "candidate_mean",
                "baseline_mean",
                "mean_difference",
                "candidate_higher",
                "baseline_higher",
                "ties",
                "wilcoxon_p",
                "wilcoxon_p_holm_3tests",
                "candidate_only_successes",
                "baseline_only_successes",
                "exact_mcnemar_p",
            ]
        ]
        .to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nRANK MOVEMENT"
    )

    print(
        movement
        .to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nTOP-50 CANDIDATE REACHABILITY"
    )

    print(
        json.dumps(
            conditional,
            indent=2,
        ),
        flush=True,
    )

    print(
        "\nSaved on Modal volume:"
    )

    print(
        "/vol/haring_rrf_ce_top50/"
        "haring_rrf_ce_top50_results.zip",
        flush=True,
    )

    return result


# ---------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------

@app.local_entrypoint()
def main():
    result = evaluate.remote()

    print(
        "\nREMOTE RUN COMPLETE."
    )

    print(
        "Baseline reproduction:"
    )

    print(
        json.dumps(
            result[
                "baseline_reproduction"
            ],
            indent=2,
        )
    )

    print(
        "\nDownload results with:"
    )

    print(
        "modal volume get -e main "
        "splade-data "
        "haring_rrf_ce_top50/"
        "haring_rrf_ce_top50_results.zip "
        r"C:\Users\Ogtay\Downloads"
        r"\haring_rrf_ce_top50_results.zip"
    )
