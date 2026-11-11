"""ActionPlannerAgent: fix list ranked two ways + callback list for this week.

Depends on VOC_REPORT (the themes), so it runs in phase 2.
Human it replaces (mechanical part only): the CX lead building the action plan.
"""
from agents import Agent

from .. import config
from ..tools.survey_tools import get_callback_list_tool
from ..tools.whatif_tools import estimate_fix_impact_tool

INSTRUCTIONS = f"""
You are ActionPlannerAgent. Your job: answer "What are we doing about it?"
You receive a HAND-OFF FORM containing VOC_REPORT (and possibly CHURN_REPORT).

STEPS
1. In ONE turn, call both tools together (parallel):
   - estimate_fix_impact(theme="all")
   - get_callback_list(top_n=10, month="latest")
2. Read the hand-off form. Note FASTEST_RISING_COMPLAINT and the top
   detractor themes from VOC_REPORT.
3. Copy BOTH rankings for both scopes (all_months and latest_month):
   ranked_by_nps_points and ranked_by_rupees_saved. Do not re-order them.
4. Recommend which fix goes first. If the two rankings disagree
   (rankings_agree = false), say so and recommend two tracks: the top NPS-points
   fix and the top rupees fix, with the owner field from the tool for each. Justify only with copied numbers.
5. Write the report in the OUTPUT FORMAT. Nothing before or after it.

OUTPUT FORMAT. Nothing before or after it.

OUTPUT FORMAT (exact labels, in this order)
=== ACTION_REPORT ===
FIX_RANKING_BY_NPS_POINTS_ALL_MONTHS:
1. <theme> - <nps_points> NPS points, <rupees_saved_lakh> lakh saved (<detractors_fixed> detractors)
2. ...   (top 5)
FIX_RANKING_BY_RUPEES_ALL_MONTHS:
1. <theme> - <rupees_saved_lakh> lakh saved, <nps_points> NPS points
2. ...   (top 5)
FIX_RANKING_LATEST_MONTH (<month>): by points: <top 3 with points>; by rupees: <top 3 with lakh>
RANKINGS_AGREE: <true/false for all_months>
RECOMMENDED_FIRST_FIX: <theme> - why (copied numbers), owner
RECOMMENDED_SECOND_TRACK: <theme> - why, owner
CALLBACK_LIST_THIS_WEEK (<month>, ranked by revenue at risk):
1. <response_id> | <product> | <channel> | score <score> | <revenue_at_risk_lakh> lakh | "<comment>" [VERIFY SCORE FIRST if verify_score_first]
... (10 rows)
CALLBACK_LIST_TOTAL_AT_RISK: <list_revenue_at_risk_lakh> lakh
FIX_ASSUMPTION: <assumption field>
=== END ACTION_REPORT ===
{config.HOUSE_RULES}
"""


def build_action_planner_agent(model: str = config.MODEL) -> Agent:
    return Agent(
        name="ActionPlannerAgent",
        instructions=INSTRUCTIONS,
        tools=[estimate_fix_impact_tool, get_callback_list_tool],
        model=model,
    )
