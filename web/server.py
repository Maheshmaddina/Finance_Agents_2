"""
web/server.py: the NPS Analyst website.

    python -m web.server            -> http://127.0.0.1:8000

Endpoints
  GET  /                  the single-page site (web/static/)
  GET  /api/dashboard     every chart's numbers, straight from the tools (no LLM)
  GET  /api/runs          saved agent runs in logs/, newest first
  GET  /api/runs/{id}     one run: brief, trace, fact check, hand-offs
  GET  /api/run/stream    starts a new agent run and streams its trace (SSE)

Code computes, agents reason: the dashboard never calls an LLM. Only the
"Run the agent team" button does, by running main.py as a subprocess.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from nps_insights_agent import config
from nps_insights_agent.tools.data import load_survey
from nps_insights_agent.tools.survey_tools import (find_score_comment_mismatches, get_callback_list,
                                                   get_nps_by_segment, get_nps_overview,
                                                   get_revenue_at_risk)
from nps_insights_agent.tools.theme_tools import get_comment_themes
from nps_insights_agent.tools.whatif_tools import estimate_fix_impact

ROOT = config.PROJECT_ROOT
LOG_DIR = ROOT / "logs"
STATIC = Path(__file__).parent / "static"
RUN_ID_RE = re.compile(r"^run_\d{8}_\d{6}$")  # only real run folders, no path tricks

app = FastAPI(title="NPS Analyst in a Box")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_run_lock = asyncio.Lock()  # one agent run at a time (free-tier quotas)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


# ---------------------------------------------------------------------------
# Dashboard: plain tool calls, no LLM
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard() -> dict:
    j = json.loads
    ov = j(get_nps_overview())
    months = [m["month"] for m in ov["monthly_trend"]]
    channel_by_month = {m: j(get_nps_by_segment("channel", m))["segments"] for m in months}
    return {
        "provider": config.PROVIDER,
        "model": config.MODEL,
        "overview": ov,
        "channel_by_month": channel_by_month,
        "product_by_month": {m: j(get_nps_by_segment("product", m))["segments"] for m in months},
        "risk": j(get_revenue_at_risk()),
        "themes": j(get_comment_themes("all", "all", 6, 2)),
        "themes_latest_detractors": j(get_comment_themes("detractor", "latest", 4, 5)),
        "fix": j(estimate_fix_impact("all")),
        "mismatches": j(find_score_comment_mismatches()),
        "callbacks": j(get_callback_list(10, "latest")),
        "theme_labels": {k: t["label"] for k, t in config.THEMES.items()},
        "theme_owners": {k: t.get("owner", "") for k, t in config.THEMES.items()},
    }


# ---------------------------------------------------------------------------
# Saved runs
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


@app.get("/api/runs")
def list_runs() -> list[dict]:
    if not LOG_DIR.exists():
        return []
    runs = []
    for d in sorted(LOG_DIR.iterdir(), reverse=True):
        if d.is_dir() and RUN_ID_RE.match(d.name) and (d / "brief.md").exists():
            fc = _read(d / "fact_check.txt")
            runs.append({"id": d.name, "passed": fc.startswith("FACT CHECK: PASSED")})
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if not RUN_ID_RE.match(run_id) or not (LOG_DIR / run_id).is_dir():
        raise HTTPException(404, "run not found")
    d = LOG_DIR / run_id
    handoffs = _read(d / "handoffs.json")
    return {
        "id": run_id,
        "brief": _read(d / "brief.md"),
        "trace": _read(d / "trace.txt"),
        "fact_check": _read(d / "fact_check.txt"),
        "handoffs": json.loads(handoffs) if handoffs else {},
    }


# ---------------------------------------------------------------------------
# Live run: main.py as a subprocess, its stdout streamed as server-sent events
# ---------------------------------------------------------------------------
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/run/stream")
async def run_stream() -> StreamingResponse:
    async def events():
        if _run_lock.locked():
            yield _sse({"type": "error", "text": "A run is already in progress. Wait for it to finish."})
            return
        async with _run_lock:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-m", "nps_insights_agent.main", "--trace", "--log-dir", str(LOG_DIR),
                cwd=str(ROOT), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            run_id = None
            try:
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    m = re.search(r"(run_\d{8}_\d{6})/?$", line)
                    if line.startswith("Saved ") and m:
                        run_id = m.group(1)
                    yield _sse({"type": "line", "text": line})
                code = await proc.wait()
                yield _sse({"type": "done", "exit": code, "run_id": run_id})
            finally:
                if proc.returncode is None:  # browser closed the page mid-run
                    proc.kill()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def main() -> None:
    import uvicorn
    load_survey()  # fail fast on a bad CSV
    print("NPS Analyst website: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
