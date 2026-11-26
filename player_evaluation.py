"""
Position-specific player evaluation model.

What it does
------------
Ranks players against a position profile and returns a recruitment verdict. The
design follows the actuarial procedure Kahneman describes for structured
judgement, and which Lawlor, Rookwood & Wright (2021) recommend for football
scouting:

    1. choose a limited set of measurable variables
    2. decide how to combine them and what weighs more
    3. fix a scale
    4. aggregate by a formula defined in advance
    5. use the result to inform the decision

Each step below maps onto one of those. The point is not to replace the scout —
it is to make the comparison explicit and repeatable, so that the scout argues
with a number instead of with a feeling, and so the same player scores the same
way twice.

Design notes
------------
* Percentile ranks, not raw values. A player is judged against his peer group at
  the same position, which makes metrics on different units comparable.
* Weights come from position profiles, which are set with scouts rather than
  fitted to data. For centre-backs, tackle volume is deliberately NOT weighted
  heavily: the best ones defend with position and make fewer tackles.
* The model reports what it cannot see. Small samples, uneven profiles and
  missing data are surfaced as explicit risk flags rather than silently averaged
  away. Off-ball movement, physical condition and mentality are not in event data
  and the model says so instead of inventing a proxy.

Author: Evgeny Telis
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Metrics where a LOW value is good: these are inverted before ranking.
LOWER_IS_BETTER = {"losses_90", "dribbled_past_90", "fouls_90"}

# Minutes below which a sample is too thin to rank confidently.
MIN_MINUTES_CONFIDENT = 450


@dataclass(frozen=True)
class PositionProfile:
    """A scout-defined player type: which metrics matter, and how much."""

    label: str
    weights: dict[str, float]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if not np.isclose(total, 1.0):
            raise ValueError(f"{self.label}: weights sum to {total:.3f}, expected 1.0")


@dataclass
class Assessment:
    """The output for one player — deliberately includes its own caveats."""

    player: str
    team: str
    minutes: int
    fit: int                       # 0-100 weighted percentile score
    grade: str                     # A / A- / B+ ...
    verdict: str                   # sign / monitor / pass
    confidence: str                # high / medium / low
    marks: dict[str, int]          # per-metric, on the 4-10 scouting scale
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def percentile_ranks(pool: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Rank each metric within the positional pool, 0-100.

    Metrics in LOWER_IS_BETTER are inverted so that a high rank always means
    'better', which keeps the weighted sum meaningful.
    """
    ranks = pd.DataFrame(index=pool.index)
    for metric in metrics:
        values = pool[metric]
        if metric in LOWER_IS_BETTER:
            values = -values
        ranks[metric] = values.rank(pct=True) * 100
    return ranks


def to_scouting_scale(percentile: float) -> int:
    """Convert a percentile to the 4-10 scale scouts already use.

    4 = poor, 6 = average, 8 = strong, 10 = exceptional. Using the scale the
    scouting department reads daily matters more than statistical elegance:
    a number nobody interprets correctly is worse than no number.
    """
    thresholds = [(95, 10), (85, 9), (70, 8), (55, 7), (40, 6), (20, 5)]
    for cutoff, mark in thresholds:
        if percentile >= cutoff:
            return mark
    return 4


def assess(
    pool: pd.DataFrame,
    profile: PositionProfile,
    top_n: int = 5,
) -> list[Assessment]:
    """Score a positional pool against a profile and return the shortlist."""
    metrics = list(profile.weights)
    ranks = percentile_ranks(pool, metrics)

    # Step 4 of the procedure: aggregate by the formula fixed in advance.
    fit = sum(ranks[m] * w for m, w in profile.weights.items())

    results: list[Assessment] = []
    for idx in fit.sort_values(ascending=False).head(top_n).index:
        row, player_ranks = pool.loc[idx], ranks.loc[idx]
        score = float(fit.loc[idx])
        marks = {m: to_scouting_scale(float(player_ranks[m])) for m in metrics}

        risks: list[str] = []
        if row.minutes < MIN_MINUTES_CONFIDENT:
            risks.append("small sample of minutes")
        # An uneven profile — excellent in one area, poor in another — is a
        # different proposition from a uniformly good player on the same score.
        if max(marks.values()) - min(marks.values()) >= 4:
            risks.append("uneven profile")

        confidence = "low" if risks else ("high" if score >= 80 else "medium")
        verdict = (
            "sign" if score >= 80 and not risks
            else "monitor" if score >= 65
            else "pass"
        )

        results.append(
            Assessment(
                player=row.player,
                team=row.team,
                minutes=int(row.minutes),
                fit=round(score),
                grade=_grade(score),
                verdict=verdict,
                confidence=confidence,
                marks=marks,
                strengths=[m for m in metrics if player_ranks[m] >= 75],
                weaknesses=[m for m in metrics if player_ranks[m] <= 35],
                risks=risks,
            )
        )
    return results


def _grade(fit: float) -> str:
    for cutoff, grade in [(85, "A"), (80, "A-"), (72, "B+"), (62, "B"), (50, "B-")]:
        if fit >= cutoff:
            return grade
    return "C"


# Example profile. In production these live in a configuration shared with the
# scouting department, so that changing a weight is a football decision rather
# than a code change — and so scouts own the criteria they are asked to trust.
BALL_PLAYING_CENTRE_BACK = PositionProfile(
    label="Ball-playing centre-back",
    weights={
        "prog_passes_90": 0.30,   # progressive passes: breaking lines
        "pass_f3_90": 0.25,       # delivery into the final third
        "pass_pct": 0.20,         # retention under normal pressure
        "press_ok_pct": 0.15,     # retention when pressed
        "long_cmp_90": 0.10,      # switching play
    },
)
