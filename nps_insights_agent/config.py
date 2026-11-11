"""
config.py: every rule, threshold and assumption in one place.

Code computes, agents reason. Anything numeric that an agent might be
tempted to invent (thresholds, churn rates, units) lives here so tools
can apply it the same way on every run.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SURVEY_PATH = os.getenv("NPS_SURVEY_PATH", str(PROJECT_ROOT / "data" / "nps_survey.csv"))

# ---------------------------------------------------------------------------
# LLM provider. All of these speak the OpenAI Chat Completions format, so the
# Agents SDK works with any of them (see llm.py). Pick one with LLM_PROVIDER.
#   gemini     free tier, key from https://aistudio.google.com/apikey  (default)
#   groq       free tier, key from https://console.groq.com/keys
#   openrouter free ":free" models, key from https://openrouter.ai/keys
#   openai     paid
# min_interval_s spaces out requests to stay under free-tier rate limits.
# parallel_param: send parallel_tool_calls=True (only where the API accepts it).
# ---------------------------------------------------------------------------
PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-3.5-flash-lite",
        "min_interval_s": 4.5,      # free tier ~15 requests/minute
        "parallel_param": False,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "openai/gpt-oss-120b",
        "min_interval_s": 2.5,
        "parallel_param": True,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "min_interval_s": 3.5,      # free models ~20 requests/minute
        "parallel_param": True,
    },
    "openai": {
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "min_interval_s": 0.0,
        "parallel_param": True,
    },
}
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
if PROVIDER not in PROVIDERS:
    raise ValueError(f"LLM_PROVIDER must be one of {list(PROVIDERS)}, got {PROVIDER!r}")
PROVIDER_CFG = PROVIDERS[PROVIDER]
MODEL = os.getenv("NPS_MODEL") or PROVIDER_CFG["default_model"]
MIN_INTERVAL_S = float(os.getenv("NPS_MIN_SECONDS_BETWEEN_CALLS", PROVIDER_CFG["min_interval_s"]))

# Columns the survey must have. Any CSV with these columns works (--survey).
REQUIRED_COLUMNS = [
    "response_id", "date", "month", "product", "tenure",
    "channel", "score", "comment", "annual_revenue_inr",
]
# Columns we are allowed to slice by. Edit this for a different survey.
SEGMENT_COLUMNS = ["month", "product", "tenure", "channel"]

# ---------------------------------------------------------------------------
# NPS rules
# ---------------------------------------------------------------------------
PROMOTER_MIN = 9      # 9-10 promoter
PASSIVE_MIN = 7       # 7-8 passive, 0-6 detractor
LOW_SAMPLE_N = 30     # segments smaller than this are tagged low_sample
Z_95 = 1.96           # 95% confidence for the margin of error

# ---------------------------------------------------------------------------
# Money assumptions (MUST be listed under DATA CAVEATS in the brief)
# Illustrative yearly churn probability by NPS bucket.
# ---------------------------------------------------------------------------
CHURN_RATES = {"promoter": 0.03, "passive": 0.10, "detractor": 0.25}
LAKH = 100_000        # 1 lakh = Rs 1,00,000. Tools report money in lakh.

# What a fix does in estimate_fix_impact (conservative assumption):
# a detractor whose complaint is fixed becomes a passive.
FIX_MOVES_DETRACTOR_TO = "passive"

# ---------------------------------------------------------------------------
# Verdict thresholds (alerts come from code, never from the LLM)
# ---------------------------------------------------------------------------
# Health verdict from NPS
HEALTH_RED_LATEST_NPS = 0        # latest month NPS below this -> RED
HEALTH_RED_MONTH_DROP = -20      # month-on-month change at or below this -> RED
HEALTH_AMBER_LATEST_NPS = 20     # latest month NPS below this -> AMBER
HEALTH_AMBER_MONTH_DROP = -10    # month-on-month change at or below this -> AMBER

# Risk verdict from revenue at risk as a share of total revenue
RISK_RED_SHARE = 0.15            # >= 15% of revenue at risk -> RED
RISK_AMBER_SHARE = 0.10          # >= 10% -> AMBER

ALERT_ORDER = ["GREEN", "AMBER", "RED"]

# ---------------------------------------------------------------------------
# Comment themes (keyword rules).
# Matching is whole-word and case-insensitive (so "fee" does not match "feel").
# polarity: "complaint" | "praise" | "neutral"
# Synonyms matter: many login complaints never say "OTP".
# ---------------------------------------------------------------------------
THEMES = {
    # ---- complaints ----
    "login_otp_failure": {
        "polarity": "complaint",
        "label": "Login / OTP failures after the app update",
        "owner": "Digital / App team",
        "keywords": [
            "otp", "verification code", "code that never comes", "logging me out",
            "locked out", "login", "get into my account", "after the update",
            "since the last app update", "new version",
        ],
    },
    "app_performance": {
        "polarity": "complaint",
        "label": "App slow / crashes / glitches",
        "owner": "Digital / App team",
        "keywords": [
            "app is slow", "slow during peak", "crashes", "freezes", "hangs",
            "glitches", "retry payments",
        ],
    },
    "fees_charges": {
        "polarity": "complaint",
        "label": "Fees and charges (hidden / unexplained)",
        "owner": "Wealth & pricing team",
        "keywords": [
            "fee", "fees", "charges", "charged", "hidden costs", "penalty",
            "paying so much",
        ],
    },
    "interest_rates": {
        "polarity": "complaint",
        "label": "Uncompetitive interest / FD rates",
        "owner": "Treasury / product team",
        "keywords": ["interest rate", "interest rates", "fd rates", "earns more at other banks"],
    },
    "call_centre_service": {
        "polarity": "complaint",
        "label": "Call centre waits, IVR loops, late callbacks",
        "owner": "Contact centre operations",
        "keywords": [
            "on hold", "ivr", "waiting time", "wait a long time", "call dropped",
            "callback was promised", "complaint still open",
        ],
    },
    "rewards_expiry": {
        "polarity": "complaint",
        "label": "Reward points expire too quickly",
        "owner": "Cards team",
        "keywords": ["points expire"],
    },
    "general_dissatisfaction": {
        "polarity": "complaint",
        "label": "General dissatisfaction (no specific reason)",
        "owner": "CX team",
        "keywords": ["not happy with the service"],
    },
    # ---- praise ----
    "digital_praise": {
        "polarity": "praise",
        "label": "Fast, easy app and payments",
        "keywords": [
            "easy to use", "super quick", "seamless", "love the app",
            "transfers are fast", "fully online",
        ],
    },
    "branch_staff_praise": {
        "polarity": "praise",
        "label": "Helpful branch staff",
        "keywords": ["branch team", "branch staff"],
    },
    "relationship_manager_praise": {
        "polarity": "praise",
        "label": "Helpful relationship manager",
        "keywords": ["rm", "relationship manager"],
    },
    "rewards_praise": {
        "polarity": "praise",
        "label": "Useful cashback / rewards",
        "keywords": ["cashback", "actually useful"],
    },
    "general_praise": {
        "polarity": "praise",
        "label": "General satisfaction",
        "keywords": [
            "good bank", "happy with the overall", "excellent service",
            "best bank", "feel safe", "amazing support", "thank you",
        ],
    },
    # ---- neutral ----
    "neutral_ok": {
        "polarity": "neutral",
        "label": "Neutral / average",
        "keywords": ["average experience", "does the job", "nothing special", "otherwise fine", "otherwise okay"],
    },
}

# Strong positive words used by the mismatch detector (low score + glowing comment)
STRONG_POSITIVE_WORDS = [
    "excellent", "amazing", "best bank", "love", "very happy", "thank you",
    "seamless", "smooth", "super quick",
]

# ---------------------------------------------------------------------------
# House rules: grounding rules appended to every agent's instructions.
# ---------------------------------------------------------------------------
HOUSE_RULES = """
HOUSE RULES (apply to every answer):
G1. Code computes, you reason. Every number you write must be copied exactly
    from a tool result or from the hand-off form you were given. Never add,
    subtract, average, round or estimate numbers yourself.
G2. NPS is a score, not a percentage. Write it with its sign exactly as the
    tool's *_display field shows it: "+18.5", "-6.5". Never "18.5%".
G3. Money is in ₹ lakh, copied from the *_lakh fields (e.g. "₹37.98 lakh").
G4. Any segment flagged low_sample (n < 30) must never be called best or worst.
    Mention it only with its margin of error and the words "low sample".
G5. Quotes must be copied word for word from tool results, with response_id.
G6. Verdicts and alert levels (GREEN / AMBER / RED) come from tool fields
    (health_verdict, risk_verdict, overall_alert_level). Never invent one.
G7. If a tool returns {"error": ...}, say so in your report; do not guess.
G8. Use the exact section labels given in your OUTPUT FORMAT, in that order.
"""
