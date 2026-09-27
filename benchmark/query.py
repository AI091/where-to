#!/usr/bin/env python3
"""
Run the frozen OD pair set against a served OTP variant and record everything.

Query shape follows README.md / bruno/Where-to/OTP raw plan.bru: a POST of a
GraphQL `plan(...)` to `/otp/gtfs/v1`, modes BUS + WALK.  Extra fields are added
because the metrics need them:

  * `walkDistance` per itinerary        -> deviation metric (walk cost of coarse
                                          spacing shows up here, not in duration)
  * `from.stop.gtfsId` / `to.stop.gtfsId` per leg
                                       -> board/alight stop identity, which is
                                          what near-duplicate detection compares
                                          (and which reveals whether the boarding
                                          point is a SYN_ stop at all)
  * `route.gtfsId` per leg             -> the route sequence key
  * `startTime` / `endTime`            -> wait time vs ride time

FIXED PARAMETERS (must be identical for every variant, else the comparison is
meaningless):
  date  2026-08-03 (a Monday; calendar.txt is daily through 2099 in this feed)
  time  08:00:00   (inside every trip's frequencies.txt window of 07:00-22:00)
  modes BUS, WALK
  numItineraries  default 5

Departure time note: this feed is entirely frequency-based (frequencies.txt has
one entry for each of the 192 trips, no exact_times column => exact_times=0), and
OTP charges a *full* headway as wait time for headway trips.  Durations therefore
carry a constant per-route wait offset.  That offset is identical across variants
so it cancels in the per-OD delta, but absolute durations should not be read as
real-world travel times.

OUTPUT (per variant, under benchmark/data/results/<variant>/)
  raw/<pair_id>.json  the untouched GraphQL response body
  queries.csv         one row per OD pair (latency, itinerary count, best duration)
  itineraries.csv     one row per itinerary (duration, walkDistance, leg summary)
  query_meta.json     run parameters + latency distribution

USAGE
-----
    python3 benchmark/query.py --variant spacing_500m --limit 20    # smoke test
    python3 benchmark/query.py --variant spacing_500m               # all 800
    python3 benchmark/query.py --variant spacing_500m --summary
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

from od_pairs import OD_CSV, load as load_od_pairs
from variants import DATA_DIR

RESULTS_DIR = DATA_DIR / "results"

DEFAULT_DATE = "2026-08-03"  # Monday
DEFAULT_TIME = "08:00:00"
DEFAULT_MODES = "BUS,WALK"
DEFAULT_NUM_ITINERARIES = 5
DEFAULT_ENDPOINT = "http://127.0.0.1:8081/otp/gtfs/v1"

# Field names verified by introspection against OTP 2.10.0-SNAPSHOT (dev-2.x).
# Two traps if this is ever ported to an older OTP: `Itinerary.transitTime` does
# not exist in 2.10 (derive it as duration - walkTime - waitingTime), and
# `startTime`/`endTime` on Itinerary and Leg were replaced by `start`/`end`
# (OffsetDateTime and LegTime respectively).
PLAN_QUERY = """
query Plan($from: InputCoordinates!, $to: InputCoordinates!, $date: String!,
           $time: String!, $modes: [TransportMode!], $num: Int) {
  plan(from: $from, to: $to, date: $date, time: $time,
       transportModes: $modes, numItineraries: $num) {
    itineraries {
      duration
      start
      end
      walkDistance
      walkTime
      waitingTime
      generalizedCost
      numberOfTransfers
      legs {
        mode
        transitLeg
        duration
        distance
        generalizedCost
        start { scheduledTime }
        end { scheduledTime }
        from { name lat lon stop { gtfsId name } }
        to   { name lat lon stop { gtfsId name } }
        route { gtfsId shortName }
        trip { gtfsId }
      }
    }
  }
}
"""

QUERY_FIELDS = [
    "pair_id",
    "band",
    "straight_km",
    "latency_ms",
    "http_status",
    "n_itineraries",
    "best_duration_s",
    "best_walk_m",
    "n_transit_itineraries",
    "error",
]

ITIN_FIELDS = [
    "pair_id",
    "itin_index",
    "duration_s",
    "generalized_cost",
    "walk_distance_m",
    "walk_time_s",
    "waiting_time_s",
    "transit_time_s",
    "n_transfers",
    "n_legs",
    "n_transit_legs",
    "route_sequence",
    "board_stops",
    "alight_stops",
    "synthetic_boardings",
    "synthetic_alightings",
]


def _modes_arg(spec: str):
    return [{"mode": m.strip().upper()} for m in spec.split(",") if m.strip()]


def post(endpoint: str, payload: dict, timeout: float) -> tuple[int, dict, float]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    latency_ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(raw)
    except Exception:
        data = {"_unparsable": raw[:2000].decode("utf-8", "replace")}
    return status, data, latency_ms


def _summarise_itinerary(pair_id: str, idx: int, itin: dict) -> dict:
    legs = itin.get("legs") or []
    transit = [l for l in legs if l.get("transitLeg")]
    route_seq = "|".join((l.get("route") or {}).get("gtfsId") or l["mode"] for l in transit)
    board = [((l.get("from") or {}).get("stop") or {}).get("gtfsId", "") for l in transit]
    alight = [((l.get("to") or {}).get("stop") or {}).get("gtfsId", "") for l in transit]
    dur = itin.get("duration") or 0
    walk_t = itin.get("walkTime") or 0
    wait_t = itin.get("waitingTime") or 0
    return {
        "pair_id": pair_id,
        "itin_index": idx,
        "duration_s": itin.get("duration"),
        "generalized_cost": itin.get("generalizedCost"),
        "walk_distance_m": round(itin.get("walkDistance") or 0.0, 1),
        "walk_time_s": walk_t,
        "waiting_time_s": wait_t,
        # OTP 2.10 dropped Itinerary.transitTime; derive it.
        "transit_time_s": max(dur - walk_t - wait_t, 0),
        "n_transfers": itin.get("numberOfTransfers"),
        "n_legs": len(legs),
        "n_transit_legs": len(transit),
        "route_sequence": route_seq,
        "board_stops": "|".join(board),
        "alight_stops": "|".join(alight),
        "synthetic_boardings": sum(1 for s in board if "SYN_" in (s or "")),
        "synthetic_alightings": sum(1 for s in alight if "SYN_" in (s or "")),
    }


def run(
    variant: str,
    endpoint: str = DEFAULT_ENDPOINT,
    limit: int | None = None,
    date: str = DEFAULT_DATE,
    dep_time: str = DEFAULT_TIME,
    modes: str = DEFAULT_MODES,
    num_itineraries: int = DEFAULT_NUM_ITINERARIES,
    timeout: float = 120.0,
    od_csv: Path = OD_CSV,
    save_raw: bool = True,
) -> dict:
    if not Path(od_csv).exists():
        raise SystemExit(f"{od_csv} missing — run: python3 benchmark/od_pairs.py")
    pairs = load_od_pairs(od_csv, limit=limit)

    out_dir = RESULTS_DIR / variant
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    mode_arg = _modes_arg(modes)

    def payload_for(p):
        return {
            "query": PLAN_QUERY,
            "variables": {
                "from": {"lat": p["from_lat"], "lon": p["from_lon"]},
                "to": {"lat": p["to_lat"], "lon": p["to_lon"]},
                "date": date,
                "time": dep_time,
                "modes": mode_arg,
                "num": num_itineraries,
            },
        }

    # Pre-flight: a GraphQL *validation* error means the query does not match this
    # OTP's schema, and every subsequent row would be silently empty. Fail loudly
    # on the first pair instead of producing 800 useless rows.
    _, probe, _ = post(endpoint, payload_for(pairs[0]), timeout)
    for e in probe.get("errors") or []:
        if (e.get("extensions") or {}).get("classification") == "ValidationError":
            raise SystemExit(
                "GraphQL schema mismatch — PLAN_QUERY does not match the served OTP:\n"
                + json.dumps(probe["errors"], indent=2)
            )
    if "_unparsable" in probe:
        raise SystemExit(f"endpoint {endpoint} did not return JSON: {probe}")

    query_rows, itin_rows, latencies = [], [], []
    n_empty = 0
    n_error = 0

    t_start = time.time()
    for i, p in enumerate(pairs, 1):
        status, data, latency_ms = post(endpoint, payload_for(p), timeout)
        latencies.append(latency_ms)
        if save_raw:
            (raw_dir / f"{p['pair_id']}.json").write_text(json.dumps(data))

        err = ""
        if data.get("errors"):
            err = json.dumps(data["errors"])[:400]
            n_error += 1
        itins = (((data.get("data") or {}).get("plan") or {}).get("itineraries")) or []
        if not itins:
            n_empty += 1

        summaries = [_summarise_itinerary(p["pair_id"], j, it) for j, it in enumerate(itins)]
        itin_rows.extend(summaries)
        transit_only = [s for s in summaries if s["n_transit_legs"] > 0]
        best = min(transit_only, key=lambda s: s["duration_s"]) if transit_only else None

        query_rows.append(
            {
                "pair_id": p["pair_id"],
                "band": p.get("band", ""),
                "straight_km": p["straight_km"],
                "latency_ms": round(latency_ms, 1),
                "http_status": status,
                "n_itineraries": len(itins),
                "best_duration_s": best["duration_s"] if best else "",
                "best_walk_m": best["walk_distance_m"] if best else "",
                "n_transit_itineraries": len(transit_only),
                "error": err,
            }
        )
        if i % 25 == 0 or i == len(pairs):
            print(
                f"  {i}/{len(pairs)}  median {statistics.median(latencies):.0f} ms  "
                f"empty {n_empty}  errors {n_error}"
            )

    _write_csv(out_dir / "queries.csv", query_rows, QUERY_FIELDS)
    _write_csv(out_dir / "itineraries.csv", itin_rows, ITIN_FIELDS)

    lat_sorted = sorted(latencies)

    def pct(q):
        return round(lat_sorted[min(int(q * len(lat_sorted)), len(lat_sorted) - 1)], 1)

    meta = {
        "variant": variant,
        "endpoint": endpoint,
        "date": date,
        "time": dep_time,
        "modes": modes,
        "num_itineraries": num_itineraries,
        "od_csv": str(od_csv),
        "n_pairs": len(pairs),
        "limit": limit,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "wall_seconds": round(time.time() - t_start, 1),
        "pairs_with_no_itinerary": n_empty,
        "pairs_with_graphql_errors": n_error,
        "pairs_with_transit_itinerary": sum(
            1 for r in query_rows if r["n_transit_itineraries"]
        ),
        "total_itineraries": len(itin_rows),
        "latency_ms": {
            "min": pct(0.0),
            "p50": pct(0.50),
            "p90": pct(0.90),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "max": lat_sorted[-1] and round(lat_sorted[-1], 1),
            "mean": round(statistics.fmean(latencies), 1),
        },
    }
    (out_dir / "query_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    return meta


def _write_csv(path: Path, rows, fields) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


def summary(variant: str) -> None:
    p = RESULTS_DIR / variant / "query_meta.json"
    if not p.exists():
        raise SystemExit(f"{p} not found")
    print(p.read_text())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query a served OTP variant")
    ap.add_argument("--variant", required=True)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument(
        "--limit", type=int, help="evenly-spaced subsample of N OD pairs (smoke test)"
    )
    ap.add_argument("--date", default=DEFAULT_DATE)
    ap.add_argument("--time", dest="dep_time", default=DEFAULT_TIME)
    ap.add_argument("--modes", default=DEFAULT_MODES)
    ap.add_argument("--num-itineraries", type=int, default=DEFAULT_NUM_ITINERARIES)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--no-raw", action="store_true", help="skip saving raw JSON")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args(argv)

    if a.summary:
        summary(a.variant)
        return
    run(
        a.variant,
        endpoint=a.endpoint,
        limit=a.limit,
        date=a.date,
        dep_time=a.dep_time,
        modes=a.modes,
        num_itineraries=a.num_itineraries,
        timeout=a.timeout,
        save_raw=not a.no_raw,
    )


if __name__ == "__main__":
    main()
