# NPS Analyst in a Box

A team of AI agents that turns 600 survey answers into a one-page leadership brief for
Future with Shivank Bank, with every number checked by code.

**Code computes, agents reason.** Tools (plain Python + pandas) do all counting, NPS maths,
rupee figures and GREEN/AMBER/RED verdicts. Agents read the tool results, decide what matters and explain it.
`fact_check.py` (plain Python) audits the final brief.

## The architecture: an NPS analysis team in code

| Agent | Human it replaces (the mechanical part only) | Its tools |
|---|---|---|
| **ScoreAnalystAgent** | Analyst building the NPS pivot table | `get_nps_overview` `get_nps_by_segment` ★ |
| **VoiceOfCustomerAgent** | Analyst reading 536 comments | `get_comment_themes` |
| **ChurnRiskAgent** | Finance partner and data-quality sceptic | `get_revenue_at_risk` `find_score_comment_mismatches` `get_nps_by_segment` ★ (shared) |
| **ActionPlannerAgent** | CX lead building the action plan | `estimate_fix_impact` `get_callback_list` |
| **ReportWriterAgent** | Head of CX writing the CEO note | none: synthesis only |
| **OrchestratorAgent** | Director assigning the work | the five agents above, each wrapped with `.as_tool()` |

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ OrchestratorAgent                                                                    │
│ director · calls every specialist as a tool · returns the final brief word for word  │
└───────┬─────────────────────────────────────┬──────────────────────────────┬─────────┘
        │ ① three calls at once               │ ② then                       │ ③ finally
        ▼                                     ▼                              ▼
┌────────────────────────────┐     ┌──────────────────────────┐   ┌──────────────────────────┐
│ ScoreAnalystAgent          │     │ ActionPlannerAgent       │   │ ReportWriterAgent        │
│ NPS analyst · the pivot    │     │ CX lead · the plan       │   │ head of CX               │
│  get_nps_overview          │     │  estimate_fix_impact     │   │ no tools · synthesis     │
│  get_nps_by_segment ★      │──┐  │  get_callback_list       │──▶│ alert table → brief      │
└────────────────────────────┘  │  └──────────────────────────┘   └────────────┬─────────────┘
┌────────────────────────────┐  │        ▲ themes                   ▲          │
│ VoiceOfCustomerAgent       │┄┄┼┄┄┄┄┄┄┄┄┘ (VOC_REPORT)              │          ▼
│ comment reader             │──┤                                   │   ┌──────────────────────┐
│  get_comment_themes        │  ├───────────────────────────────────┘   │ NPS brief            │
└────────────────────────────┘  │   all four reports go in               │ GREEN / AMBER / RED  │
┌────────────────────────────┐  │                                        └──────────┬───────────┘
│ ChurnRiskAgent             │──┘                                                   ▼
│ finance · the sceptic      │                                        ┌──────────────────────┐
│  get_revenue_at_risk       │                                        │ fact_check.py        │
│  find_score_comment_       │                                        │ plain-Python auditor │
│    mismatches              │                                        │ fail → rewrite (≤2)  │
│  get_nps_by_segment ★      │                                        └──────────────────────┘
└────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ data/nps_survey.csv (pandas, loaded once) feeds every tool · ★ = shared tool, cached │
│ so the second agent gets the answer for free                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Three phases.** ① ScoreAnalyst, VoiceOfCustomer and ChurnRisk don't depend on each other, so they run
at the same time. ② ActionPlanner needs the themes (VOC_REPORT) to plan fixes. ③ ReportWriter needs all
four reports. Then `fact_check.py` re-computes the headline numbers and checks the brief quotes them.

### Where everything lives

```
Finance_2_Agents/
├── data/nps_survey.csv              # GIVEN: 600 answers, Jul–Sep 2026
├── nps_by_hand.py                   # Step 0: NPS in plain pandas (the answer key), no LLM
├── try_tools.py                     # Step 1: every tool's output + cross-check, no LLM
├── nps_insights_agent/
│   ├── config.py                    # NPS rules, thresholds, churn assumptions, themes, house rules, model
│   ├── agents/
│   │   ├── score_analyst_agent.py   # overview + segments → health verdict
│   │   ├── voice_of_customer_agent.py # comments → themes, quotes, root-cause hypotheses
│   │   ├── churn_risk_agent.py      # sceptic: revenue at risk + data-quality warnings
│   │   ├── action_planner_agent.py  # fixes ranked two ways + callback list
│   │   ├── report_writer_agent.py   # everything → final brief (no tools)
│   │   └── orchestrator.py          # runs the 3 phases; hand-off board
│   ├── tools/
│   │   ├── data.py                  # load once (cached), NPS maths, margin of error, formatting
│   │   ├── survey_tools.py          # overview, segments, revenue at risk, mismatches, callbacks
│   │   ├── theme_tools.py           # comments → themes (whole-word keyword rules)
│   │   └── whatif_tools.py          # "if we fix X": NPS points and rupees saved
│   ├── llm.py                       # connects the SDK to Gemini / Groq / OpenRouter / OpenAI
│   ├── fact_check.py                # the auditor (label-aware, catches invented numbers)
│   └── main.py                      # entry point: --trace --verbose --stream --log-dir --survey
├── stretch/llm_theme_tagger.py      # stretch: LLM tagger limited to the fixed theme list, cached
├── web/                             # website: server.py (FastAPI) + static/ (HTML, CSS, JS charts)
├── tests/test_offline.py            # offline tests (no API key needed)
├── slide.md                         # the one slide for leadership (M5)
├── requirements.txt
└── .env                             # LLM_PROVIDER + your API key (never commit this)
```

> **Read it bottom-up.** Tools are the hands (plain Python that loads and calculates). Agents are the
> brains (an LLM + instructions + which hands they may use). The orchestrator is the manager.

## Setup

```bash
python3.12 -m venv .venv          # Python 3.11–3.13
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then paste your free API key in .env
```

### Free API key (no OpenAI needed)

The project runs on **Google Gemini's free tier** by default. Any OpenAI-compatible provider works,
because the Agents SDK only needs a Chat Completions endpoint ([llm.py](nps_insights_agent/llm.py)).

| `LLM_PROVIDER` | Key variable | Get a free key | Default model |
|---|---|---|---|
| `gemini` (default) | `GEMINI_API_KEY` | https://aistudio.google.com/apikey | `gemini-3.5-flash-lite` |
| `groq` | `GROQ_API_KEY` | https://console.groq.com/keys | `openai/gpt-oss-120b` (see note) |
| `openrouter` | `OPENROUTER_API_KEY` | https://openrouter.ai/keys | `meta-llama/llama-3.3-70b-instruct:free` |
| `openai` (paid) | `OPENAI_API_KEY` | https://platform.openai.com/api-keys | `gpt-4o` |

`.env` for Gemini:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
```
Free tiers limit requests per minute and per day, so `llm.py` spaces requests out (4.5 s apart on Gemini)
and retries on rate-limit errors. A full run uses about 13 requests and takes about 70 seconds.
Change the spacing with `NPS_MIN_SECONDS_BETWEEN_CALLS`, or the model with `NPS_MODEL`.

Free-tier notes (tested on 2026-11-10):
- **Gemini:** quotas are per model and per day. `gemini-2.5-flash` allows only 20 requests per day
  (about one run). `gemini-3.5-flash-lite` works well and supports parallel tool calls. If you hit a
  429 "quota exceeded" error, switch model with `NPS_MODEL=...` or wait for the daily reset.
- **Groq:** the free tier caps a model at 8,000 tokens per minute. One orchestrator request is close to that,
  so full runs usually fail with error 413. Use Groq for small experiments only.

## Run it, milestone by milestone

| Milestone | Command | Done when |
|---|---|---|
| M0 · Data | `python nps_by_hand.py` | prints Overall NPS +18.5 and the three months |
| M1 · Hands | `python try_tools.py` | prints every tool's result and `CROSS-CHECK PASSED` |
| Tests | `python -m tests.test_offline` | 8 offline tests pass (tools, bad input, fact checker) |
| M3 · The team | `python -m nps_insights_agent.main --trace --log-dir logs` | trace shows three `CALL` lines before any `OUTPUT` |
| M4 · Trust | run the M3 command 3 times | wording differs, `FACT CHECK: PASSED` every time |
| Re-check a brief | `python -m nps_insights_agent.fact_check logs/run_*/brief.md` | all checks PASS |

Flags: `--trace` (CALL/OUTPUT lines), `--verbose` (every specialist's full report), `--stream` (stream the
final text), `--log-dir DIR` (saves `brief.md`, `trace.txt`, `fact_check.txt`, `handoffs.json`),
`--survey FILE` (any CSV with the same columns), `--model NAME`, `--max-rewrites N`.

Expected trace shape (phase 1 in parallel):
```
[   0.0s] START  provider=gemini model=gemini-3.5-flash-lite survey=.../data/nps_survey.csv
[   1.9s] CALL   score_analyst      input='{"input":"Analyse the NPS survey."}'
[   1.9s] CALL   voice_of_customer  input='{"input":"Analyse the NPS survey."}'
[   1.9s] CALL   churn_risk         input='{"input":"Analyse the NPS survey."}'
[  14.2s] OUTPUT voice_of_customer  (...)
[  16.8s] OUTPUT score_analyst      (...)
[  18.0s] OUTPUT churn_risk         (...)
[  19.5s] CALL   action_planner     ...
...
[  60.1s] DONE   fact check PASSED after 0 rewrite(s)
```

## Website

```bash
python -m web.server          # then open http://127.0.0.1:8000
```

- **Dashboard:** KPI tiles and charts for the three stories. All numbers come straight from the tools (no LLM),
  with hover tooltips, keyboard support and a "Show as table" view on every chart.
- **Leadership brief:** pick any saved run from `logs/` and see its brief, fact check and trace.
- **Run the agents:** one button runs the full team and streams the trace live. The pipeline diagram lights up
  as each agent starts and finishes, so you can watch phase 1 run in parallel.
- Light and dark mode. Files: [web/server.py](web/server.py) (FastAPI) and [web/static/](web/static/).

## What the tools find (the three hidden stories)

All figures below come straight from the tools (`python try_tools.py`).

1. **What caused the drop: login/OTP failures after the app update.** NPS went +32.0 (Jul) → +30.0 (Aug)
   → −6.5 (Sep). `login_otp_failure` mentions went 1 → 2 → 48. In September, customers mentioning it
   score −87.5; everyone else scores +19.1. Mobile App NPS in September is −33.6, while Branch holds at +34.4.
   Many of these comments never say "OTP" ("the app keeps asking for a code that never comes"), so the
   keyword rules include synonyms.
2. **Where the money sits: Wealth, and fees. Loud ≠ expensive.** ₹37.98 lakh of ₹304.43 lakh revenue is
   at risk (12.5%). Wealth has 103 of 600 customers but 83.0% of the money at risk. The loudest complaint
   is the call centre (61 customers, ₹4.73 lakh at risk). The costliest is fees (24 customers, ₹10.66 lakh).
   - Fix ranking by NPS points (all months): `login_otp_failure` +7.5 first.
   - Fix ranking by rupees saved: `fees_charges` ₹6.40 lakh first.
   - So there are two tracks: the app team fixes OTP (the NPS drop) and the Wealth team fixes fee
     transparency (the money).
3. **Data-quality problem in the scores.** 9 customers gave 0–1 with glowing comments (for example R0003,
   score 0: "Amazing support from the branch team, thank you."). They probably flipped the scale. Scores are
   never changed. The brief reports NPS as recorded +18.5, +21.5 if those scores were reversed, and +20.3 if
   they were excluded.

## Design choices

- **Verdicts in code.** Health (latest NPS and month-on-month change), risk (share of revenue at risk) and
  the overall alert (the worse of the two) are computed in `survey_tools.py` with thresholds from `config.py`.
- **Display strings from tools.** Tools return `nps_display: "+18.5"` and `*_lakh` fields, so the LLM
  copies signed values and never counts zeros.
- **Margin of error and the low-sample rule.** Every NPS has a 95% MoE. Segments with n < 30 are tagged
  `low_sample` and excluded from best/worst in code (e.g. Call Centre in Sep 2026: n=26).
- **Fixed hand-off forms, built by code.** Each specialist writes a report with exact keys (`SCORE_REPORT`,
  `HEADLINE_NPS:`, `OVERALL_ALERT_LEVEL:` ...). A `HandoffBoard` saves each report through
  `as_tool(custom_output_extractor=...)` and gives the orchestrator a short receipt. Later specialists get
  the reports they need as a `HAND-OFF FORM` attached by `as_tool(input_builder=...)`. The orchestrator
  decides *when* each phase runs but never retypes a report: no copy errors, and far fewer tokens.
- **One turn per specialist.** Each specialist calls all its tools in parallel in one turn. Tools accept
  `month="latest"` / `"worst"`, so no lookup call is needed first. A full run is about 13 LLM requests.
  If the orchestrator alters the writer's brief, `main.py` falls back to the writer's exact text.
- **The auditor.** `fact_check.py` checks the overall NPS, each month's NPS *on the line naming that month*
  (label-aware), the alert level, revenue at risk, both top fixes, the mismatch count, the alternative NPS,
  churn assumptions, low-sample caveats and NPS-never-as-%. It also flags **any number in the brief that no
  tool produced**.
- **Never crash.** Every tool catches errors and returns `{"error": ...}` JSON. Bad CSVs fail with a clear message.

## Stretch goals done
1. **LLM theme tagger.** `python -m stretch.llm_theme_tagger` uses a `Literal[...]` theme list and caches to CSV.
2. **Guardrail.** A failed fact check sends the brief back to ReportWriter with the failed checks, at most twice.
3. **Label-aware fact check.** Built into `fact_check.py`.
5. **Your own data.** `--survey other.csv`; edit `SEGMENT_COLUMNS` / `THEMES` in `config.py`.

## Caveats
- Churn rates (3% / 10% / 25%) are illustrative assumptions, set in `config.py`.
- Themes come from keyword rules. The stretch tagger cross-checks them with an LLM.
- A fix is assumed to turn a detractor into a passive (conservative).
