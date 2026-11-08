#!/usr/bin/env python3
"""
Häring confidence-aware abstention diagnostic for the frozen RRF retriever.

PURPOSE
-------
Ask whether we can identify when the final RRF top-1 issue is more likely to
coincide with an originally human-judged positive Häring issue, so that a
downstream response system can abstain on uncertain retrievals.

IMPORTANT INTERPRETATION
------------------------
Häring judgments are pool-incomplete. Therefore:
  - "benchmark_confirmed_hit1 = 1" means the RRF top-1 is one of the
    originally human-judged positive issues.
  - "benchmark_confirmed_hit1 = 0" means NOT CONFIRMED by that pool.
    It does NOT prove the retrieved issue is semantically wrong.

NO TRAINING.
NO CONFIDENCE MODEL.
NO THRESHOLD TUNING.
NO USE OF LABELS TO BUILD CONFIDENCE SCORES.
NO QUERY EXPANSION.
NO CROSS-ENCODER.

Frozen retrieval:
  - BGE-ZS: BAAI/bge-base-en-v1.5
  - BM25
  - SPLADE-ZS: naver/splade-cocondenser-ensembledistil
  - Final retriever remains RRF60(BGE-ZS + BM25)
  - title-only documents
  - Firefox, VLC, Nextcloud only; Signal excluded
  - 82 reviews with >=1 originally judged positive issue

PRIMARY CONFIDENCE SIGNAL
-------------------------
base_ranker_corroboration_rr =
    mean(
        1 / rank_BGE(RRF_top1),
        1 / rank_BM25(RRF_top1),
        1 / rank_SPLADE(RRF_top1)
    )

This is equal-weight, label-free corroboration of the *actual RRF top issue*.

SECONDARY DIAGNOSTICS
---------------------
1) rrf_relative_margin = (RRF_score_1 - RRF_score_2) / abs(RRF_score_1)
2) mean pairwise top-10 Jaccard across BGE/BM25/SPLADE
3) exact top-1 support count for the RRF top issue among BGE/BM25/SPLADE
4) top-3 and top-10 support counts for the RRF top issue

SELECTIVE EVALUATION
--------------------
For each continuous confidence signal, report target coverages:
  100%, 75%, 50%, 25%

To avoid arbitrary tie-breaking, the score threshold is the Nth score and ALL
ties at that threshold are accepted. Realized coverage can therefore exceed
the target slightly.

For categorical exact-top1 support, report natural thresholds:
  support >= 1, support >= 2, support = 3

At every operating point report:
  - accepted queries
  - realized coverage
  - benchmark-confirmed top-1 hits among accepted queries
  - benchmark-confirmed Hit@1 among accepted queries
  - fraction of all 16 confirmed RRF top-1 hits retained

Outputs:
  /vol/haring_rrf_abstention/
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

APP_NAME = "haring-rrf-abstention"
VOLUME_NAME = "splade-data"

VOL = Path("/vol")
OUTPUT = VOL / "haring_rrf_abstention"

BGE_MODEL = "BAAI/bge-base-en-v1.5"
SPLADE_MODEL = "naver/splade-cocondenser-ensembledistil"

MAX_LENGTH = 128
RRF_K = 60

TARGET_COVERAGES = [1.00, 0.75, 0.50, 0.25]

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
        "pandas>=2.2,<3",
        "numpy>=2,<3",
        "rank-bm25>=0.2.2,<1",
        "scipy>=1.14,<2",
        "sentencepiece>=0.2,<1",
    )
)


# ---------------------------------------------------------------------
# Generic helpers
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
        f"Cannot parse fitting_issue value {x!r}"
    )


def first_col(df, names):
    for col in names:
        if col in df.columns:
            return col
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
        dest = Path(
            "/tmp/haring_rrf_abstention_pack"
        )

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


def jaccard(a, b):
    a = set(a)
    b = set(b)

    union = a | b

    if not union:
        return 1.0

    return len(a & b) / len(union)


# ---------------------------------------------------------------------
# BGE
# ---------------------------------------------------------------------

class BGE:
    def __init__(
        self,
        model_name,
        device,
    ):
        from transformers import (
            AutoModel,
            AutoTokenizer,
        )

        self.tokenizer = (
            AutoTokenizer
            .from_pretrained(
                model_name
            )
        )

        self.model = (
            AutoModel
            .from_pretrained(
                model_name
            )
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
                        start:start
                        + batch_size
                    ]
                )

                toks = (
                    self.tokenizer(
                        batch,
                        max_length=MAX_LENGTH,
                        truncation=True,
                        padding=True,
                        return_tensors="pt",
                    )
                )

                toks = {
                    k: v.to(
                        self.device,
                        non_blocking=True,
                    )
                    for k, v
                    in toks.items()
                }

                amp_dtype = (
                    torch.bfloat16
                    if (
                        self.device.type == "cuda"
                        and torch.cuda.is_bf16_supported()
                    )
                    else torch.float16
                )

                with torch.autocast(
                    "cuda",
                    dtype=amp_dtype,
                    enabled=(
                        self.device.type
                        == "cuda"
                    ),
                ):
                    out = self.model(
                        **toks
                    )

                    emb = (
                        out
                        .last_hidden_state[
                            :, 0
                        ]
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
# SPLADE-ZS
# ---------------------------------------------------------------------

class SpladeZS:
    """
    Standard SPLADE representation:
      max_t attention_mask_t * log(1 + ReLU(masked_lm_logit_tj))
    """

    def __init__(
        self,
        model_name,
        device,
    ):
        from transformers import (
            AutoModelForMaskedLM,
            AutoTokenizer,
        )

        self.tokenizer = (
            AutoTokenizer
            .from_pretrained(
                model_name
            )
        )

        self.model = (
            AutoModelForMaskedLM
            .from_pretrained(
                model_name
            )
            .to(device)
            .eval()
        )

        if hasattr(
            self.model.config,
            "use_cache",
        ):
            self.model.config.use_cache = False

        self.device = device

    def encode(
        self,
        texts,
        batch_size=16,
        out_dtype=None,
    ):
        import torch

        if out_dtype is None:
            out_dtype = torch.float16

        blocks = []

        with torch.inference_mode():
            for start in range(
                0,
                len(texts),
                batch_size,
            ):
                batch = list(
                    texts[
                        start:start
                        + batch_size
                    ]
                )

                toks = (
                    self.tokenizer(
                        batch,
                        max_length=MAX_LENGTH,
                        truncation=True,
                        padding=True,
                        return_tensors="pt",
                    )
                )

                toks = {
                    k: v.to(
                        self.device,
                        non_blocking=True,
                    )
                    for k, v
                    in toks.items()
                }

                amp_dtype = (
                    torch.bfloat16
                    if torch.cuda.is_bf16_supported()
                    else torch.float16
                )

                with torch.autocast(
                    "cuda",
                    dtype=amp_dtype,
                ):
                    logits = (
                        self.model(
                            **toks
                        ).logits
                    )

                    values = (
                        torch.log1p(
                            torch.relu(
                                logits
                            )
                        )
                        * toks[
                            "attention_mask"
                        ].unsqueeze(-1)
                    )

                    vectors = (
                        torch.max(
                            values,
                            dim=1,
                        ).values
                    )

                blocks.append(
                    vectors
                    .detach()
                    .to(out_dtype)
                    .cpu()
                )

                del (
                    toks,
                    logits,
                    values,
                    vectors,
                )

                if (
                    self.device.type
                    == "cuda"
                ):
                    torch.cuda.empty_cache()

        return torch.cat(
            blocks,
            dim=0,
        )


# ---------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------

def load_data(root):
    import pandas as pd

    coding_path = find_coding(
        root
    )

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

    missing = (
        required
        - set(
            coding.columns
        )
    )

    if missing:
        raise KeyError(
            "Coding CSV missing "
            f"{sorted(missing)}"
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
        .isin(
            package_to_app
        )
    ].copy()

    if len(coding) != 450:
        raise AssertionError(
            "Expected 450 non-Signal "
            f"judgments, got {len(coding)}"
        )

    coding["_app_name"] = (
        coding["app"]
        .astype(str)
        .map(
            package_to_app
        )
    )

    coding["_query_id"] = (
        coding[
            "user_feedback_id"
        ].map(norm_id)
    )

    coding["_issue_id"] = (
        coding[
            "issue_id"
        ].map(norm_id)
    )

    coding["_review_text"] = (
        coding[
            review_col
        ].map(clean)
    )

    coding["_relevant"] = (
        coding[
            "fitting_issue"
        ].map(bool_value)
    )

    relevant = coding[
        coding[
            "_relevant"
        ]
    ].copy()

    gold_ids = (
        relevant
        .groupby(
            [
                "_app_name",
                "_query_id",
            ]
        )[
            "_issue_id"
        ]
        .agg(
            lambda s:
            tuple(
                dict.fromkeys(
                    map(
                        str,
                        s,
                    )
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
        .reset_index(
            drop=True
        )
    )

    positive = queries[
        queries.apply(
            lambda row:
            (
                str(
                    row["app"]
                ),
                str(
                    row[
                        "query_id"
                    ]
                ),
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

    observed = (
        positive
        .groupby(
            "app"
        )[
            "query_id"
        ]
        .nunique()
        .to_dict()
    )

    if (
        observed
        != expected_counts
    ):
        raise AssertionError(
            "Positive-query counts changed. "
            f"Expected {expected_counts}, "
            f"got {observed}"
        )

    if len(positive) != 82:
        raise AssertionError(
            f"Expected 82 queries, got {len(positive)}"
        )

    corpora = {}

    for app_name, cfg in APP_CONFIG.items():
        path = (
            root
            / cfg[
                "filename"
            ]
        )

        if not path.exists():
            raise FileNotFoundError(
                path
            )

        df = pd.read_csv(
            path,
            low_memory=False,
        ).copy()

        if (
            len(df)
            != cfg[
                "raw_rows"
            ]
        ):
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

        if (
            id_col is None
            or title_col is None
        ):
            raise KeyError(
                f"{app_name}: missing "
                "issue ID/title column"
            )

        df["_issue_id"] = (
            df[
                id_col
            ].map(norm_id)
        )

        df["_title"] = (
            df[
                title_col
            ].map(clean)
        )

        df = df[
            (
                df[
                    "_issue_id"
                ]
                != ""
            )
            & (
                df[
                    "_title"
                ]
                != ""
            )
        ].copy()

        if (
            df[
                "_issue_id"
            ]
            .duplicated()
            .any()
        ):
            df = (
                df
                .drop_duplicates(
                    "_issue_id",
                    keep="first",
                )
                .copy()
            )

        judged = set(
            coding.loc[
                coding[
                    "_app_name"
                ]
                == app_name,
                "_issue_id",
            ]
        )

        absent = (
            judged
            - set(
                df[
                    "_issue_id"
                ]
            )
        )

        if absent:
            raise AssertionError(
                f"{app_name}: judged IDs "
                "missing from corpus: "
                f"{list(absent)[:10]}"
            )

        corpora[
            app_name
        ] = {
            "ids": (
                df[
                    "_issue_id"
                ]
                .astype(str)
                .tolist()
            ),
            "titles": (
                df[
                    "_title"
                ]
                .tolist()
            ),
        }

        print(
            f"{app_name:10s}: "
            f"{len(df):,} issue titles",
            flush=True,
        )

    return (
        positive
        .reset_index(
            drop=True
        ),
        gold_ids,
        corpora,
    )


# ---------------------------------------------------------------------
# Ranking helpers
# ---------------------------------------------------------------------

def order_and_ranks(
    scores,
):
    import numpy as np

    order = np.argsort(
        -scores,
        kind="stable",
    )

    ranks = np.empty(
        len(order),
        dtype=np.int64,
    )

    ranks[
        order
    ] = np.arange(
        1,
        len(order)
        + 1,
    )

    return (
        order,
        ranks,
    )


def best_gold_rank(
    ranks,
    id_to_idx,
    gold_issue_ids,
):
    return min(
        int(
            ranks[
                id_to_idx[
                    issue_id
                ]
            ]
        )
        for issue_id
        in gold_issue_ids
    )


# ---------------------------------------------------------------------
# Selective evaluation
# ---------------------------------------------------------------------

def coverage_curve(
    frame,
    score_col,
    score_name,
    target_coverages,
    total_confirmed_hits,
):
    """
    Higher score = higher confidence.

    Tie policy:
      Determine the rank position corresponding to the target coverage,
      then accept every query whose score >= the score at that position.
      Thus tied confidence values are never split using gold labels or
      arbitrary query ordering.
    """
    import numpy as np
    import pandas as pd

    scores = (
        frame[
            score_col
        ]
        .astype(float)
        .to_numpy()
    )

    if not np.isfinite(
        scores
    ).all():
        raise AssertionError(
            f"Non-finite values in {score_col}"
        )

    sorted_scores = (
        np.sort(
            scores
        )[
            ::-1
        ]
    )

    n = len(frame)

    rows = []

    for target in (
        target_coverages
    ):
        target_n = max(
            1,
            min(
                n,
                int(
                    math.floor(
                        target
                        * n
                        + 0.5
                    )
                ),
            ),
        )

        threshold = float(
            sorted_scores[
                target_n
                - 1
            ]
        )

        accepted = frame[
            frame[
                score_col
            ].astype(float)
            >= threshold
        ].copy()

        hits = int(
            accepted[
                "benchmark_confirmed_hit1"
            ]
            .astype(int)
            .sum()
        )

        rows.append(
            {
                "confidence_signal": (
                    score_name
                ),
                "target_coverage": (
                    float(
                        target
                    )
                ),
                "threshold_inclusive": (
                    threshold
                ),
                "accepted_queries": (
                    int(
                        len(
                            accepted
                        )
                    )
                ),
                "abstained_queries": (
                    int(
                        n
                        - len(
                            accepted
                        )
                    )
                ),
                "realized_coverage": (
                    float(
                        len(
                            accepted
                        )
                        / n
                    )
                ),
                "confirmed_hits_accepted": (
                    hits
                ),
                "confirmed_hit1_among_accepted": (
                    float(
                        hits
                        / len(
                            accepted
                        )
                    )
                ),
                "confirmed_hits_retained_fraction": (
                    float(
                        hits
                        / total_confirmed_hits
                    )
                ),
                "confirmed_hits_abstained": (
                    int(
                        total_confirmed_hits
                        - hits
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def categorical_support_table(
    frame,
    total_confirmed_hits,
):
    import pandas as pd

    rows = []

    conditions = [
        (
            "rrf_top1_exact_support>=1",
            frame[
                "rrf_top1_exact_support_count"
            ]
            >= 1,
        ),
        (
            "rrf_top1_exact_support>=2",
            frame[
                "rrf_top1_exact_support_count"
            ]
            >= 2,
        ),
        (
            "rrf_top1_exact_support=3",
            frame[
                "rrf_top1_exact_support_count"
            ]
            == 3,
        ),
        (
            "all_three_base_top1_same",
            frame[
                "all_three_base_top1_same"
            ]
            .astype(bool),
        ),
    ]

    n = len(
        frame
    )

    for label, mask in conditions:
        accepted = frame[
            mask
        ].copy()

        hits = int(
            accepted[
                "benchmark_confirmed_hit1"
            ]
            .astype(int)
            .sum()
        )

        rows.append(
            {
                "rule": label,
                "accepted_queries": int(
                    len(
                        accepted
                    )
                ),
                "realized_coverage": (
                    float(
                        len(
                            accepted
                        )
                        / n
                    )
                ),
                "confirmed_hits_accepted": (
                    hits
                ),
                "confirmed_hit1_among_accepted": (
                    float(
                        hits
                        / len(
                            accepted
                        )
                    )
                    if len(
                        accepted
                    )
                    else float(
                        "nan"
                    )
                ),
                "confirmed_hits_retained_fraction": (
                    float(
                        hits
                        / total_confirmed_hits
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ---------------------------------------------------------------------
# Remote analysis
# ---------------------------------------------------------------------

@app.function(
    image=image,
    volumes={
        "/vol": volume,
    },
    gpu="A100-40GB",
    cpu=8.0,
    memory=65536,
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

    volume.reload()

    root = prepare_root()

    (
        positive,
        gold_ids,
        corpora,
    ) = load_data(
        root
    )

    if OUTPUT.exists():
        shutil.rmtree(
            OUTPUT
        )

    OUTPUT.mkdir(
        parents=True
    )

    device = torch.device(
        "cuda"
    )

    print(
        "\nGPU:",
        torch.cuda.get_device_name(
            0
        ),
        flush=True,
    )

    print(
        "Final retriever:"
        " RRF60(BGE-ZS + BM25)",
        flush=True,
    )

    print(
        "Confidence-only third ranker:"
        f" {SPLADE_MODEL}",
        flush=True,
    )

    bge = BGE(
        BGE_MODEL,
        device,
    )

    splade = SpladeZS(
        SPLADE_MODEL,
        device,
    )

    rows = []

    # -------------------------------------------------------------
    # Compute the three base rankings and frozen RRF.
    # Gold is NOT referenced anywhere in confidence feature creation.
    # -------------------------------------------------------------

    for app_name in APP_CONFIG:
        qf = (
            positive[
                positive[
                    "app"
                ]
                == app_name
            ]
            .reset_index(
                drop=True
            )
        )

        ids = (
            corpora[
                app_name
            ][
                "ids"
            ]
        )

        titles = (
            corpora[
                app_name
            ][
                "titles"
            ]
        )

        id_to_idx = {
            issue_id: idx
            for idx, issue_id
            in enumerate(
                ids
            )
        }

        reviews = (
            qf[
                "review_text"
            ]
            .map(clean)
            .tolist()
        )

        print(
            f"\n{app_name}: "
            "BGE encoding...",
            flush=True,
        )

        bge_docs = bge.encode(
            titles,
            batch_size=256,
        )

        bge_queries = bge.encode(
            reviews,
            batch_size=64,
        )

        bge_scores_matrix = (
            bge_queries
            @ bge_docs.T
        ).numpy()

        print(
            f"{app_name}: "
            "BM25 indexing...",
            flush=True,
        )

        bm25 = BM25Okapi(
            [
                tokenize(
                    title
                )
                for title
                in titles
            ]
        )

        print(
            f"{app_name}: "
            "SPLADE-ZS encoding...",
            flush=True,
        )

        # Keep vectors on CPU between encoding and scoring.
        # Firefox is ~30k x vocabulary; fp16 keeps memory manageable.
        splade_docs_cpu = (
            splade.encode(
                titles,
                batch_size=16,
                out_dtype=torch.float16,
            )
        )

        splade_queries_cpu = (
            splade.encode(
                reviews,
                batch_size=16,
                out_dtype=torch.float16,
            )
        )

        # Move the document matrix once for this app.
        splade_docs_gpu = (
            splade_docs_cpu
            .to(
                device,
                non_blocking=True,
            )
        )

        for qi, q in enumerate(
            qf.itertuples(
                index=False
            )
        ):
            review = (
                reviews[
                    qi
                ]
            )

            # ---------------- BGE ----------------
            (
                bge_order,
                bge_ranks,
            ) = order_and_ranks(
                bge_scores_matrix[
                    qi
                ]
            )

            # ---------------- BM25 ----------------
            bm25_scores = (
                np.asarray(
                    bm25.get_scores(
                        tokenize(
                            review
                        )
                    ),
                    dtype=np.float64,
                )
            )

            (
                bm25_order,
                bm25_ranks,
            ) = order_and_ranks(
                bm25_scores
            )

            # ---------------- SPLADE-ZS ----------------
            splade_q = (
                splade_queries_cpu[
                    qi:qi + 1
                ]
                .to(
                    device,
                    non_blocking=True,
                )
            )

            splade_scores = (
                torch.matmul(
                    splade_q.float(),
                    splade_docs_gpu
                    .float()
                    .T,
                )
                .squeeze(0)
                .cpu()
                .numpy()
            )

            (
                splade_order,
                splade_ranks,
            ) = order_and_ranks(
                splade_scores
            )

            del (
                splade_q,
                splade_scores,
            )

            # ---------------- Frozen final RRF ----------------
            rrf_scores = (
                1.0
                / (
                    RRF_K
                    + bge_ranks
                    .astype(
                        np.float64
                    )
                )
                + 1.0
                / (
                    RRF_K
                    + bm25_ranks
                    .astype(
                        np.float64
                    )
                )
            )

            (
                rrf_order,
                rrf_ranks,
            ) = order_and_ranks(
                rrf_scores
            )

            top_idx = int(
                rrf_order[
                    0
                ]
            )

            second_idx = int(
                rrf_order[
                    1
                ]
            )

            top_issue_id = (
                ids[
                    top_idx
                ]
            )

            top_issue_title = (
                titles[
                    top_idx
                ]
            )

            top_rrf_score = float(
                rrf_scores[
                    top_idx
                ]
            )

            second_rrf_score = float(
                rrf_scores[
                    second_idx
                ]
            )

            absolute_margin = (
                top_rrf_score
                - second_rrf_score
            )

            relative_margin = (
                absolute_margin
                / max(
                    abs(
                        top_rrf_score
                    ),
                    1e-12,
                )
            )

            # -------------------------------------------------
            # Confidence features: NO GOLD USED BELOW.
            # -------------------------------------------------

            r_bge = int(
                bge_ranks[
                    top_idx
                ]
            )

            r_bm25 = int(
                bm25_ranks[
                    top_idx
                ]
            )

            r_splade = int(
                splade_ranks[
                    top_idx
                ]
            )

            corroboration_rr = float(
                (
                    1.0 / r_bge
                    + 1.0 / r_bm25
                    + 1.0 / r_splade
                )
                / 3.0
            )

            exact_top1_support = int(
                r_bge == 1
            ) + int(
                r_bm25 == 1
            ) + int(
                r_splade == 1
            )

            top3_support = int(
                r_bge <= 3
            ) + int(
                r_bm25 <= 3
            ) + int(
                r_splade <= 3
            )

            top10_support = int(
                r_bge <= 10
            ) + int(
                r_bm25 <= 10
            ) + int(
                r_splade <= 10
            )

            bge_top10 = list(
                map(
                    int,
                    bge_order[
                        :10
                    ],
                )
            )

            bm25_top10 = list(
                map(
                    int,
                    bm25_order[
                        :10
                    ],
                )
            )

            splade_top10 = list(
                map(
                    int,
                    splade_order[
                        :10
                    ],
                )
            )

            jac_bge_bm25 = (
                jaccard(
                    bge_top10,
                    bm25_top10,
                )
            )

            jac_bge_splade = (
                jaccard(
                    bge_top10,
                    splade_top10,
                )
            )

            jac_bm25_splade = (
                jaccard(
                    bm25_top10,
                    splade_top10,
                )
            )

            mean_top10_jaccard = float(
                (
                    jac_bge_bm25
                    + jac_bge_splade
                    + jac_bm25_splade
                )
                / 3.0
            )

            all_three_same = int(
                bge_order[
                    0
                ]
                == bm25_order[
                    0
                ]
                == splade_order[
                    0
                ]
            )

            # -------------------------------------------------
            # ONLY NOW use the existing pool labels to evaluate
            # whether confidence enriched confirmed top-1 hits.
            # -------------------------------------------------

            gids = gold_ids[
                (
                    app_name,
                    str(
                        q.query_id
                    ),
                )
            ]

            confirmed_hit1 = int(
                top_issue_id
                in set(
                    gids
                )
            )

            best_rank = (
                best_gold_rank(
                    rrf_ranks,
                    id_to_idx,
                    gids,
                )
            )

            rows.append(
                {
                    "app": app_name,
                    "query_id": str(
                        q.query_id
                    ),
                    "review_text": review,
                    "rrf_top1_issue_id": (
                        top_issue_id
                    ),
                    "rrf_top1_title": (
                        top_issue_title
                    ),
                    "benchmark_confirmed_hit1": (
                        confirmed_hit1
                    ),
                    "best_known_positive_rrf_rank": (
                        int(
                            best_rank
                        )
                    ),
                    "rrf_reciprocal_rank_known_positive": (
                        float(
                            1.0
                            / best_rank
                        )
                    ),
                    "rrf_top1_score": (
                        top_rrf_score
                    ),
                    "rrf_top2_score": (
                        second_rrf_score
                    ),
                    "rrf_absolute_margin": (
                        float(
                            absolute_margin
                        )
                    ),
                    "rrf_relative_margin": (
                        float(
                            relative_margin
                        )
                    ),
                    "rrf_top1_rank_in_bge": (
                        r_bge
                    ),
                    "rrf_top1_rank_in_bm25": (
                        r_bm25
                    ),
                    "rrf_top1_rank_in_splade_zs": (
                        r_splade
                    ),
                    "base_ranker_corroboration_rr": (
                        corroboration_rr
                    ),
                    "rrf_top1_exact_support_count": (
                        exact_top1_support
                    ),
                    "rrf_top1_top3_support_count": (
                        top3_support
                    ),
                    "rrf_top1_top10_support_count": (
                        top10_support
                    ),
                    "all_three_base_top1_same": (
                        all_three_same
                    ),
                    "top10_jaccard_bge_bm25": (
                        float(
                            jac_bge_bm25
                        )
                    ),
                    "top10_jaccard_bge_splade": (
                        float(
                            jac_bge_splade
                        )
                    ),
                    "top10_jaccard_bm25_splade": (
                        float(
                            jac_bm25_splade
                        )
                    ),
                    "mean_pairwise_top10_jaccard": (
                        mean_top10_jaccard
                    ),
                    "bge_top1_issue_id": (
                        ids[
                            int(
                                bge_order[
                                    0
                                ]
                            )
                        ]
                    ),
                    "bm25_top1_issue_id": (
                        ids[
                            int(
                                bm25_order[
                                    0
                                ]
                            )
                        ]
                    ),
                    "splade_top1_issue_id": (
                        ids[
                            int(
                                splade_order[
                                    0
                                ]
                            )
                        ]
                    ),
                    "bge_top10_issue_ids": (
                        ";".join(
                            ids[
                                idx
                            ]
                            for idx
                            in bge_top10
                        )
                    ),
                    "bm25_top10_issue_ids": (
                        ";".join(
                            ids[
                                idx
                            ]
                            for idx
                            in bm25_top10
                        )
                    ),
                    "splade_top10_issue_ids": (
                        ";".join(
                            ids[
                                idx
                            ]
                            for idx
                            in splade_top10
                        )
                    ),
                }
            )

        del (
            bge_docs,
            bge_queries,
            bge_scores_matrix,
            bm25,
            splade_docs_cpu,
            splade_queries_cpu,
            splade_docs_gpu,
        )

        gc.collect()
        torch.cuda.empty_cache()

    per_query = (
        pd.DataFrame(
            rows
        )
    )

    if len(
        per_query
    ) != 82:
        raise AssertionError(
            f"Expected 82 rows, got {len(per_query)}"
        )

    if (
        per_query[
            [
                "app",
                "query_id",
            ]
        ]
        .duplicated()
        .any()
    ):
        raise AssertionError(
            "Duplicate app/query_id rows"
        )

    # -------------------------------------------------------------
    # Hard RRF reproduction guard
    # -------------------------------------------------------------

    hit1_count = int(
        per_query[
            "benchmark_confirmed_hit1"
        ]
        .sum()
    )

    hit10_count = int(
        (
            per_query[
                "best_known_positive_rrf_rank"
            ]
            <= 10
        ).sum()
    )

    hit50_count = int(
        (
            per_query[
                "best_known_positive_rrf_rank"
            ]
            <= 50
        ).sum()
    )

    mrr = float(
        per_query[
            "rrf_reciprocal_rank_known_positive"
        ].mean()
    )

    median_rank = float(
        per_query[
            "best_known_positive_rrf_rank"
        ].median()
    )

    if hit1_count != 16:
        raise AssertionError(
            "RRF baseline reproduction failed: "
            f"expected 16 confirmed H@1, got {hit1_count}"
        )

    if hit10_count != 42:
        raise AssertionError(
            "RRF baseline reproduction failed: "
            f"expected H@10 count 42, got {hit10_count}"
        )

    if hit50_count != 63:
        raise AssertionError(
            "RRF baseline reproduction failed: "
            f"expected H@50 count 63, got {hit50_count}"
        )

    if abs(
        mrr
        - 0.2890973404537107
    ) > 5e-6:
        raise AssertionError(
            "RRF baseline reproduction failed: "
            f"expected MRR 0.28909734, got {mrr}"
        )

    if median_rank != 9.0:
        raise AssertionError(
            "RRF baseline reproduction failed: "
            f"expected median 9, got {median_rank}"
        )

    print(
        "\nRRF BASELINE REPRODUCED:",
        {
            "confirmed_H1": (
                f"{hit1_count}/82"
            ),
            "H10": (
                f"{hit10_count}/82"
            ),
            "H50": (
                f"{hit50_count}/82"
            ),
            "MRR": mrr,
            "median_rank": median_rank,
        },
        flush=True,
    )

    # -------------------------------------------------------------
    # Fixed selective curves
    # -------------------------------------------------------------

    continuous_signals = [
        (
            "base_ranker_corroboration_rr",
            "PRIMARY_base_ranker_corroboration_rr",
        ),
        (
            "rrf_relative_margin",
            "SECONDARY_rrf_relative_margin",
        ),
        (
            "mean_pairwise_top10_jaccard",
            "SECONDARY_mean_pairwise_top10_jaccard",
        ),
    ]

    curve_frames = []

    for score_col, score_name in continuous_signals:
        curve_frames.append(
            coverage_curve(
                frame=per_query,
                score_col=score_col,
                score_name=score_name,
                target_coverages=TARGET_COVERAGES,
                total_confirmed_hits=hit1_count,
            )
        )

    selective_curves = (
        pd.concat(
            curve_frames,
            ignore_index=True,
        )
    )

    support_rules = (
        categorical_support_table(
            frame=per_query,
            total_confirmed_hits=hit1_count,
        )
    )

    # -------------------------------------------------------------
    # Descriptive signal separation.
    # This is NOT treated as complete binary classification because
    # unconfirmed cases are not known negatives.
    # -------------------------------------------------------------

    separation_rows = []

    for score_col, score_name in continuous_signals:
        confirmed = (
            per_query.loc[
                per_query[
                    "benchmark_confirmed_hit1"
                ]
                == 1,
                score_col,
            ]
            .astype(float)
        )

        unconfirmed = (
            per_query.loc[
                per_query[
                    "benchmark_confirmed_hit1"
                ]
                == 0,
                score_col,
            ]
            .astype(float)
        )

        separation_rows.append(
            {
                "confidence_signal": (
                    score_name
                ),
                "confirmed_n": int(
                    len(
                        confirmed
                    )
                ),
                "unconfirmed_n": int(
                    len(
                        unconfirmed
                    )
                ),
                "confirmed_mean": float(
                    confirmed.mean()
                ),
                "unconfirmed_mean": float(
                    unconfirmed.mean()
                ),
                "confirmed_median": float(
                    confirmed.median()
                ),
                "unconfirmed_median": float(
                    unconfirmed.median()
                ),
            }
        )

    separation = (
        pd.DataFrame(
            separation_rows
        )
    )

    # -------------------------------------------------------------
    # Save
    # -------------------------------------------------------------

    per_query.to_csv(
        OUTPUT
        / "rrf_confidence_per_query_82.csv",
        index=False,
    )

    selective_curves.to_csv(
        OUTPUT
        / "selective_coverage_curves.csv",
        index=False,
    )

    support_rules.to_csv(
        OUTPUT
        / "categorical_support_rules.csv",
        index=False,
    )

    separation.to_csv(
        OUTPUT
        / "confidence_signal_descriptives.csv",
        index=False,
    )

    protocol = {
        "experiment": (
            "Confidence-aware abstention "
            "diagnostic for frozen RRF60"
        ),
        "queries": 82,
        "external_apps": [
            "Firefox",
            "VLC",
            "Nextcloud",
        ],
        "signal_excluded": True,
        "final_retriever": (
            "RRF60(BGE-ZS + BM25)"
        ),
        "confidence_rankers": [
            BGE_MODEL,
            "BM25",
            SPLADE_MODEL,
        ],
        "document_representation": (
            "issue title only"
        ),
        "primary_confidence_signal": (
            "Equal-weight mean reciprocal "
            "rank of the final RRF top-1 "
            "issue under BGE, BM25, and "
            "SPLADE-ZS"
        ),
        "secondary_confidence_signals": [
            "RRF relative rank1-rank2 score margin",
            "mean pairwise top-10 Jaccard overlap",
            "exact/top3/top10 support counts",
        ],
        "target_coverages": (
            TARGET_COVERAGES
        ),
        "tie_policy": (
            "At each target coverage, "
            "include all queries tied at "
            "the Nth confidence score; "
            "realized coverage may exceed target."
        ),
        "gold_usage": (
            "Gold is used only after all "
            "confidence features are computed, "
            "to measure enrichment of originally "
            "judged positive top-1 issues."
        ),
        "no_training": True,
        "no_threshold_tuning": True,
        "no_model_selection": True,
        "interpretation_guard": (
            "A benchmark-confirmed hit means "
            "the selected issue was one of the "
            "originally human-judged positive "
            "Häring issues. An unconfirmed top-1 "
            "is not necessarily semantically wrong "
            "because the original judgment pool "
            "is incomplete."
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
        "baseline": {
            "n": 82,
            "benchmark_confirmed_hit1_count": (
                hit1_count
            ),
            "benchmark_confirmed_hit1_rate": (
                hit1_count
                / 82
            ),
            "known_positive_H10": (
                hit10_count
                / 82
            ),
            "known_positive_H50": (
                hit50_count
                / 82
            ),
            "known_positive_MRR": (
                mrr
            ),
            "median_known_positive_rank": (
                median_rank
            ),
        },
        "selective_curves": (
            selective_curves
            .to_dict(
                "records"
            )
        ),
        "categorical_support_rules": (
            support_rules
            .to_dict(
                "records"
            )
        ),
        "confidence_signal_descriptives": (
            separation
            .to_dict(
                "records"
            )
        ),
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
        "haring_rrf_abstention_results"
    )

    shutil.make_archive(
        archive_base,
        "zip",
        root_dir=str(
            OUTPUT
        ),
    )

    shutil.copy2(
        archive_base
        + ".zip",
        OUTPUT
        / "haring_rrf_abstention_results.zip",
    )

    volume.commit()

    # -------------------------------------------------------------
    # Terminal output
    # -------------------------------------------------------------

    print(
        "\n"
        + "=" * 118
    )

    print(
        "HÄRING RRF CONFIDENCE / "
        "ABSTENTION DIAGNOSTIC"
    )

    print(
        "=" * 118
    )

    print(
        "\nBASELINE"
    )

    print(
        json.dumps(
            result[
                "baseline"
            ],
            indent=2,
        ),
        flush=True,
    )

    print(
        "\nSELECTIVE COVERAGE CURVES"
    )

    print(
        selective_curves[
            [
                "confidence_signal",
                "target_coverage",
                "accepted_queries",
                "realized_coverage",
                "confirmed_hits_accepted",
                "confirmed_hit1_among_accepted",
                "confirmed_hits_retained_fraction",
                "confirmed_hits_abstained",
                "threshold_inclusive",
            ]
        ].to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nCATEGORICAL SUPPORT RULES"
    )

    print(
        support_rules.to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nCONFIDENCE SIGNAL DESCRIPTIVES"
    )

    print(
        separation.to_string(
            index=False
        ),
        flush=True,
    )

    print(
        "\nSaved on Modal volume:"
    )

    print(
        "/vol/haring_rrf_abstention/"
        "haring_rrf_abstention_results.zip",
        flush=True,
    )

    return result


@app.local_entrypoint()
def main():
    result = (
        evaluate.remote()
    )

    print(
        "\nREMOTE RUN COMPLETE."
    )

    print(
        "Baseline:"
    )

    print(
        json.dumps(
            result[
                "baseline"
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
        "haring_rrf_abstention/"
        "haring_rrf_abstention_results.zip "
        r"C:\Users\Ogtay\Downloads"
        r"\haring_rrf_abstention_results.zip"
    )
