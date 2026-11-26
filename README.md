# Football Analytics — Code Samples

Two self-contained samples from a football analytics system I built and run in
production. The system ingests event data, derives ~70 performance indicators per
player, evaluates players against position profiles and generates finished PDF
reports — opposition analysis, player assessments, recruitment shortlists and
squad gap analysis — in two languages.

These two files were chosen because they show the two things the work actually
requires: knowing which football question to ask, and building something that
answers it reliably.

---

## `possession_normalisation.py`

**Problem.** Tackles, interceptions, blocks and fouls are made by the team *without*
the ball. A centre-back whose side holds 66% of possession defends for roughly half
as long as one whose side holds 43%, and posts lower per-90 numbers even if he is
the better defender. Raw per-90 defensive figures measure a team's style, not a
player's quality.

**Approach.** Normalise by time out of possession, following Phatak, Rein & Memmert
(chapter 20 of *Match Analysis*, Routledge 2022):

```
normalised_kpi = kpi_per_90 / (1 - possession_share)
```

Possession is derived from the event feed itself — a team's share of all passes in
a match — rather than taken from a provider field, since that field is absent from
some feeds and computed differently by others.

**Result on our data.** La Liga 2015/16, 77 centre-backs with 1,800+ minutes:

| Player | Team | Possession | Rank before → after |
|---|---|---|---|
| Javier Mascherano | Barcelona | 66% | 58th → **15th** |
| Dani Alves | Barcelona | 66% | 49th → **9th** |
| Sporting Gijón defenders | | 43% | drop 15–17 places |

The direction matches the published research, where the sign of the relationship
with expected goals against flips once the correction is applied.

---

## `player_evaluation.py`

**Problem.** Comparing players across teams and competitions without the comparison
collapsing into opinion.

**Approach.** The actuarial procedure Kahneman describes for structured judgement,
and which Lawlor, Rookwood & Wright (2021) recommend for football scouting: pick a
limited set of measurable variables, decide the weights, fix a scale, aggregate by a
formula defined in advance, use the result to inform the decision.

**Design decisions worth noting.**

* Percentile ranks within the positional pool, so metrics on different units compare.
* Weights come from position profiles set *with scouts*, not fitted to data. For
  centre-backs, tackle volume is deliberately not weighted heavily — the best ones
  defend with position and make fewer tackles.
* Output uses the 4–10 scale scouts already read, not a bespoke one.
* The model reports what it cannot see. Small samples and uneven profiles become
  explicit risk flags; off-ball movement, physical condition and mentality are not
  in event data, and the model says so instead of inventing a proxy.

A player can score well and still return *monitor* rather than *sign* — that is the
intended behaviour, not a bug.

---

## Notes

Both files run against a players table derived from StatsBomb open data. They are
extracts, not the full system: the production code also covers data ingestion,
match-level opposition analysis, set-piece breakdown, squad gap analysis and
report rendering.

Written by **Evgenii Telis** — football scout and data analyst.
[LinkedIn](https://www.linkedin.com/in/jacktelis/)
