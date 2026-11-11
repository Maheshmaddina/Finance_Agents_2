"""
Step 1 (M1): call every tool directly and print its result. No LLM.
Also cross-checks the tools against nps_by_hand-style plain pandas maths.

Run: python try_tools.py
"""
import json

import pandas as pd

from nps_insights_agent.tools.data import get_survey_path
from nps_insights_agent.tools.survey_tools import (find_score_comment_mismatches, get_callback_list,
                                                   get_nps_by_segment, get_nps_overview,
                                                   get_revenue_at_risk)
from nps_insights_agent.tools.theme_tools import get_comment_themes
from nps_insights_agent.tools.whatif_tools import estimate_fix_impact

CALLS = [
    ("get_nps_overview", get_nps_overview, {}),
    ("get_nps_by_segment(channel, 2026-09)", get_nps_by_segment, {"column": "channel", "month": "2026-09"}),
    ("get_nps_by_segment(product)", get_nps_by_segment, {"column": "product"}),
    ("get_comment_themes(detractor)", get_comment_themes, {"bucket": "detractor", "quotes_per_theme": 1}),
    ("get_revenue_at_risk", get_revenue_at_risk, {}),
    ("find_score_comment_mismatches", find_score_comment_mismatches, {}),
    ("estimate_fix_impact(all)", estimate_fix_impact, {"theme": "all"}),
    ("get_callback_list", get_callback_list, {"top_n": 5}),
    # bad input must come back as JSON errors, not crashes
    ("BAD get_nps_by_segment(colour)", get_nps_by_segment, {"column": "colour"}),
    ("BAD get_comment_themes(month=2030-01)", get_comment_themes, {"month": "2030-01"}),
    ("BAD estimate_fix_impact(weather)", estimate_fix_impact, {"theme": "weather"}),
    ("BAD get_callback_list(top_n='x')", get_callback_list, {"top_n": "x"}),
]

results = {}
for name, fn, kwargs in CALLS:
    out = fn(**kwargs)
    results[name] = json.loads(out)  # every tool must return valid JSON
    print(f"\n===== {name} =====\n{out[:2500]}{' ...' if len(out) > 2500 else ''}")

# Cross-check against plain pandas (the nps_by_hand.py answer key)
df = pd.read_csv(get_survey_path())
by_hand = lambda s: round(((s >= 9).mean() - (s <= 6).mean()) * 100, 1)
ov = results["get_nps_overview"]
assert ov["overall"]["nps"] == by_hand(df.score), "overall NPS disagrees with nps_by_hand"
for m in ov["monthly_trend"]:
    assert m["nps"] == by_hand(df[df.month == m["month"]].score), f"{m['month']} disagrees"
print("\nCROSS-CHECK PASSED: tools agree with nps_by_hand.py")
