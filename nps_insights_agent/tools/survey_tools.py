"""
tools/survey_tools.py: the numbers. Every count, NPS, margin of error,
rupee figure and verdict an agent quotes comes from one of these functions.

All functions are plain Python, return a JSON string and never raise.
The agents wrap them with function_tool(); try_tools.py calls them directly.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .. import config
from .data import (data_quality, error_json, fmt_lakh, fmt_nps, latest_month,
                   load_survey, nps_stats, resolve_month, to_json, to_lakh, worst_alert,
                   get_survey_path)
from .theme_tools import polarity_of, tag_comment


# ---------------------------------------------------------------------------
# Verdicts (code decides, agents explain)
# ---------------------------------------------------------------------------
def _health_verdict(monthly: list[dict]) -> dict:
    """GREEN / AMBER / RED from the latest month's NPS and its month-on-month change."""
    latest = monthly[-1]
    change = latest["nps"] - monthly[-2]["nps"] if len(monthly) > 1 else 0.0
    reasons = []
    level = "GREEN"
    if latest["nps"] < config.HEALTH_RED_LATEST_NPS:
        level = "RED"
        reasons.append(f"{latest['month']} NPS {latest['nps_display']} is below {config.HEALTH_RED_LATEST_NPS}")
    if change <= config.HEALTH_RED_MONTH_DROP:
        level = "RED"
        reasons.append(f"month-on-month change {fmt_nps(change)} is at or below {config.HEALTH_RED_MONTH_DROP}")
    if level != "RED":
        if latest["nps"] < config.HEALTH_AMBER_LATEST_NPS or change <= config.HEALTH_AMBER_MONTH_DROP:
            level = "AMBER"
            reasons.append("latest NPS below target or falling")
    return {"level": level, "month_on_month_change": round(change, 1),
            "month_on_month_change_display": fmt_nps(change), "reasons": reasons}


def _risk_verdict(at_risk: float, total: float) -> dict:
    share = at_risk / total if total else 0.0
    if share >= config.RISK_RED_SHARE:
        level = "RED"
    elif share >= config.RISK_AMBER_SHARE:
        level = "AMBER"
    else:
        level = "GREEN"
    return {"level": level, "share_of_revenue_at_risk_pct": round(share * 100, 1),
            "thresholds_pct": {"amber": config.RISK_AMBER_SHARE * 100, "red": config.RISK_RED_SHARE * 100}}


def _monthly(df: pd.DataFrame) -> list[dict]:
    return [{"month": m, **nps_stats(g["score"])} for m, g in df.groupby("month", sort=True)]


# ---------------------------------------------------------------------------
# Tool 1: overview
# ---------------------------------------------------------------------------
def get_nps_overview() -> str:
    """Headline NPS for the whole survey and for each month.

    Returns JSON: overall NPS with 95% margin of error and bucket counts,
    a monthly trend (NPS, margin of error, n), the change from first to last
    month, the worst month, and a code-computed health verdict (GREEN/AMBER/RED).
    NPS is a score, not a percent: quote nps_display exactly (e.g. "+18.5").
    """
    try:
        df = load_survey()
        monthly = _monthly(df)
        worst = min(monthly, key=lambda m: m["nps"])
        best = max(monthly, key=lambda m: m["nps"])
        change = monthly[-1]["nps"] - monthly[0]["nps"]
        return to_json({
            "survey_file": get_survey_path(),
            "data_quality": data_quality(),
            "overall": nps_stats(df["score"]),
            "monthly_trend": monthly,
            "first_month": monthly[0]["month"],
            "latest_month": monthly[-1]["month"],
            "change_first_to_latest": round(change, 1),
            "change_first_to_latest_display": fmt_nps(change),
            "best_month": best["month"],
            "worst_month": worst["month"],
            "health_verdict": _health_verdict(monthly),
            "rules": {"promoter": "9-10", "passive": "7-8", "detractor": "0-6",
                      "low_sample_below": config.LOW_SAMPLE_N},
        })
    except Exception as e:
        return error_json("get_nps_overview", e)


# ---------------------------------------------------------------------------
# Tool 2: segments (shared by ScoreAnalyst and ChurnRisk -> cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _segment_cached(path: str, column: str, month: str) -> str:
    df = load_survey()
    scope = df if month == "all" else df[df["month"] == month]
    rows = []
    for value, g in scope.groupby(column, sort=True):
        s = nps_stats(g["score"])
        rows.append({
            column: value, **s,
            "revenue_lakh": to_lakh(g["annual_revenue_inr"].sum()),
            "revenue_at_risk_lakh": to_lakh(g["revenue_at_risk_inr"].sum()),
        })
    eligible = [r for r in rows if not r["low_sample"]]
    best = max(eligible, key=lambda r: r["nps"])[column] if eligible else None
    worst = min(eligible, key=lambda r: r["nps"])[column] if eligible else None
    return to_json({
        "column": column, "month": month, "segments": rows,
        "best_segment": best, "worst_segment": worst,
        "low_sample_segments": [r[column] for r in rows if r["low_sample"]],
        "note": f"segments with n < {config.LOW_SAMPLE_N} are low_sample and are never named best or worst",
    })


def get_nps_by_segment(column: str, month: str = "all") -> str:
    """NPS broken down by one segment column, optionally inside one month.

    Args:
        column: one of "product", "tenure", "channel", "month".
        month: "all", "latest", "worst" (month with the lowest NPS) or a month like "2026-09".

    Returns JSON: per segment NPS, margin of error, n, low_sample flag,
    revenue and revenue at risk in lakh; plus best/worst segment
    (low-sample segments are excluded from best/worst).
    """
    try:
        df = load_survey()
        if column not in config.SEGMENT_COLUMNS:
            return error_json("get_nps_by_segment", f"column must be one of {config.SEGMENT_COLUMNS}")
        return _segment_cached(get_survey_path(), column, resolve_month(df, month))
    except Exception as e:
        return error_json("get_nps_by_segment", e)


# ---------------------------------------------------------------------------
# Tool 3: revenue at risk
# ---------------------------------------------------------------------------
def _breakdown(df: pd.DataFrame, column: str) -> list[dict]:
    total_risk = df["revenue_at_risk_inr"].sum() or 1
    out = []
    for value, g in df.groupby(column):
        out.append({
            column: value,
            "customers": int(len(g)),
            "detractors": int((g["bucket"] == "detractor").sum()),
            "revenue_lakh": to_lakh(g["annual_revenue_inr"].sum()),
            "revenue_at_risk_lakh": to_lakh(g["revenue_at_risk_inr"].sum()),
            "share_of_total_risk_pct": round(g["revenue_at_risk_inr"].sum() / total_risk * 100, 1),
        })
    return sorted(out, key=lambda r: r["revenue_at_risk_lakh"], reverse=True)


def get_revenue_at_risk() -> str:
    """Revenue at risk = sum of (yearly revenue x assumed churn probability).

    Churn assumptions (config.py): promoter 3%, passive 10%, detractor 25%.
    Returns JSON in ₹ lakh: total revenue, total at risk, split by NPS bucket,
    product, channel, tenure, month and complaint theme; the top 10 customers
    by money at risk; concentration; a risk verdict; and the overall alert
    level (worst of the NPS health verdict and the risk verdict).
    """
    try:
        df = load_survey().copy()
        total_rev = df["annual_revenue_inr"].sum()
        at_risk = df["revenue_at_risk_inr"].sum()

        # Complaint themes: who is shouting vs where the money is.
        df["themes"] = df["comment"].map(tag_comment)
        theme_rows = []
        for key, t in config.THEMES.items():
            if t["polarity"] != "complaint":
                continue
            g = df[df["themes"].map(lambda ts: key in ts)]
            if g.empty:
                continue
            theme_rows.append({
                "theme": key, "label": t["label"], "customers": int(len(g)),
                "detractors": int((g["bucket"] == "detractor").sum()),
                "revenue_at_risk_lakh": to_lakh(g["revenue_at_risk_inr"].sum()),
                "avg_revenue_lakh": to_lakh(g["annual_revenue_inr"].mean()),
            })
        by_loudness = sorted(theme_rows, key=lambda r: r["customers"], reverse=True)
        by_money = sorted(theme_rows, key=lambda r: r["revenue_at_risk_lakh"], reverse=True)

        top = df.sort_values("revenue_at_risk_inr", ascending=False).head(10)
        top10_share = top["revenue_at_risk_inr"].sum() / at_risk * 100 if at_risk else 0

        risk = _risk_verdict(at_risk, total_rev)
        health = _health_verdict(_monthly(df))
        overall = worst_alert(risk["level"], health["level"])

        return to_json({
            "assumed_churn_rates": config.CHURN_RATES,
            "assumed_churn_rates_display": ", ".join(f"{k} {v * 100:g}%" for k, v in config.CHURN_RATES.items()),
            "units": "₹ lakh (1 lakh = ₹1,00,000)",
            "total_revenue_lakh": to_lakh(total_rev),
            "total_revenue_at_risk_lakh": to_lakh(at_risk),
            "total_revenue_at_risk_display": fmt_lakh(at_risk),
            "by_bucket": _breakdown(df, "bucket"),
            "by_product": _breakdown(df, "product"),
            "by_channel": _breakdown(df, "channel"),
            "by_tenure": _breakdown(df, "tenure"),
            "by_month": sorted(_breakdown(df, "month"), key=lambda r: r["month"]),
            "complaint_themes_ranked_by_customers": by_loudness,
            "complaint_themes_ranked_by_money": by_money,
            "loudest_complaint": by_loudness[0]["theme"] if by_loudness else None,
            "most_expensive_complaint": by_money[0]["theme"] if by_money else None,
            "loud_equals_expensive": bool(by_loudness and by_loudness[0]["theme"] == by_money[0]["theme"]),
            "top_10_customers_by_risk": [
                {"response_id": r.response_id, "product": r.product, "channel": r.channel,
                 "month": r.month, "score": int(r.score), "bucket": r.bucket,
                 "annual_revenue_lakh": to_lakh(r.annual_revenue_inr),
                 "revenue_at_risk_lakh": to_lakh(r.revenue_at_risk_inr), "comment": r.comment}
                for r in top.itertuples()
            ],
            "top_10_share_of_risk_pct": round(top10_share, 1),
            "risk_verdict": risk,
            "health_verdict_level": health["level"],
            "overall_alert_level": overall,
            "alert_rule": "overall alert = worst of health verdict and risk verdict",
        })
    except Exception as e:
        return error_json("get_revenue_at_risk", e)


# ---------------------------------------------------------------------------
# Tool 4: score / comment mismatches (data-quality sceptic)
# ---------------------------------------------------------------------------
def _mismatch_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Rows whose score contradicts the comment.

    low_score_positive_comment: detractor (0-6) whose comment is praise only
        (no complaint or neutral theme) -> probably flipped the 0-10 scale.
    high_score_negative_comment: promoter (9-10) whose comment is complaint only.
    """
    df = df.copy()
    df["themes"] = df["comment"].map(tag_comment)
    df["polarity"] = df["themes"].map(polarity_of)
    low_pos = (df["score"] < config.PASSIVE_MIN) & (df["polarity"] == {"praise"})
    high_neg = (df["score"] >= config.PROMOTER_MIN) & (df["polarity"] == {"complaint"})
    df["mismatch_type"] = None
    df.loc[low_pos, "mismatch_type"] = "low_score_positive_comment"
    df.loc[high_neg, "mismatch_type"] = "high_score_negative_comment"
    return df[df["mismatch_type"].notna()]


def find_score_comment_mismatches() -> str:
    """Find answers where the score contradicts the comment (e.g. a 0 with
    "Excellent service"). Scores are NOT changed; instead the tool reports
    alternative NPS figures so the brief can state them as caveats.

    Returns JSON: every mismatch (response_id, score, comment, type), counts by
    month, and NPS as recorded vs if mismatched scores were reversed
    (score -> 10 - score) vs if they were excluded, overall and per month.
    """
    try:
        df = load_survey()
        mm = _mismatch_frame(df)
        ids = set(mm["response_id"])

        reversed_scores = df["score"].where(~df["response_id"].isin(ids), 10 - df["score"])
        alt = df.assign(score_reversed=reversed_scores)

        def scenario(frame: pd.DataFrame) -> dict:
            rec = nps_stats(frame["score"])
            rev = nps_stats(frame["score_reversed"])
            exc = nps_stats(frame[~frame["response_id"].isin(ids)]["score"])
            return {"as_recorded": rec["nps_display"], "if_reversed": rev["nps_display"],
                    "if_excluded": exc["nps_display"],
                    "shift_if_reversed": fmt_nps(rev["nps"] - rec["nps"])}

        months = sorted(df["month"].unique())
        return to_json({
            "mismatch_count": int(len(mm)),
            "share_of_responses_pct": round(len(mm) / len(df) * 100, 1),
            "by_type": mm["mismatch_type"].value_counts().to_dict(),
            "by_month": {m: int((mm["month"] == m).sum()) for m in months},
            "mismatches": [
                {"response_id": r.response_id, "month": r.month, "score": int(r.score),
                 "type": r.mismatch_type, "comment": r.comment,
                 "annual_revenue_lakh": to_lakh(r.annual_revenue_inr)}
                for r in mm.itertuples()
            ],
            "alternative_nps": {
                "overall": scenario(alt),
                "by_month": {m: scenario(alt[alt["month"] == m]) for m in months},
            },
            "policy": "scores are never changed silently; report alternatives under DATA CAVEATS",
        })
    except Exception as e:
        return error_json("find_score_comment_mismatches", e)


# ---------------------------------------------------------------------------
# Tool 5: callback list
# ---------------------------------------------------------------------------
def get_callback_list(top_n: int = 10, month: str = "latest") -> str:
    """Detractors to call back this week, ranked by money at risk.

    Args:
        top_n: how many customers to return (1-50).
        month: "latest" (default), a month like "2026-09", or "all".

    Returns JSON: customers (response_id, product, channel, score, revenue,
    revenue at risk in lakh, comment, themes) and a verify_score_first flag for
    any whose comment contradicts the score.
    """
    try:
        df = load_survey()
        top_n = max(1, min(int(top_n), 50))
        month = resolve_month(df, month or "latest")
        if month != "all":
            df = df[df["month"] == month]
        mismatch_ids = set(_mismatch_frame(df)["response_id"])
        det = df[df["bucket"] == "detractor"].sort_values("revenue_at_risk_inr", ascending=False)
        rows = [
            {"rank": i + 1, "response_id": r.response_id, "product": r.product,
             "channel": r.channel, "tenure": r.tenure, "score": int(r.score),
             "annual_revenue_lakh": to_lakh(r.annual_revenue_inr),
             "revenue_at_risk_lakh": to_lakh(r.revenue_at_risk_inr),
             "comment": r.comment or "(no comment)", "themes": tag_comment(r.comment),
             "verify_score_first": r.response_id in mismatch_ids}
            for i, r in enumerate(det.head(top_n).itertuples())
        ]
        return to_json({
            "month": month, "detractors_in_scope": int(len(det)),
            "callback_list": rows,
            "list_revenue_at_risk_lakh": round(sum(r["revenue_at_risk_lakh"] for r in rows), 2),
        })
    except Exception as e:
        return error_json("get_callback_list", e)


# ---------------------------------------------------------------------------
# Agents SDK wrappers. The plain functions above stay callable for tests;
# agents get these. get_nps_by_segment_tool is shared by two agents and its
# results are cached, so the second agent gets the answer for free.
# ---------------------------------------------------------------------------
from agents import function_tool  # noqa: E402

# Strict JSON schemas are an OpenAI feature; other providers get plain schemas.
_STRICT = config.PROVIDER == "openai"

get_nps_overview_tool = function_tool(get_nps_overview, strict_mode=_STRICT)
get_nps_by_segment_tool = function_tool(get_nps_by_segment, strict_mode=_STRICT)
get_revenue_at_risk_tool = function_tool(get_revenue_at_risk, strict_mode=_STRICT)
find_score_comment_mismatches_tool = function_tool(find_score_comment_mismatches, strict_mode=_STRICT)
get_callback_list_tool = function_tool(get_callback_list, strict_mode=_STRICT)
