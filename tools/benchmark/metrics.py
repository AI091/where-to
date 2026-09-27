#!/usr/bin/env python3
"""
Deviation metrics for the discretization benchmark.  STUBS — not computed yet.

Status (2026-07-30): the loaders and the stop-geometry helper below are
implemented and tested against the smoke-test output; every metric function
raises NotImplementedError on purpose.  Tonight's deliverable is the harness and
one smoke-tested variant; the metrics are computed once the full spacing matrix
has been run, so that they are written against real result files rather than
guessed-at ones.  Each stub carries the precise definition it must implement,
including the judgement calls that still need a decision.

VOCABULARY
----------
variant        one GTFS feed at one synthetic-stop spacing, e.g. `spacing_500m`.
               `fixed` is the no-synthetic-stops control.
dense baseline the finest spacing available, normally `spacing_10m`.  Standing
               in for "true continuous boarding".  research-plan.md also wants a
               25 m -> 10 m convergence check: if the 25 m results are already
               within noise of the 10 m results, dense really does approximate
               continuous and the baseline is trustworthy.
best duration  shortest `duration` among a pair's itineraries that contain at
               least one transit leg.  Walk-only itineraries are excluded
               because they are spacing-invariant and would mask the signal.

INPUTS
------
    data/results/<variant>/queries.csv       one row per OD pair
    data/results/<variant>/itineraries.csv   one row per itinerary
    data/results/<variant>/query_meta.json   run params + latency distribution
    data/otp/<variant>/run_meta.json         build time, graph size, RSS
    data/variants/<variant>.zip              stop coordinates (for stop distances)

USAGE (once implemented)
------------------------
    python3 benchmark/metrics.py report --baseline spacing_10m
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from variants import VARIANTS_DIR, haversine, read_csv_from_zip
from query import RESULTS_DIR
from run_otp import OTP_DIR

DENSE_BASELINE = "spacing_10m"
CONVERGENCE_CHECK = ("spacing_25m", "spacing_10m")
NEAR_DUPLICATE_DURATION_TOLERANCE_S = 60


# --- loaders (implemented) ---------------------------------------------------
def load_queries(variant: str) -> dict[str, dict]:
    """pair_id -> query row, numeric fields coerced. Empty strings stay None."""
    path = RESULTS_DIR / variant / "queries.csv"
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            for k in ("latency_ms", "straight_km", "best_walk_m"):
                r[k] = float(r[k]) if r[k] else None
            for k in ("n_itineraries", "best_duration_s", "n_transit_itineraries"):
                r[k] = int(r[k]) if r[k] else None
            out[r["pair_id"]] = r
    return out


def load_itineraries(variant: str) -> dict[str, list[dict]]:
    """pair_id -> list of itinerary rows in the order OTP returned them."""
    path = RESULTS_DIR / variant / "itineraries.csv"
    out: dict[str, list[dict]] = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            for k in (
                "itin_index",
                "duration_s",
                "n_legs",
                "n_transit_legs",
                "synthetic_boardings",
            ):
                r[k] = int(r[k]) if r[k] else None
            for k in ("walk_distance_m", "walk_time_s", "waiting_time_s", "transit_time_s"):
                r[k] = float(r[k]) if r[k] else None
            r["board_stops"] = [s for s in (r["board_stops"] or "").split("|") if s]
            r["alight_stops"] = [s for s in (r["alight_stops"] or "").split("|") if s]
            out.setdefault(r["pair_id"], []).append(r)
    return out


def load_run_meta(variant: str) -> dict:
    """Build time / graph size / RSS, as recorded by run_otp.py."""
    return json.loads((OTP_DIR / variant / "run_meta.json").read_text())


def load_query_meta(variant: str) -> dict:
    return json.loads((RESULTS_DIR / variant / "query_meta.json").read_text())


def stop_coords(variant: str) -> dict[str, tuple[float, float]]:
    """gtfsId-suffix -> (lat, lon) for every stop in the variant feed.

    OTP returns stop ids namespaced by feed (`<feedId>:<stop_id>`), while the zip
    holds bare `stop_id`s.  Both keys are inserted so callers can look up either.
    """
    zip_path = VARIANTS_DIR / f"{variant}.zip"
    out: dict[str, tuple[float, float]] = {}
    for s in read_csv_from_zip(str(zip_path), "stops.txt"):
        latlon = (float(s["stop_lat"]), float(s["stop_lon"]))
        out[s["stop_id"]] = latlon
    return out


def stop_distance_m(coords: dict, a: str, b: str) -> float | None:
    """Great-circle metres between two OTP stop ids, tolerating the feed prefix."""
    pa = coords.get(a) or coords.get(a.split(":")[-1])
    pb = coords.get(b) or coords.get(b.split(":")[-1])
    if pa is None or pb is None:
        return None
    return haversine(pa[0], pa[1], pb[0], pb[1])


# --- metric stubs ------------------------------------------------------------
def best_duration_delta(variant: str, baseline: str = DENSE_BASELINE) -> dict:
    """METRIC 1 — per-OD best-duration deviation from the dense baseline.

    For every OD pair present in both runs:

        delta_s = best_duration(variant) - best_duration(baseline)

    where best_duration is the minimum `duration_s` over that pair's itineraries
    with at least one transit leg.  Report the *distribution* of delta_s (min,
    p25, median, p75, p90, p95, max, mean, and the share of pairs with
    |delta| <= 60 s), not a single mean — research-plan.md asks for
    distributions, and the interesting failure mode is a heavy right tail on a
    minority of pairs rather than a shifted average.

    Expected sign: positive.  Coarser spacing means the nearest boardable point
    is further from the true optimum, so the traveller walks further or rides
    past their destination; both cost time.  A *negative* delta is a red flag
    worth chasing (typically a coarse feed's interpolated stop_times happening to
    align better with the search window, i.e. an artefact of the interpolation,
    not a routing win).

    Three cases need separate accounting, not silent dropping:
      * pair has transit in baseline but not in variant -> `lost_transit`.  This
        is the most damaging discretization failure (the trip becomes
        unroutable) and must be reported as a count, since it has no finite
        delta.
      * pair has transit in variant but not in baseline -> `gained_transit`.
      * pair has transit in neither -> `no_transit_either`, excluded.

    Normalise as well as report raw seconds: delta_s / baseline_duration_s gives
    a relative deviation whose distribution is comparable across the OD distance
    bands from od_pairs.py, and the raw seconds alone will look worse for the
    20-70 km band purely because those trips are longer.

    DECISION STILL OPEN: whether to also report the delta of `walk_distance_m`
    of the best itinerary as a paired metric.  It should be reported — it is the
    mechanism behind the duration delta, and a spacing that costs 300 m of extra
    walking but no extra time (because the walk replaces waiting) is a
    materially different finding from one that costs time.

    Returns: {"deltas": {pair_id: delta_s}, "distribution": {...},
              "lost_transit": [...], "gained_transit": [...],
              "no_transit_either": [...]}
    """
    raise NotImplementedError("computed after the full spacing matrix runs")


def near_duplicate_count(variant: str, spacing_m: float | None = None) -> dict:
    """METRIC 2 — itineraries that are the same trip wearing a different stop.

    The worry: discretization gives Raptor N nearly identical boarding options
    per route, so OTP's itinerary filter emits several results that differ only
    in which synthetic stop was used.  A rider sees "5 options" that are one
    option.  This metric counts that pollution.

    Two itineraries of the same OD pair are near-duplicates iff ALL of:
      1. identical `route_sequence` (the ordered list of route gtfsIds over the
         transit legs) — a different route sequence is a genuinely different
         trip, however similar the timing;
      2. every corresponding board stop pair is within `spacing_m` metres, and
         likewise every alight stop pair (great-circle, via stop_distance_m).
         One spacing is the right threshold because it is exactly the resolution
         at which the discretization cannot distinguish two boarding points;
      3. |duration difference| <= NEAR_DUPLICATE_DURATION_TOLERANCE_S (60 s).

    `spacing_m` defaults to the variant's own `spacing_m` from
    data/variants/<variant>.json.  Note this makes the threshold vary with the
    variant by design (the question is "duplicates at this feed's own
    resolution"); a secondary run with a *fixed* threshold across all variants is
    also worth reporting, because a spacing-scaled threshold flatters coarse
    feeds.

    Group by transitive closure within a pair, then per OD pair report
    `n_itineraries`, `n_distinct_groups`, and
    `n_near_duplicates = n_itineraries - n_distinct_groups`.  Aggregate over
    pairs as a distribution plus the mean duplicates per pair, and correlate
    against spacing: the expected result is duplicates rising as spacing falls,
    which would be the headline cost of a dense feed.

    CONFOUND TO CONTROL FOR: OTP's own itinerary filter chain
    (`numItineraries`, groupSimilarity) already suppresses some duplicates
    *before* they reach us, and `numItineraries=5` truncates the list.  So this
    metric measures duplicates that survive OTP's filter, which is the
    user-visible quantity but not the raw Raptor output.  If the counts come out
    at zero everywhere, re-run with a larger numItineraries and/or a relaxed
    filter before concluding the problem does not exist.

    Returns: {"per_pair": {pair_id: {...}}, "distribution": {...},
              "threshold_m": spacing_m}
    """
    raise NotImplementedError("computed after the full spacing matrix runs")


def convergence_check(fine: str = "spacing_10m", coarse: str = "spacing_25m") -> dict:
    """Does 25 m already behave like 10 m? Certifies the dense baseline.

    Run best_duration_delta(coarse, baseline=fine) and check that the deviation
    distribution is negligible (proposed threshold: p95 |delta| <= 60 s and no
    lost_transit pairs).  If it is not negligible, 25 m is not converged, the
    baseline must move to 10 m or finer, and every deviation number measured
    against 25 m is suspect.  research-plan.md calls this the
    "25 m -> 10 m convergence check proving dense ~ continuous".
    """
    raise NotImplementedError("computed after the full spacing matrix runs")


def cost_table(variants: list[str]) -> dict:
    """The non-deviation half: what each spacing costs to build and serve.

    One row per variant, all values already recorded by the harness — no new
    computation, just collation:
      synthetic_stops, total_stop_times   (data/variants/<variant>.json)
      build_seconds, graph_obj_bytes, rss_bytes, transit_patterns
                                          (data/otp/<variant>/run_meta.json)
      latency p50/p90/p95                 (data/results/<variant>/query_meta.json)

    Watch `transit_patterns`: if it drops for a variant, that feed's stop_times
    are non-monotonic and OTP silently discarded patterns (the 2026-05-30
    failure), which invalidates that variant's deviation numbers entirely.
    """
    raise NotImplementedError("computed after the full spacing matrix runs")


def report(baseline: str = DENSE_BASELINE, variants: list[str] | None = None) -> dict:
    """Assemble every metric above into one JSON report + a markdown summary."""
    raise NotImplementedError("computed after the full spacing matrix runs")


def available_variants() -> list[str]:
    """Variants that have query results on disk."""
    if not RESULTS_DIR.exists():
        return []
    return sorted(d.name for d in RESULTS_DIR.iterdir() if (d / "queries.csv").exists())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deviation metrics (stubs)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="variants with results on disk")
    p = sub.add_parser("report")
    p.add_argument("--baseline", default=DENSE_BASELINE)
    p.add_argument("--variants", nargs="*")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for v in available_variants():
            m = load_query_meta(v)
            print(
                f"{v:20s} pairs={m['n_pairs']:4d} "
                f"with_transit={m['pairs_with_transit_itinerary']:4d} "
                f"p50={m['latency_ms']['p50']} ms"
            )
        return
    report(baseline=a.baseline, variants=a.variants)


if __name__ == "__main__":
    main()
