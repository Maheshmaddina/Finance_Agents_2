"""
tools/whatif_tools.py: "if we fix X, what do we gain?"

Assumption (config.FIX_MOVES_DETRACTOR_TO): fixing a complaint turns the
detractors who raised it into passives. That gives two gains per fix:
  - NPS points  = detractors fixed / all responses x 100
  - rupees saved = sum of their revenue x (detractor churn - passive churn)
Ranking by each shows that the loudest problem is not always the costliest.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from .data import error_json, fmt_lakh, fmt_nps, latest_month, load_survey, to_json, to_lakh
from .theme_tools import tag_comment

COMPLAINT_THEMES = [k for k, t in config.THEMES.items() if t["polarity"] == "complaint"]


def _impact(df: pd.DataFrame, theme: str) -> dict:
    n = len(df)
    hit = df[df["themes"].map(lambda ts: theme in ts)]
    det = hit[hit["bucket"] == "detractor"]
    churn_gap = config.CHURN_RATES["detractor"] - config.CHURN_RATES[config.FIX_MOVES_DETRACTOR_TO]
    points = len(det) / n * 100 if n else 0.0
    saved = det["annual_revenue_inr"].sum() * churn_gap
    return {
        "theme": theme,
        "label": config.THEMES[theme]["label"],
        "owner": config.THEMES[theme].get("owner", ""),
        "customers_mentioning": int(len(hit)),
        "detractors_fixed": int(len(det)),
        "nps_points_gained": round(points, 1),
        "nps_points_display": fmt_nps(points),
        "rupees_saved_lakh": to_lakh(saved),
        "rupees_saved_display": fmt_lakh(saved),
    }


def _rank(df: pd.DataFrame, themes: list[str]) -> dict:
    rows = [_impact(df, t) for t in themes]
    rows = [r for r in rows if r["customers_mentioning"] > 0]
    by_points = sorted(rows, key=lambda r: (r["nps_points_gained"], r["rupees_saved_lakh"]), reverse=True)
    by_rupees = sorted(rows, key=lambda r: (r["rupees_saved_lakh"], r["nps_points_gained"]), reverse=True)
    short = lambda r: {"theme": r["theme"], "owner": r["owner"], "nps_points": r["nps_points_display"],
                       "rupees_saved_lakh": r["rupees_saved_lakh"], "detractors_fixed": r["detractors_fixed"]}
    return {
        "responses_in_scope": int(len(df)),
        "ranked_by_nps_points": [{"rank": i + 1, **short(r)} for i, r in enumerate(by_points)],
        "ranked_by_rupees_saved": [{"rank": i + 1, **short(r)} for i, r in enumerate(by_rupees)],
        "top_fix_by_nps_points": by_points[0]["theme"] if by_points else None,
        "top_fix_by_rupees": by_rupees[0]["theme"] if by_rupees else None,
        "rankings_agree": bool(by_points and by_points[0]["theme"] == by_rupees[0]["theme"]),
    }


def estimate_fix_impact(theme: str = "all") -> str:
    """Estimate NPS points gained and rupees saved if a complaint theme is fixed.

    Args:
        theme: a complaint theme key (e.g. "login_otp_failure", "fees_charges")
               or "all" to rank every complaint theme.

    Returns JSON with two scopes, "all_months" and "latest_month", each holding
    the fix list ranked by NPS points AND ranked by rupees saved (₹ lakh),
    plus the top fix under each ranking and whether the two rankings agree.
    Assumption: a fixed detractor becomes a passive.
    """
    try:
        df = load_survey().copy()
        df["themes"] = df["comment"].map(tag_comment)
        if theme in ("all", "", None):
            themes = COMPLAINT_THEMES
        elif theme in COMPLAINT_THEMES:
            themes = [theme]
        else:
            return error_json("estimate_fix_impact", f"theme must be 'all' or one of {COMPLAINT_THEMES}")
        lm = latest_month(df)
        return to_json({
            "assumption": f"a fixed detractor becomes a {config.FIX_MOVES_DETRACTOR_TO}; "
                          f"churn rates {config.CHURN_RATES}",
            "all_months": _rank(df, themes),
            "latest_month": {"month": lm, **_rank(df[df["month"] == lm], themes)},
        })
    except Exception as e:
        return error_json("estimate_fix_impact", e)


# Agents SDK wrapper (the plain function above stays callable for tests).
from agents import function_tool  # noqa: E402

# Strict JSON schemas are an OpenAI feature; other providers get plain schemas.
_STRICT = config.PROVIDER == "openai"

estimate_fix_impact_tool = function_tool(estimate_fix_impact, strict_mode=_STRICT)
