"""
fact_check.py: the auditor. Plain Python, no LLM.

Recomputes the headline facts straight from the tools and checks that the
brief quotes them correctly. Checks are label-aware where it matters: the
September NPS must appear on the line that talks about September, not just
anywhere in the brief.

Run on a saved brief:  python -m nps_insights_agent.fact_check logs/brief.md
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime

from . import config
from .tools.survey_tools import (find_score_comment_mismatches, get_callback_list, get_nps_by_segment,
                                 get_nps_overview, get_revenue_at_risk)
from .tools.theme_tools import get_comment_themes
from .tools.whatif_tools import estimate_fix_impact

NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def _norm(text: str) -> str:
    """Unicode minus/dashes -> ASCII so "−6.5" and "-6.5" compare equal."""
    return text.replace("−", "-").replace("–", "-").replace("—", "-")


def _month_aliases(month: str) -> list[str]:
    """'2026-09' -> ['2026-09', 'sep', 'september']"""
    try:
        d = datetime.strptime(month, "%Y-%m")
        return [month.lower(), d.strftime("%b").lower(), d.strftime("%B").lower()]
    except ValueError:
        return [month.lower()]


def _has_number(text: str, value: str) -> bool:
    """value present as a whole number token (so '18.5' doesn't match '118.5')."""
    return re.search(r"(?<![\d.])" + re.escape(value) + r"(?![\d])", text) is not None


def compute_facts() -> dict:
    """Every headline fact, straight from the tools."""
    ov = json.loads(get_nps_overview())
    risk = json.loads(get_revenue_at_risk())
    mm = json.loads(find_score_comment_mismatches())
    fix = json.loads(estimate_fix_impact("all"))
    low_samples = set()
    for col in ("product", "tenure", "channel"):
        for month in ("all", ov["latest_month"]):
            seg = json.loads(get_nps_by_segment(col, month))
            low_samples.update(seg.get("low_sample_segments", []))
    return {
        "overall_nps": ov["overall"]["nps_display"],
        "monthly": {m["month"]: m["nps_display"] for m in ov["monthly_trend"]},
        "alert_level": risk["overall_alert_level"],
        "revenue_at_risk_lakh": f'{risk["total_revenue_at_risk_lakh"]:.2f}',
        "top_fix_points": fix["all_months"]["top_fix_by_nps_points"],
        "top_fix_rupees": fix["all_months"]["top_fix_by_rupees"],
        "mismatch_count": mm["mismatch_count"],
        "alt_nps_if_reversed": mm["alternative_nps"]["overall"]["if_reversed"],
        "churn_pcts": [round(v * 100, 1) for v in config.CHURN_RATES.values()],
        "low_sample_segments": sorted(low_samples),
    }


def allowed_numbers() -> set[float]:
    """Every number any tool can produce (plus config values). A number in the
    brief that is not in this set was invented by an LLM."""
    outputs = [get_nps_overview(), get_revenue_at_risk(), find_score_comment_mismatches(),
               estimate_fix_impact("all"), get_callback_list(10, "latest"),
               get_comment_themes("all", "all", 15, 5)]
    df_months = json.loads(get_nps_overview())["monthly_trend"]
    for m in ["all"] + [x["month"] for x in df_months]:
        for col in ("product", "tenure", "channel", "month"):
            outputs.append(get_nps_by_segment(col, m))
    for m in [x["month"] for x in df_months]:
        outputs.append(get_comment_themes("all", m, 15, 5))
    allowed: set[float] = set()
    for text in outputs + [json.dumps(config.CHURN_RATES)]:
        for tok in NUM_RE.findall(_norm(text)):
            try:
                v = float(tok.replace(",", ""))
            except ValueError:
                continue
            allowed.update({round(abs(v), 2), round(abs(v) * 100, 2)})  # 0.25 -> 25 (%)
    allowed.update(float(i) for i in range(0, 31))      # ranks, scores 0-10, list sizes, n<30 rule
    allowed.update({100.0, 1000.0, 100000.0, 1e7})      # lakh / crore definitions
    return allowed


def fact_check(brief: str) -> dict:
    """Return {"passed": bool, "checks": [{name, passed, detail}], "facts": {...}}."""
    text = _norm(brief)
    low = text.lower()
    lines = low.splitlines()
    f = compute_facts()
    checks = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Overall NPS with sign
    add("overall_nps", _has_number(text, f["overall_nps"]), f"expects {f['overall_nps']}")

    # 2. Label-aware monthly NPS: value must sit on a line naming that month
    for month, val in f["monthly"].items():
        aliases = _month_aliases(month)
        ok = any(_has_number(line, val) and any(a in line for a in aliases) for line in lines)
        add(f"nps_{month}", ok, f"expects {val} on a line mentioning {month}")

    # 3. Alert level line
    m = re.search(r"alert level:\s*\**\s*(green|amber|red)", low)
    add("alert_level", bool(m) and m.group(1).upper() == f["alert_level"],
        f"expects 'ALERT LEVEL: {f['alert_level']}', found {m.group(1).upper() if m else 'none'}")

    # 4. Revenue at risk in lakh
    add("revenue_at_risk", _has_number(text, f["revenue_at_risk_lakh"]),
        f"expects ₹{f['revenue_at_risk_lakh']} lakh")

    # 5. Both rankings: top fix by points and by rupees are named
    for key in ("top_fix_points", "top_fix_rupees"):
        theme = f[key]
        label = config.THEMES[theme]["label"].lower()
        ok = theme in low or theme.replace("_", " ") in low or label in low
        add(key, ok, f"expects theme {theme}")
    add("two_rankings", "nps points" in low and ("rupees" in low or "₹" in text),
        "expects a ranking by NPS points and one by rupees")

    # 6. Data quality story: mismatches + alternative NPS
    mm_line = any("mismatch" in line and _has_number(line, str(f["mismatch_count"])) for line in lines)
    add("mismatch_count", mm_line, f"expects {f['mismatch_count']} on a mismatch line")
    add("alternative_nps", _has_number(text, f["alt_nps_if_reversed"]),
        f"expects alternative NPS {f['alt_nps_if_reversed']}")

    # 7. Caveats section with churn assumptions and low samples
    add("data_caveats_section", "data caveats" in low, "expects a DATA CAVEATS section")
    def pct_present(v: float) -> bool:  # 3% or 3.0% both count
        return re.search(r"(?<![\d.])" + f"{v:g}" + r"(\.0+)?\s*%", text) is not None
    add("churn_assumptions", all(pct_present(v) for v in f["churn_pcts"]),
        f"expects churn rates {[f'{v:g}%' for v in f['churn_pcts']]}")
    if f["low_sample_segments"]:
        add("low_sample_mentioned", "low sample" in low or "low_sample" in low,
            f"low-sample segments exist: {f['low_sample_segments']}")

    # 8. NPS never written as a percentage
    nps_vals = [f["overall_nps"], *f["monthly"].values()]
    bad = [v for v in nps_vals if re.search(re.escape(v.lstrip("+-")) + r"\s*%", text)]
    add("nps_not_percent", not bad, f"NPS written with %: {bad}" if bad else "ok")

    # 9. No invented numbers
    allowed = allowed_numbers()
    body = re.sub(r"\b\d{4}-\d{2}(-\d{2})?\b", " ", text)             # dates
    body = re.sub(r"\bR\d{3,}\b", " ", body)                           # response ids
    invented = []
    for tok in NUM_RE.findall(body):
        try:
            v = round(abs(float(tok.replace(",", ""))), 2)
        except ValueError:
            continue
        if v not in allowed:
            invented.append(tok)
    add("no_invented_numbers", not invented,
        f"numbers not produced by any tool: {sorted(set(invented))}" if invented else "ok")

    return {"passed": all(c["passed"] for c in checks), "checks": checks, "facts": f}


def format_report(result: dict) -> str:
    rows = [f"FACT CHECK: {'PASSED' if result['passed'] else 'FAILED'}"]
    for c in result["checks"]:
        rows.append(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']:<22} {c['detail']}")
    return "\n".join(rows)


def failed_checks_text(result: dict) -> str:
    return "\n".join(f"- {c['name']}: {c['detail']}" for c in result["checks"] if not c["passed"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m nps_insights_agent.fact_check <brief.md>")
        sys.exit(2)
    res = fact_check(open(sys.argv[1], encoding="utf-8").read())
    print(format_report(res))
    sys.exit(0 if res["passed"] else 1)
