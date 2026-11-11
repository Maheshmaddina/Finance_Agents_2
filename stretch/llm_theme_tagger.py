"""
Stretch goal 1: LLM theme tagger.

Tags every unique comment with an LLM that may only answer from the fixed
theme list (a Literal type, so it cannot invent themes), caches the tags to
CSV, and compares the top detractor themes with the keyword rules.

Run: python -m stretch.llm_theme_tagger [--refresh]
Cost: one call per unique comment (~55 on the course data), cached after the first run.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Literal

import pandas as pd
from agents import Agent, Runner
from pydantic import BaseModel

from nps_insights_agent import config
from nps_insights_agent.llm import resolve_model, setup_llm
from nps_insights_agent.tools.data import load_survey
from nps_insights_agent.tools.theme_tools import tag_comment

CACHE = Path(__file__).parent / "theme_tags_cache.csv"
ThemeKey = Literal[tuple(config.THEMES.keys())]  # type: ignore[valid-type]


class Tags(BaseModel):
    themes: list[ThemeKey]  # one or more keys from the fixed list


THEME_LIST = "\n".join(f"- {k}: {t['label']} ({t['polarity']})" for k, t in config.THEMES.items())
tagger = Agent(
    name="ThemeTagger",
    instructions=f"Tag the bank customer's comment with every theme that applies, "
                 f"choosing ONLY from this list:\n{THEME_LIST}\nReturn at least one theme.",
    output_type=Tags,
    model=config.MODEL,
)


async def tag_all(comments: list[str]) -> dict[str, list[str]]:
    sem = asyncio.Semaphore(4)

    async def one(c: str) -> tuple[str, list[str]]:
        async with sem:
            r = await Runner.run(tagger, c)
            return c, list(r.final_output.themes)

    return dict(await asyncio.gather(*(one(c) for c in comments)))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--refresh", action="store_true", help="ignore the cache and re-tag")
    args = p.parse_args()

    df = load_survey()
    setup_llm()
    tagger.model = resolve_model(config.MODEL)
    comments = sorted(c for c in df["comment"].unique() if c)
    cache = {} if args.refresh or not CACHE.exists() else {
        r.comment: r.themes.split("|") for r in pd.read_csv(CACHE).itertuples()}
    todo = [c for c in comments if c not in cache]
    if todo:
        print(f"Tagging {len(todo)} new comments with {config.MODEL} ...", file=sys.stderr)
        cache.update(asyncio.run(tag_all(todo)))
        pd.DataFrame({"comment": list(cache), "themes": ["|".join(v) for v in cache.values()]}).to_csv(CACHE, index=False)

    det = df[df["bucket"] == "detractor"]
    llm = det["comment"].map(lambda c: cache.get(c, [])).explode().value_counts()
    kw = det["comment"].map(tag_comment).explode().value_counts()
    table = pd.DataFrame({"keyword_rules": kw, "llm_tagger": llm}).fillna(0).astype(int)
    print("Detractor theme counts: keyword rules vs LLM tagger\n")
    print(table.sort_values("keyword_rules", ascending=False).to_string())
    agree = sum(set(tag_comment(c)) == set(cache.get(c, [])) for c in comments)
    print(f"\nExact agreement on {agree}/{len(comments)} unique comments")


if __name__ == "__main__":
    main()
