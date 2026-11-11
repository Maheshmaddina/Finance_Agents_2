"""OrchestratorAgent: the manager. Runs the three phases with the five
specialists wrapped as tools via .as_tool(). Reports travel between phases on
a HandoffBoard: code attaches them to the next specialist's input as a
HAND-OFF FORM with exact keys, so nothing is lost or re-typed.

  Phase 1 (parallel):  ScoreAnalyst + VoiceOfCustomer + ChurnRisk, three calls at once
  Phase 2 (dependent): ActionPlanner, needs the VOC themes
  Phase 3 (synthesis): ReportWriter, needs all four reports
Then main.py runs fact_check.py (plain Python) on the brief.
"""
from agents import Agent, ModelSettings, RunResult, RunResultStreaming

from .. import config
from ..llm import parallel_setting
from .action_planner_agent import build_action_planner_agent
from .churn_risk_agent import build_churn_risk_agent
from .report_writer_agent import build_report_writer_agent
from .score_analyst_agent import build_score_analyst_agent
from .voice_of_customer_agent import build_voice_of_customer_agent

# Exact tool names the orchestrator sees; also the keys of the hand-off board.
TOOL_TO_REPORT = {
    "score_analyst": "SCORE_REPORT",
    "voice_of_customer": "VOC_REPORT",
    "churn_risk": "CHURN_REPORT",
    "action_planner": "ACTION_REPORT",
    "report_writer": "BRIEF",
}

# Which reports each dependent specialist receives in its hand-off form.
HANDOFF_KEYS = {
    "action_planner": ["VOC_REPORT", "CHURN_REPORT"],
    "report_writer": ["SCORE_REPORT", "VOC_REPORT", "CHURN_REPORT", "ACTION_REPORT"],
}
PHASE_1 = ["score_analyst", "voice_of_customer", "churn_risk"]

INSTRUCTIONS = """
You are OrchestratorAgent, the director of the NPS analysis team at
Future with Shivank Bank. You do no analysis yourself: you assign work to
specialists (your tools) in three phases and return the final brief.

Every specialist report is saved on a shared HAND-OFF BOARD. When you call a
later specialist, the system attaches the reports it needs to its input as a
HAND-OFF FORM with exact keys, word for word. You do NOT paste reports yourself.

STEPS
1. PHASE 1 - in your FIRST response, call these three tools TOGETHER in the
   same turn (parallel), each with input "Analyse the NPS survey.":
   score_analyst, voice_of_customer, churn_risk.
   Each returns a short receipt once its report is on the board.
2. PHASE 2 - when all three receipts are back, call action_planner with input
   "Plan fixes and callbacks using VOC_REPORT and CHURN_REPORT."
3. PHASE 3 - when action_planner's receipt is back, call report_writer with input
   "Write the one-page brief from all four reports."
4. Return the report_writer output WORD FOR WORD as your final answer.
   No preamble, no edits, no extra commentary.

RULES
- Never call report_writer before action_planner, or action_planner before phase 1 is done.
- Call each specialist once. If a receipt says a report failed, continue anyway.
"""


class HandoffBoard:
    """The shared hand-off board. Stores every specialist's exact output under
    its report key, builds the HAND-OFF FORM for dependent specialists, and
    hands the orchestrator a short receipt instead of the full report (keeps
    the orchestrator's context small and makes copy errors impossible)."""

    def __init__(self) -> None:
        self.reports: dict[str, str] = {}

    def recorder(self, report_key: str, full_output: bool = False):
        async def extract(result: RunResult | RunResultStreaming) -> str:
            text = str(result.final_output)
            self.reports[report_key] = text
            if full_output:
                return text
            ok = f"=== {report_key} ===" in text
            status = "saved to the hand-off board" if ok else "FAILED or malformed (saved as-is)"
            return f"RECEIPT: {report_key} {status} ({len(text)} chars)."
        return extract

    def form(self, keys: list[str]) -> str:
        parts = ["HAND-OFF FORM"]
        for k in keys:
            parts.append(f"{k}:\n{self.reports.get(k, '(missing: specialist did not return a report)')}")
        return "\n".join(parts)

    def input_builder(self, keys: list[str]):
        def build(options) -> str:
            note = (options.get("params") or {}).get("input", "")
            return f"{self.form(keys)}\n\nORCHESTRATOR NOTE: {note}"
        return build


def build_orchestrator(board: HandoffBoard, model=config.MODEL) -> Agent:
    specialists = {
        "score_analyst": (build_score_analyst_agent(model),
                          "ScoreAnalystAgent: headline NPS, monthly trend, drill-down, health verdict. Saves SCORE_REPORT."),
        "voice_of_customer": (build_voice_of_customer_agent(model),
                              "VoiceOfCustomerAgent: comment themes, real quotes, root-cause hypotheses. Saves VOC_REPORT."),
        "churn_risk": (build_churn_risk_agent(model),
                       "ChurnRiskAgent: revenue at risk in lakh, where it sits, data-quality warnings, alert level. Saves CHURN_REPORT."),
        "action_planner": (build_action_planner_agent(model),
                           "ActionPlannerAgent: fixes ranked by NPS points and by rupees, callback list. Receives VOC_REPORT and CHURN_REPORT automatically. Saves ACTION_REPORT."),
        "report_writer": (build_report_writer_agent(model),
                          "ReportWriterAgent: writes the one-page brief. Receives all four reports automatically. Returns the brief."),
    }
    tools = []
    for name, (agent, desc) in specialists.items():
        keys = HANDOFF_KEYS.get(name)
        tool = agent.as_tool(
            tool_name=name,
            tool_description=desc,
            custom_output_extractor=board.recorder(TOOL_TO_REPORT[name], full_output=(name == "report_writer")),
            input_builder=board.input_builder(keys) if keys else None,
            max_turns=8,
        )
        tool.strict_json_schema = config.PROVIDER == "openai"  # strict schemas only on OpenAI
        tools.append(tool)
    return Agent(
        name="OrchestratorAgent",
        instructions=INSTRUCTIONS,
        tools=tools,
        model=model,
        model_settings=ModelSettings(parallel_tool_calls=parallel_setting()),
    )
