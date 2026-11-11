"""
tools/data.py: the shared core every tool uses.

- load_survey(): read the CSV once (cached), validate and clean it.
- NPS maths: bucket, nps, margin of error.
- Formatting: signed NPS strings ("+18.5") and money in lakh.

Nothing here talks to an LLM, so all of it can be unit tested directly.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

import pandas as pd

from .. import config

# The active survey path. main.py --survey can change it via set_survey_path().
_survey_path: str = config.SURVEY_PATH


def set_survey_path(path: str) -> None:
    """Point every tool at a different CSV and clear the caches."""
    global _survey_path
    _survey_path = path
    _load.cache_clear()


def get_survey_path() -> str:
    return _survey_path


@lru_cache(maxsize=4)  # load once; shared tools get the answer for free
def _load(path: str) -> tuple[pd.DataFrame, dict]:
    """Read and clean the CSV. Returns (dataframe, data_quality_report)."""
    df = pd.read_csv(path, dtype={"response_id": str, "month": str})
    missing = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"survey is missing columns: {missing}")

    quality: dict[str, Any] = {"rows_read": int(len(df))}

    # Scores must be whole numbers 0-10; anything else is dropped and counted.
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    bad_score = df["score"].isna() | (df["score"] < 0) | (df["score"] > 10)
    quality["rows_dropped_bad_score"] = int(bad_score.sum())
    df = df[~bad_score].copy()
    df["score"] = df["score"].astype(int)

    # Revenue must be a non-negative number; missing becomes 0 and is counted.
    df["annual_revenue_inr"] = pd.to_numeric(df["annual_revenue_inr"], errors="coerce")
    quality["rows_missing_revenue"] = int(df["annual_revenue_inr"].isna().sum())
    df["annual_revenue_inr"] = df["annual_revenue_inr"].fillna(0).clip(lower=0)

    df["comment"] = df["comment"].fillna("").astype(str).str.strip()
    quality["rows_with_comment"] = int((df["comment"] != "").sum())

    # Derive month from date if the month column is blank.
    if df["month"].isna().any():
        df["month"] = df["month"].fillna(pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m"))

    df["bucket"] = df["score"].map(bucket)
    df["nps_value"] = df["bucket"].map({"promoter": 1, "passive": 0, "detractor": -1})
    df["churn_prob"] = df["bucket"].map(config.CHURN_RATES)
    df["revenue_at_risk_inr"] = df["annual_revenue_inr"] * df["churn_prob"]
    df = df.reset_index(drop=True)
    quality["rows_used"] = int(len(df))
    return df, quality


def load_survey() -> pd.DataFrame:
    """The cleaned survey as a DataFrame (cached per path)."""
    return _load(_survey_path)[0]



def data_quality() -> dict:
    return dict(_load(_survey_path)[1])


# ---------------------------------------------------------------------------
# NPS maths
# ---------------------------------------------------------------------------
def bucket(score: int) -> str:
    if score >= config.PROMOTER_MIN:
        return "promoter"
    if score >= config.PASSIVE_MIN:
        return "passive"
    return "detractor"


def nps_stats(scores: pd.Series) -> dict:
    """NPS, counts and 95% margin of error for a set of 0-10 scores."""
    n = int(len(scores))
    if n == 0:
        return {"n": 0, "nps": None, "nps_display": "n/a", "moe": None, "moe_display": "n/a",
                "promoters": 0, "passives": 0, "detractors": 0, "low_sample": True}
    p = int((scores >= config.PROMOTER_MIN).sum())
    d = int((scores < config.PASSIVE_MIN).sum())
    pas = n - p - d
    nps = (p - d) / n * 100
    # Each answer is +1 / 0 / -1; NPS is the mean x 100. MoE = z * sd / sqrt(n).
    mean = (p - d) / n
    var = (p + d) / n - mean ** 2
    moe = config.Z_95 * math.sqrt(max(var, 0.0)) / math.sqrt(n) * 100
    return {
        "n": n,
        "nps": round(nps, 1),
        "nps_display": fmt_nps(nps),
        "moe": round(moe, 1),
        "moe_display": f"±{moe:.1f}",
        "promoters": p,
        "passives": pas,
        "detractors": d,
        "pct_promoters": round(p / n * 100, 1),
        "pct_detractors": round(d / n * 100, 1),
        "low_sample": n < config.LOW_SAMPLE_N,
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def fmt_nps(x: float | None) -> str:
    """NPS is a score, not a percent: +18.5 / -6.5 / 0.0."""
    if x is None:
        return "n/a"
    x = round(float(x), 1)
    if x == 0:
        return "0.0"
    return f"{x:+.1f}"


def to_lakh(inr: float) -> float:
    return round(float(inr) / config.LAKH, 2)


def fmt_lakh(inr: float) -> str:
    return f"₹{to_lakh(inr):,.2f} lakh"


def worst_alert(*levels: str) -> str:
    return max(levels, key=config.ALERT_ORDER.index)


def to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)  # compact = fewer tokens


def error_json(tool: str, err: Exception | str) -> str:
    """Tools never crash: they return this instead."""
    return to_json({"error": f"{tool} failed: {err}", "hint": "check the arguments and try again"})


def latest_month(df: pd.DataFrame) -> str:
    return str(sorted(df["month"].dropna().unique())[-1])


def resolve_month(df: pd.DataFrame, month: str | None) -> str:
    """Turn "all" / "latest" / "worst" / "2026-09" into "all" or a real month.
    "worst" = the month with the lowest NPS. Raises ValueError on unknown months,
    which the calling tool turns into an error JSON."""
    month = (month or "all").strip().lower()
    months = sorted(df["month"].dropna().unique())
    if month == "all":
        return "all"
    if month == "latest":
        return months[-1]
    if month == "worst":
        return min(months, key=lambda m: nps_stats(df[df["month"] == m]["score"])["nps"])
    if month not in months:
        raise ValueError(f"unknown month {month!r}; use 'all', 'latest', 'worst' or one of {months}")
    return month
