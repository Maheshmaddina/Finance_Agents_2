"""
Offline tests: no LLM, no API key. Run: python -m tests.test_offline
Covers the tools (numbers, bad input) and the fact checker (pass + catch errors).
"""
import json

from nps_insights_agent.fact_check import fact_check
from nps_insights_agent.tools.data import nps_stats
from nps_insights_agent.tools.survey_tools import (get_callback_list, get_nps_by_segment,
                                                   get_nps_overview)
from nps_insights_agent.tools.theme_tools import get_comment_themes, tag_comment
from nps_insights_agent.tools.whatif_tools import estimate_fix_impact
import pandas as pd

GOOD_BRIEF = """# NPS Brief - Future with Shivank Bank
ALERT LEVEL: RED

## 1. How bad is it?
- Overall NPS: +18.5 (±6.6, n=600)
- Monthly trend:
  - 2026-07: +32.0
  - 2026-08: +30.0
  - 2026-09: -6.5
## 2. Why
- login_otp_failure mentions: 2026-07=1, 2026-08=2, 2026-09=48
## 3. Money
- Revenue at risk: ₹37.98 lakh of ₹304.43 lakh (12.5%)
## 4. Fix first
| Rank | By NPS points | By rupees |
| 1 | login_otp_failure +7.5 NPS points | fees_charges ₹6.40 lakh |
## DATA CAVEATS
- Churn assumptions: promoter 3%, passive 10%, detractor 25%
- Low samples: Wealth Call Centre (low sample)
- Score/comment mismatches: 9 responses; NPS as recorded +18.5, if reversed +21.5, if excluded +20.3
"""


def test_nps_maths():
    s = nps_stats(pd.Series([10, 9, 8, 7, 6, 0]))
    assert s["nps"] == 0.0 and s["promoters"] == 2 and s["detractors"] == 2
    assert nps_stats(pd.Series([], dtype=int))["nps"] is None


def test_overview_numbers():
    ov = json.loads(get_nps_overview())
    assert ov["overall"]["nps_display"] == "+18.5"
    assert [m["nps_display"] for m in ov["monthly_trend"]] == ["+32.0", "+30.0", "-6.5"]
    assert ov["health_verdict"]["level"] == "RED"


def test_bad_inputs_return_json_errors():
    for out in (get_nps_by_segment("colour"), get_comment_themes(month="2030-01"),
                estimate_fix_impact("weather"), get_callback_list(top_n="x")):
        assert "error" in json.loads(out)


def test_theme_whole_words():
    assert "fees_charges" not in tag_comment("I feel safe banking here")
    assert "login_otp_failure" in tag_comment("The app keeps asking for a code that never comes.")


def test_low_sample_never_best_or_worst():
    seg = json.loads(get_nps_by_segment("channel", "2026-09"))
    low = set(seg["low_sample_segments"])
    assert seg["best_segment"] not in low and seg["worst_segment"] not in low


def test_fact_check_passes_good_brief():
    res = fact_check(GOOD_BRIEF)
    assert res["passed"], [c for c in res["checks"] if not c["passed"]]


def test_fact_check_catches_errors():
    bad = GOOD_BRIEF.replace("2026-09: -6.5", "2026-09: -9.5").replace("ALERT LEVEL: RED", "ALERT LEVEL: AMBER")
    bad = bad.replace("+18.5 (", "18.5% (")
    failed = {c["name"] for c in fact_check(bad)["checks"] if not c["passed"]}
    assert {"nps_2026-09", "alert_level", "nps_not_percent"} <= failed, failed


def test_fact_check_catches_invented_numbers():
    bad = GOOD_BRIEF + "- Fixing everything saves ₹47.13 lakh\n"
    failed = {c["name"] for c in fact_check(bad)["checks"] if not c["passed"]}
    assert "no_invented_numbers" in failed, failed


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nAll {len(tests)} offline tests passed.")
