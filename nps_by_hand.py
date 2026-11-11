"""
Step 0 (M0): NPS in plain pandas. No LLM, no project code.
This is the independent answer key the tools must agree with.

Run: python nps_by_hand.py [path/to/survey.csv]
"""
import sys

import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "data/nps_survey.csv"
df = pd.read_csv(path)


def nps(scores: pd.Series) -> float:
    """% promoters (9-10) minus % detractors (0-6)."""
    promoters = (scores >= 9).mean() * 100
    detractors = (scores <= 6).mean() * 100
    return round(promoters - detractors, 1)


print(f"Responses: {len(df)}")
print(f"Promoters: {(df.score >= 9).sum()}  Passives: {df.score.between(7, 8).sum()}  "
      f"Detractors: {(df.score <= 6).sum()}")
print(f"Overall NPS {nps(df.score):+.1f}")
for month, g in df.groupby("month"):
    print(f"  {month}: NPS {nps(g.score):+.1f}  (n={len(g)})")
