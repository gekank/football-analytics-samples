"""
Possession-normalised defensive KPIs.

Why this exists
---------------
Defensive actions — tackles, interceptions, blocks, clearances, fouls — are made
by the team WITHOUT the ball. A centre-back whose side holds 66% of possession
spends roughly half as long defending as one whose side holds 43%, and will post
lower per-90 figures even if he is the better defender. Raw per-90 defensive
numbers therefore measure a team's style, not a player's quality.

The correction follows Phatak, Rein & Memmert (chapter 20 of Memmert, D. (ed.),
*Match Analysis: How to Use Data in Professional Sport*, Routledge 2022; see also
Phatak et al., "Context is key", PMC8782855):

    normalised_kpi = kpi_per_90 / (1 - possession_share)

In the authors' sample (five top leagues, 2017/18–2020/21) the sign of the
relationship with expected goals against flips once this is applied: blocks move
from +10.98 to -4.01, tackles + interceptions from +10.09 to -5.52. A model using
normalised KPIs explained 57.8% of variance against 49.9% for raw KPIs.

Validation on our own data
--------------------------
La Liga 2015/16, 77 centre-backs with 1,800+ minutes. Mascherano moves from 58th
to 15th and Dani Alves from 49th to 9th — both Barcelona, 66% possession — while
Sporting Gijón's defenders (43%) drop 15–17 places. The direction of the effect
matches the published research.

Author: Evgeny Telis
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

# Defensive KPIs that are distorted by possession, mapped to their normalised names.
NORMALISED_KPIS: dict[str, str] = {
    "tkl_int_90": "tkl_int_90_norm",
    "blocks_90": "blocks_90_norm",
    "clearances_90": "clearances_90_norm",
    "pressures_90": "pressures_90_norm",
    "fouls_90": "fouls_90_norm",
}

# Floor on time spent out of possession. Without it, a side with extreme
# possession would divide by a near-zero denominator and produce absurd values.
MIN_OUT_OF_POSSESSION = 0.20

# A match needs enough passes before the possession share means anything.
MIN_PASSES_PER_MATCH = 100


def possession_from_events(events_dir: Path) -> dict[str, float]:
    """Derive each team's mean possession share from event data.

    Possession is approximated as a team's share of all passes in a match. This
    avoids depending on a provider-supplied possession figure, which is not
    present in every feed and is computed differently by different providers.

    Validated on La Liga 2015/16: Barcelona 66%, Atlético Madrid 47%, the bottom
    sides around 40% — consistent with the published figures for that season.

    Returns
    -------
    dict
        Team name -> mean possession share across matches, in the range 0..1.
    """
    per_team: dict[str, list[float]] = defaultdict(list)

    for match_file in sorted(events_dir.glob("*.json")):
        with match_file.open(encoding="utf-8") as fh:
            events = json.load(fh)

        passes: dict[str, int] = defaultdict(int)
        for event in events:
            if event["type"]["name"] == "Pass" and event.get("team"):
                passes[event["team"]["name"]] += 1

        total = sum(passes.values())
        # Skip abandoned or partially recorded matches, and anything that does
        # not have exactly two teams on file.
        if total < MIN_PASSES_PER_MATCH or len(passes) != 2:
            continue

        for team, count in passes.items():
            per_team[team].append(count / total)

    return {team: sum(shares) / len(shares) for team, shares in per_team.items() if shares}


def add_normalised_kpis(players: pd.DataFrame) -> pd.DataFrame:
    """Add possession-normalised versions of the defensive KPIs.

    Expects a ``team_possession`` column holding each player's team possession
    share (0..1). If it is absent the frame is returned untouched, so that the
    caller degrades gracefully rather than failing on an incomplete dataset.

    Note on use: normalised figures are for comparing players across different
    teams. Within a single squad the raw per-90 values are the right ones, since
    every player shares the same possession context.
    """
    if "team_possession" not in players.columns:
        return players

    possession = pd.to_numeric(players["team_possession"], errors="coerce")
    out_of_possession = (1 - possession).clip(lower=MIN_OUT_OF_POSSESSION)

    for raw, normalised in NORMALISED_KPIS.items():
        if raw in players.columns:
            players[normalised] = players[raw] / out_of_possession

    return players


if __name__ == "__main__":
    # Minimal demonstration against the La Liga 2015/16 dataset.
    players = pd.read_parquet("data/derived/laliga/players.parquet")
    centre_backs = players[
        players.primary_position.str.contains("Back", na=False)
        & (players.minutes >= 1800)
    ].copy()

    centre_backs["tkl_int_90"] = (
        (centre_backs.tackles + centre_backs.interceptions) / centre_backs.minutes * 90
    )
    centre_backs = add_normalised_kpis(centre_backs)

    comparison = centre_backs.assign(
        rank_raw=centre_backs.tkl_int_90.rank(ascending=False),
        rank_normalised=centre_backs.tkl_int_90_norm.rank(ascending=False),
    ).sort_values("rank_normalised")

    print(
        comparison[
            ["player", "team", "team_possession", "tkl_int_90",
             "tkl_int_90_norm", "rank_raw", "rank_normalised"]
        ].head(10).to_string(index=False)
    )
