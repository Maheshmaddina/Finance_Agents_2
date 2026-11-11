"""
main.py: entry point.

    python -m nps_insights_agent.main --trace
    python -m nps_insights_agent.main --trace --verbose --log-dir logs
    python -m nps_insights_agent.main --survey other.csv --stream

Flow: orchestrator (3 phases) -> brief -> fact_check.py. If the fact check
fails, the brief goes back to ReportWriterAgent with the failed checks
(at most --max-rewrites times, default 2).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from agents import RunHooks, Runner
from openai.types.responses import ResponseTextDeltaEvent

from . import config
from .agents.orchestrator import HANDOFF_KEYS, HandoffBoard, build_orchestrator
from .agents.report_writer_agent import build_report_writer_agent
from .llm import resolve_model, setup_llm
from .fact_check import fact_check, failed_checks_text, format_report
from .tools.data import load_survey, set_survey_path

USER_PROMPT = (
    "Our NPS fell sharply last month. Produce the one-page NPS brief for the CEO "
    "meeting on Thursday: how bad it is, why, how much money is at risk, what to "
    "fix first and who to call back this week."
)


class Tracer(RunHooks):
    """SDK run hooks that print CALL / OUTPUT lines for the orchestrator's tool
    calls (the specialists) and keep them for the log.
    Three CALL lines before any OUTPUT = phase 1 really ran in parallel.
    Hooks work the same on every provider, streamed or not."""

    def __init__(self, show: bool, verbose: bool) -> None:
        self.show, self.verbose = show, verbose
        self.t0 = time.perf_counter()
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        line = f"[{time.perf_counter() - self.t0:6.1f}s] {line}"
        self.lines.append(line)
        if self.show:
            print(line, flush=True)

    async def on_tool_start(self, context, agent, tool) -> None:
        args = str(getattr(context, "tool_arguments", "") or "")
        self.log(f"CALL   {tool.name:<18} input={args[:70]!r}{'...' if len(args) > 70 else ''}")

    async def on_tool_end(self, context, agent, tool, result) -> None:
        self.log(f"OUTPUT {tool.name:<18} ({len(str(result))} chars)")
        if self.verbose:
            print(f"\n----- {tool.name} -----\n{result}\n", flush=True)


async def run_team(model, tracer: Tracer, stream: bool) -> tuple[str, HandoffBoard]:
    board = HandoffBoard()
    orchestrator = build_orchestrator(board, model=model)
    # Gemini's OpenAI-compatible endpoint merges parallel tool calls when
    # streaming, so streaming is only used on providers that handle it.
    if stream and config.PROVIDER == "gemini":
        tracer.log("NOTE   --stream is not supported on Gemini; running without streaming")
        stream = False
    if stream:
        result = Runner.run_streamed(orchestrator, USER_PROMPT, max_turns=12, hooks=tracer)
        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                print(event.data.delta, end="", flush=True)
        print()
    else:
        result = await Runner.run(orchestrator, USER_PROMPT, max_turns=12, hooks=tracer)

    final = str(result.final_output or "")
    writer = board.reports.get("BRIEF", "")
    # The orchestrator must return the writer's brief word for word. If it
    # edited or summarised it, fall back to the writer's exact text.
    if writer and final.strip() != writer.strip():
        tracer.log("NOTE   orchestrator output differs from report_writer output; using report_writer's brief")
        final = writer
    return final, board


async def rewrite(brief: str, board: HandoffBoard, failed: str, model) -> str:
    """Guardrail: send the brief back to the writer with the failed checks."""
    form = board.form(HANDOFF_KEYS["report_writer"])
    form += f"\n\nPREVIOUS_BRIEF:\n{brief}\n\nFAILED_CHECKS (fix every one, change nothing else):\n{failed}"
    result = await Runner.run(build_report_writer_agent(model), form)
    return str(result.final_output)


async def main_async(args: argparse.Namespace) -> int:
    if args.survey:
        set_survey_path(args.survey)
    try:
        load_survey()  # fail fast with a clear message on a bad CSV
    except Exception as e:
        print(f"Could not load survey: {e}", file=sys.stderr)
        return 2
    try:
        setup_llm()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2

    tracer = Tracer(show=args.trace or args.verbose, verbose=args.verbose)
    tracer.log(f"START  provider={config.PROVIDER} model={args.model} survey={args.survey or config.SURVEY_PATH}")
    model = resolve_model(args.model)
    brief, board = await run_team(model, tracer, args.stream)

    result = fact_check(brief)
    attempts = 0
    while not result["passed"] and attempts < args.max_rewrites:
        attempts += 1
        failed = [c for c in result["checks"] if not c["passed"]]
        tracer.log(f"GUARD  fact check failed ({'; '.join(c['name'] + ': ' + c['detail'] for c in failed)}); "
                   f"rewrite {attempts}/{args.max_rewrites}")
        brief = await rewrite(brief, board, failed_checks_text(result), model)
        result = fact_check(brief)
    tracer.log(f"DONE   fact check {'PASSED' if result['passed'] else 'FAILED'} after {attempts} rewrite(s)")

    print("\n" + "=" * 78 + "\n" + brief + "\n" + "=" * 78)
    print(format_report(result))

    if args.log_dir:
        out = Path(args.log_dir) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.md").write_text(brief, encoding="utf-8")
        (out / "trace.txt").write_text("\n".join(tracer.lines) + "\n", encoding="utf-8")
        (out / "fact_check.txt").write_text(format_report(result) + "\n", encoding="utf-8")
        (out / "handoffs.json").write_text(json.dumps(board.reports, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved brief, trace, fact check and hand-offs to {out}/")
    return 0 if result["passed"] else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NPS Analyst in a Box")
    p.add_argument("--trace", action="store_true", help="print CALL / OUTPUT lines for each specialist")
    p.add_argument("--verbose", action="store_true", help="also print every specialist's full report")
    p.add_argument("--stream", action="store_true", help="stream the orchestrator's final text")
    p.add_argument("--log-dir", default=None, help="save brief, trace, fact check and hand-offs here")
    p.add_argument("--survey", default=None, help="path to a survey CSV with the same columns")
    p.add_argument("--model", default=config.MODEL, help=f"model name (default {config.MODEL})")
    p.add_argument("--max-rewrites", type=int, default=2, help="fact-check guardrail retries (default 2)")
    return p.parse_args(argv)


def main() -> None:
    sys.exit(asyncio.run(main_async(parse_args())))


if __name__ == "__main__":
    main()
