"""
tools/theme_tools.py: turn free-text comments into themes with keyword rules.

get_comment_themes() is the VoiceOfCustomerAgent's only tool. It counts
themes per NPS bucket, shows how complaint themes move month by month, and
returns real quotes (with response_id) so the agent never has to invent one.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from .. import config
from .data import error_json, latest_month, load_survey, nps_stats, resolve_month, to_json, to_lakh


@lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern]:
    """One regex per theme. Whole-word matching, so "fee" never matches "feel"."""
    return {
        key: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in t["keywords"]) + r")\b", re.I)
        for key, t in config.THEMES.items()
    }


def tag_comment(comment: str) -> list[str]:
    """All theme keys whose keywords appear in the comment as whole words."""
    text = str(comment or "")
    if not text.strip():
        return []
    return [key for key, pat in _patterns().items() if pat.search(text)]


def polarity_of(themes: list[str]) -> set[str]:
    return {config.THEMES[t]["polarity"] for t in themes}


def tagged_survey() -> pd.DataFrame:
    """Survey with a `themes` list column. Cheap: 600 rows, recomputed per call."""
    df = load_survey().copy()
    df["themes"] = df["comment"].map(tag_comment)
    return df


def _theme_table(df: pd.DataFrame, n_quotes: int) -> list[dict]:
    """Count each theme in df, with share, revenue and real quotes."""
    rows = []
    with_comment = int((df["comment"] != "").sum()) or 1
    exploded = df.explode("themes").dropna(subset=["themes"])
    for theme, g in exploded.groupby("themes"):
        quotes = (
            g.drop_duplicates("comment")
             .sort_values("annual_revenue_inr", ascending=False)
             .head(n_quotes)
        )
        rows.append({
            "theme": theme,
            "label": config.THEMES[theme]["label"],
            "polarity": config.THEMES[theme]["polarity"],
            "mentions": int(len(g)),
            "pct_of_comments": round(len(g) / with_comment * 100, 1),
            "avg_score": round(float(g["score"].mean()), 1),
            "revenue_lakh": to_lakh(g["annual_revenue_inr"].sum()),
            "quotes": [
                {"response_id": r.response_id, "score": int(r.score), "month": r.month,
                 "product": r.product, "quote": r.comment}
                for r in quotes.itertuples()
            ],
        })
    return sorted(rows, key=lambda r: r["mentions"], reverse=True)


def get_comment_themes(bucket: str = "all", month: str = "all", top_n: int = 6,
                       quotes_per_theme: int = 2) -> str:
    """Group survey comments into themes using keyword rules.

    Args:
        bucket: "detractor", "passive", "promoter" or "all" (default all: returns each bucket separately).
        month: "all" (default), "latest", "worst" or a month like "2026-09".
        top_n: how many themes to return per bucket (1-15).
        quotes_per_theme: real customer quotes to return per theme (0-5).

    Returns JSON with themes per bucket (mentions, share of comments, avg score,
    revenue, quotes with response_id) and a month-by-month count of every
    complaint theme so you can see which complaint spiked.
    """
    try:
        df = tagged_survey()
        top_n = max(1, min(int(top_n), 15))
        quotes_per_theme = max(0, min(int(quotes_per_theme), 5))
        months = sorted(df["month"].unique())
        month = resolve_month(df, month)
        scope = df if month == "all" else df[df["month"] == month]

        buckets = ["detractor", "passive", "promoter"]
        if bucket not in ("all", "", None):
            if bucket not in buckets:
                return error_json("get_comment_themes", f"bucket must be one of {buckets} or 'all'")
            buckets = [bucket]

        by_bucket = {}
        for b in buckets:
            sub = scope[scope["bucket"] == b]
            by_bucket[b] = {
                "responses": int(len(sub)),
                "with_comment": int((sub["comment"] != "").sum()),
                "top_themes": _theme_table(sub, quotes_per_theme)[:top_n],
            }

        # Month-by-month trend of complaint themes (all buckets) -> what spiked?
        complaint_keys = [k for k, t in config.THEMES.items() if t["polarity"] == "complaint"]
        trend = []
        for key in complaint_keys:
            counts = {m: int(df[df["month"] == m]["themes"].map(lambda ts: key in ts).sum()) for m in months}
            if sum(counts.values()) == 0:
                continue
            first, last = counts[months[0]], counts[months[-1]]
            trend.append({"theme": key, "label": config.THEMES[key]["label"],
                          "mentions_by_month": counts, "change_first_to_last": last - first})
        trend.sort(key=lambda r: r["change_first_to_last"], reverse=True)
        biggest = trend[0] if trend else None

        # NPS of customers who mention the biggest riser vs those who don't (latest month).
        lm = latest_month(df)
        lm_df = df[df["month"] == lm]
        spike_effect = None
        if biggest:
            has = lm_df["themes"].map(lambda ts: biggest["theme"] in ts)
            spike_effect = {
                "month": lm,
                "theme": biggest["theme"],
                "nps_with_theme": nps_stats(lm_df[has]["score"])["nps_display"],
                "n_with_theme": int(has.sum()),
                "nps_without_theme": nps_stats(lm_df[~has]["score"])["nps_display"],
                "n_without_theme": int((~has).sum()),
            }

        return to_json({
            "scope": {"bucket": bucket or "all", "month": month or "all"},
            "method": "keyword rules in config.THEMES (a comment can match several themes)",
            "comments_without_theme": int(((scope["comment"] != "") & (scope["themes"].map(len) == 0)).sum()),
            "by_bucket": by_bucket,
            "complaint_trend_by_month": trend,
            "fastest_rising_complaint": biggest["theme"] if biggest else None,
            "latest_month_effect_of_rising_complaint": spike_effect,
        })
    except Exception as e:  # never crash: hand the error back as JSON
        return error_json("get_comment_themes", e)


# Agents SDK wrapper (the plain function above stays callable for tests).
from agents import function_tool  # noqa: E402

# Strict JSON schemas are an OpenAI feature; other providers get plain schemas.
_STRICT = config.PROVIDER == "openai"

get_comment_themes_tool = function_tool(get_comment_themes, strict_mode=_STRICT)
