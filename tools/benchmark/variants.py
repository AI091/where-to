#!/usr/bin/env python3
"""
Generate GTFS variants at different synthetic-stop spacings (Phase 3 benchmark).

WHY THIS EXISTS
---------------
`infra/otp/alex_gtfs.zip` in the repo is *already* discretized: it contains 7,419
synthetic hail-and-ride stops at ~200 m spacing, merged in on 2026-05-30.  The
benchmark needs the *pre-synthetic* fixed-stops feed as the seed for every
variant, so that the only variable across variants is the spacing.

WHERE THE ORIGINAL FEED LIVES (found 2026-07-30)
------------------------------------------------
Two pristine copies of the fixed-stops feed exist:

  1. `data/alexandria/data/alex_gtfs.zip` — the untouched DT4A download.
     441 stops, 2,547 stop_times, 0 synthetic stops.
     calendar.txt still ends 2023-12-30.
  2. `git show b1479e6:otp/alex_gtfs.zip` — byte-identical GTFS content except
     calendar.txt end_date extended 20231230 -> 20991231 (dataset.md change
     #1, 2026-05-29).  Commit b1479e6 is the last commit *before* d1c5e5a
     ("Merge synthetic stops into alex_gtfs.zip").

We seed from (2) — the calendar extension is a standing project decision, not a
benchmark variable, and without it OTP has no service on any date we would
query.  So no regeneration from a "non-synthetic subset" was needed; the real
original feed is recoverable from git history intact.

Source data is never modified: the base is copied out of git into
`tools/benchmark/data/base/` and all variants are written to `tools/benchmark/data/variants/`.

REUSE OF EXISTING PREPROCESSING
-------------------------------
The geometry/time primitives are imported from the existing scripts rather than
reimplemented:

  tools/gtfs/generate_hail_ride_stops.py -> haversine, build_shape_with_distances,
      generate_synthetic_stops, time_to_seconds
  tools/gtfs/merge_synthetic_stops.py    -> seconds_to_time, read_csv_from_zip

Only the *driver* is new, because the originals hardcode INTERVAL=200 and the
input/output paths, write intermediate CSVs, and (in the merge step) re-derive
each synthetic stop's shape position with an O(stops x shape_points) nearest-
point scan.  At 10 m spacing that scan is ~10^9 haversine calls, so this driver
carries the exact along-shape distance from generation straight through to
merging.  The merge *rule* is unchanged (see build_variant).

DEVIATION FROM THE ORIGINAL SCRIPTS: shape mode
-----------------------------------------------
`generate_hail_ride_stops.py` builds `route_to_shape` from the *first* trip of
each route and generates one synthetic stop set per route.  But this feed has
192 trips and 192 distinct shape_ids: 88 of 104 routes have two shapes (one per
direction_id).  Under the legacy behaviour the direction-1 trip of those 88
routes gets stops sampled along the direction-0 alignment.  That is a bug for a
benchmark whose entire subject is spatial discretization error, so the default
here is `--shape-mode per-trip` (stops sampled along each trip's own shape).
`--shape-mode legacy-per-route` reproduces the old behaviour and, at 200 m,
should approximately reproduce the counts in the committed feed (7,419 stops /
15,508 stop_times) — use `--validate` to check.

USAGE
-----
    python3 tools/benchmark/variants.py extract-base
    python3 tools/benchmark/variants.py build --spacing 500
    python3 tools/benchmark/variants.py build --all
    python3 tools/benchmark/variants.py build --spacing 200 --shape-mode legacy-per-route --validate
    python3 tools/benchmark/variants.py list
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# --- reuse the existing preprocessing primitives -----------------------------
BENCHMARK_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARK_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "gtfs"))

from generate_hail_ride_stops import (  # noqa: E402
    build_shape_with_distances,
    generate_synthetic_stops,
    haversine,
    time_to_seconds,
)
from merge_synthetic_stops import (  # noqa: E402
    read_csv_from_zip,
    seconds_to_time,
)

# --- paths -------------------------------------------------------------------
DATA_DIR = BENCHMARK_DIR / "data"
BASE_DIR = DATA_DIR / "base"
BASE_ZIP = BASE_DIR / "alex_gtfs_base.zip"
VARIANTS_DIR = DATA_DIR / "variants"

# The commit holding the pre-synthetic-stops feed with the extended calendar.
BASE_COMMIT = "b1479e6"
BASE_PATH_IN_COMMIT = "otp/alex_gtfs.zip"
# Pristine DT4A download, kept only as a cross-check (calendar ends 2023).
PRISTINE_ZIP = REPO_ROOT / "data" / "alexandria" / "data" / "alex_gtfs.zip"

# Spacings from research-plan.md Phase 3: study spacings + dense baselines.
STUDY_SPACINGS = [1000, 500, 250, 100]
DENSE_SPACINGS = [25, 10]
ALL_SPACINGS = STUDY_SPACINGS + DENSE_SPACINGS

SYN_ID_START = 100_000  # matches generate_hail_ride_stops.py's naming scheme
SYN_PREFIX = "SYN_"

STOPS_FIELDS = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
STOP_TIMES_FIELDS = [
    "trip_id",
    "stop_id",
    "stop_sequence",
    "arrival_time",
    "departure_time",
    "timepoint",
]


def variant_name(spacing: int, shape_mode: str = "per-trip") -> str:
    """Canonical variant name. spacing==0 means 'fixed stops only' (control)."""
    base = "fixed" if spacing == 0 else f"spacing_{spacing}m"
    return base if shape_mode == "per-trip" else f"{base}_legacy"


def variant_zip(spacing: int, shape_mode: str = "per-trip") -> Path:
    return VARIANTS_DIR / f"{variant_name(spacing, shape_mode)}.zip"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- base feed extraction ----------------------------------------------------
def extract_base(force: bool = False) -> Path:
    """Copy the pre-synthetic-stops feed out of git history into data/base/.

    Never reads or writes infra/otp/alex_gtfs.zip.
    """
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if BASE_ZIP.exists() and not force:
        print(f"base already present: {BASE_ZIP}")
    else:
        blob = subprocess.run(
            ["git", "show", f"{BASE_COMMIT}:{BASE_PATH_IN_COMMIT}"],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        BASE_ZIP.write_bytes(blob)
        print(f"wrote {BASE_ZIP} ({len(blob)} bytes) from {BASE_COMMIT}:{BASE_PATH_IN_COMMIT}")

    stops = read_csv_from_zip(str(BASE_ZIP), "stops.txt")
    stop_times = read_csv_from_zip(str(BASE_ZIP), "stop_times.txt")
    syn = [s for s in stops if s["stop_id"].startswith(SYN_PREFIX)]
    if syn:
        raise SystemExit(
            f"FATAL: base feed contains {len(syn)} synthetic stops — wrong commit?"
        )
    meta = {
        "source": f"git {BASE_COMMIT}:{BASE_PATH_IN_COMMIT}",
        "sha256": sha256(BASE_ZIP),
        "stops": len(stops),
        "stop_times": len(stop_times),
        "synthetic_stops": 0,
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (BASE_DIR / "base_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"base: {len(stops)} stops, {len(stop_times)} stop_times, 0 synthetic")
    return BASE_ZIP


# --- variant construction ----------------------------------------------------
def _load_base(zip_path: Path):
    p = str(zip_path)
    return {
        "stops": read_csv_from_zip(p, "stops.txt"),
        "stop_times": read_csv_from_zip(p, "stop_times.txt"),
        "shapes": read_csv_from_zip(p, "shapes.txt"),
        "trips": read_csv_from_zip(p, "trips.txt"),
        "routes": read_csv_from_zip(p, "routes.txt"),
    }


def _shapes_with_distance(shape_rows):
    """shape_id -> (list of (lat, lon, cum_dist), total_length_m)."""
    by_id: dict[str, list] = {}
    for row in shape_rows:
        by_id.setdefault(row["shape_id"], []).append(
            (
                int(row["shape_pt_sequence"]),
                float(row["shape_pt_lat"]),
                float(row["shape_pt_lon"]),
            )
        )
    out = {}
    for sid, pts in by_id.items():
        pts.sort(key=lambda p: p[0])
        out[sid] = build_shape_with_distances([(p[1], p[2]) for p in pts])
    return out


def _nearest_dist_on_shape(lat, lon, shape_with_dist):
    """Along-shape distance of the shape vertex closest to (lat, lon).

    Same rule as find_nearest_point_on_shape / find_dist_on_shape in the
    existing scripts (vertex-snapping, not perpendicular projection).
    """
    best_d = float("inf")
    best_pos = 0.0
    for slat, slon, sdist in shape_with_dist:
        d = haversine(lat, lon, slat, slon)
        if d < best_d:
            best_d = d
            best_pos = sdist
    return best_pos


def build_variant(
    spacing: int,
    shape_mode: str = "per-trip",
    base_zip: Path = BASE_ZIP,
    out_zip: Path | None = None,
    verbose: bool = True,
) -> dict:
    """Write one GTFS variant with synthetic stops every `spacing` metres.

    spacing == 0 -> straight copy of the base feed (the fixed-stops control).

    Merge rule (unchanged from tools/gtfs/merge_synthetic_stops.py):
      for every trip that gains synthetic stops, real + synthetic stop_times are
      combined, sorted by along-shape distance, re-sequenced 1..N, and *all*
      times are regenerated as
          t = t_first_real + (t_last_real - t_first_real) * pos / pos_last_real
      i.e. constant speed along the trip.  Trips with no synthetic stops keep
      their original rows untouched.
    """
    if shape_mode not in ("per-trip", "legacy-per-route"):
        raise ValueError(shape_mode)
    out_zip = out_zip or variant_zip(spacing, shape_mode)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    base = _load_base(base_zip)

    if spacing == 0:
        out_zip.write_bytes(Path(base_zip).read_bytes())
        stats = {
            "variant": variant_name(spacing, shape_mode),
            "spacing_m": 0,
            "shape_mode": shape_mode,
            "synthetic_stops": 0,
            "total_stops": len(base["stops"]),
            "total_stop_times": len(base["stop_times"]),
            "trips_with_synthetic": 0,
            "zip_bytes": out_zip.stat().st_size,
            "sha256": sha256(out_zip),
            "gen_seconds": round(time.perf_counter() - t0, 2),
        }
        _write_stats(out_zip, stats, verbose)
        return stats

    shape_dist = _shapes_with_distance(base["shapes"])
    stops_by_id = {
        s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"])) for s in base["stops"]
    }
    routes_by_id = {r["route_id"]: r for r in base["routes"]}

    # which shape each trip samples its synthetic stops from
    trip_shape = {}
    if shape_mode == "per-trip":
        for t in base["trips"]:
            if t.get("shape_id"):
                trip_shape[t["trip_id"]] = t["shape_id"]
        # one synthetic stop set per shape
        group_of_trip = dict(trip_shape)
    else:
        route_to_shape = {}
        for t in base["trips"]:
            if t["route_id"] not in route_to_shape and t.get("shape_id"):
                route_to_shape[t["route_id"]] = t["shape_id"]
        for t in base["trips"]:
            sid = route_to_shape.get(t["route_id"])
            if sid:
                trip_shape[t["trip_id"]] = sid
        # one synthetic stop set per route
        group_of_trip = {
            t["trip_id"]: t["route_id"]
            for t in base["trips"]
            if t["route_id"] in route_to_shape
        }

    trip_route = {t["trip_id"]: t["route_id"] for t in base["trips"]}

    # --- generate the synthetic stop sets ---
    syn_counter = SYN_ID_START
    # group key -> list of dicts with stop_id / lat / lon / dist
    group_stops: dict[str, list[dict]] = {}
    all_syn_stops: list[dict] = []
    for trip_id, group in group_of_trip.items():
        if group in group_stops:
            continue
        sid = trip_shape[trip_id]
        if sid not in shape_dist:
            continue
        swd, total = shape_dist[sid]
        if total <= 0:
            continue
        pts = generate_synthetic_stops(swd, spacing)
        route = routes_by_id.get(trip_route[trip_id], {})
        rows = []
        for lat, lon, dist in pts:
            stop_id = f"{SYN_PREFIX}{syn_counter}"
            syn_counter += 1
            row = {
                "stop_id": stop_id,
                "stop_name": f"Hail {route.get('route_short_name', 'unknown')}",
                "stop_lat": f"{lat:.6f}",
                "stop_lon": f"{lon:.6f}",
            }
            rows.append({**row, "dist": dist})
            all_syn_stops.append(row)
        group_stops[group] = rows

    # --- real-stop positions along each shape (cached) ---
    pos_cache: dict[tuple[str, str], float] = {}

    def real_pos(shape_id, stop_id):
        key = (shape_id, stop_id)
        if key not in pos_cache:
            lat, lon = stops_by_id[stop_id]
            pos_cache[key] = _nearest_dist_on_shape(lat, lon, shape_dist[shape_id][0])
        return pos_cache[key]

    orig_by_trip: dict[str, list] = {}
    for st in base["stop_times"]:
        orig_by_trip.setdefault(st["trip_id"], []).append(st)

    new_stop_times = []
    trips_with_syn = 0
    syn_stop_times = 0
    used_syn_ids = set()

    for trip_id, orig_list in orig_by_trip.items():
        orig_list = sorted(orig_list, key=lambda s: int(s["stop_sequence"]))
        shape_id = trip_shape.get(trip_id)
        group = group_of_trip.get(trip_id)
        if shape_id is None or group not in group_stops or shape_id not in shape_dist:
            new_stop_times.extend(orig_list)
            continue

        real = [
            (st, real_pos(shape_id, st["stop_id"]))
            for st in orig_list
            if st["stop_id"] in stops_by_id
        ]
        if len(real) < 2:
            new_stop_times.extend(orig_list)
            continue

        lo = min(p for _, p in real)
        hi = max(p for _, p in real)
        if hi <= lo:
            new_stop_times.extend(orig_list)
            continue

        # A synthetic stop only gets a stop_time on this trip if it lies
        # strictly between the trip's first and last real stop (same effective
        # filter as generate_hail_ride_stops.py's before/after pairing).
        syn = [
            (
                {
                    "trip_id": trip_id,
                    "stop_id": s["stop_id"],
                    "stop_sequence": "0",
                    "arrival_time": "",
                    "departure_time": "",
                    "timepoint": "0",
                },
                s["dist"],
            )
            for s in group_stops[group]
            if lo < s["dist"] < hi
        ]
        if not syn:
            new_stop_times.extend(orig_list)
            continue

        trips_with_syn += 1
        syn_stop_times += len(syn)
        for row, _ in syn:
            used_syn_ids.add(row["stop_id"])

        combined = sorted(real + syn, key=lambda x: x[1])
        first_real = min(real, key=lambda x: x[1])
        last_real = max(real, key=lambda x: x[1])
        t_first = time_to_seconds(first_real[0]["arrival_time"])
        t_last = time_to_seconds(last_real[0]["arrival_time"])
        span = last_real[1]

        for i, (st, pos) in enumerate(combined):
            st["stop_sequence"] = str(i + 1)
            ratio = pos / span if span > 0 else 0.0
            t = seconds_to_time(int(t_first + (t_last - t_first) * ratio))
            st["arrival_time"] = t
            st["departure_time"] = t
            new_stop_times.append(st)

    # Drop synthetic stops that no trip ended up using: an unreferenced stop
    # would still be street-linked by OTP and inflate the graph.
    kept_syn = [s for s in all_syn_stops if s["stop_id"] in used_syn_ids]
    all_stops = base["stops"] + kept_syn

    _write_variant_zip(base_zip, out_zip, all_stops, new_stop_times)

    stats = {
        "variant": variant_name(spacing, shape_mode),
        "spacing_m": spacing,
        "shape_mode": shape_mode,
        "synthetic_stops_generated": len(all_syn_stops),
        "synthetic_stops": len(kept_syn),
        "synthetic_stop_times": syn_stop_times,
        "total_stops": len(all_stops),
        "total_stop_times": len(new_stop_times),
        "trips_with_synthetic": trips_with_syn,
        "trips_total": len(orig_by_trip),
        "zip_bytes": out_zip.stat().st_size,
        "sha256": sha256(out_zip),
        "gen_seconds": round(time.perf_counter() - t0, 2),
    }
    _write_stats(out_zip, stats, verbose)
    return stats


def _write_variant_zip(base_zip: Path, out_zip: Path, stops, stop_times) -> None:
    """Copy every base entry through, replacing stops.txt and stop_times.txt."""
    replace = {"stops.txt", "stop_times.txt"}
    tmp = out_zip.with_suffix(".zip.tmp")
    with zipfile.ZipFile(base_zip, "r") as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            if item.filename not in replace:
                zout.writestr(item, zin.read(item.filename))
        zout.writestr("stops.txt", _csv_bytes(stops, STOPS_FIELDS))
        zout.writestr("stop_times.txt", _csv_bytes(stop_times, STOP_TIMES_FIELDS))
    os.replace(tmp, out_zip)


def _csv_bytes(rows, fieldnames) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _write_stats(out_zip: Path, stats: dict, verbose: bool) -> None:
    out_zip.with_suffix(".json").write_text(json.dumps(stats, indent=2) + "\n")
    if verbose:
        print(json.dumps(stats, indent=2))


# --- validation --------------------------------------------------------------
def validate_against_committed(stats: dict) -> None:
    """Compare a 200 m legacy-per-route variant against infra/otp/alex_gtfs.zip.

    Read-only sanity check that the reimplemented driver reproduces the feed the
    project has been running since 2026-05-30 (7,419 synthetic stops /
    15,508 stop_times).
    """
    committed = REPO_ROOT / "infra" / "otp" / "alex_gtfs.zip"
    if not committed.exists():
        print("validate: infra/otp/alex_gtfs.zip not found, skipping")
        return
    stops = read_csv_from_zip(str(committed), "stops.txt")
    sts = read_csv_from_zip(str(committed), "stop_times.txt")
    ref_syn = sum(1 for s in stops if s["stop_id"].startswith(SYN_PREFIX))
    print("\n--- validation vs committed infra/otp/alex_gtfs.zip ---")
    print(f"  synthetic stops:  ours={stats.get('synthetic_stops')}  committed={ref_syn}")
    print(f"  total stops:      ours={stats.get('total_stops')}  committed={len(stops)}")
    print(f"  total stop_times: ours={stats.get('total_stop_times')}  committed={len(sts)}")


# --- CLI ---------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract-base", help="copy the pre-synthetic feed out of git")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("build", help="build one or more variants")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--spacing", type=int, help="metres; 0 = fixed-stops control")
    g.add_argument("--all", action="store_true", help=f"build {ALL_SPACINGS} + fixed")
    p.add_argument(
        "--shape-mode",
        choices=["per-trip", "legacy-per-route"],
        default="per-trip",
    )
    p.add_argument("--validate", action="store_true", help="compare to committed feed")
    p.add_argument("--force", action="store_true", help="rebuild if zip exists")

    sub.add_parser("list", help="show which variants exist on disk")

    args = ap.parse_args(argv)

    if args.cmd == "extract-base":
        extract_base(force=args.force)
        return

    if args.cmd == "list":
        if not VARIANTS_DIR.exists():
            print("no variants built yet")
            return
        for z in sorted(VARIANTS_DIR.glob("*.zip")):
            meta = z.with_suffix(".json")
            info = json.loads(meta.read_text()) if meta.exists() else {}
            print(
                f"{z.name:24s} {z.stat().st_size/1e6:7.2f} MB  "
                f"stops={info.get('total_stops','?')} "
                f"stop_times={info.get('total_stop_times','?')} "
                f"mode={info.get('shape_mode','?')}"
            )
        return

    if not BASE_ZIP.exists():
        extract_base()

    spacings = [0] + ALL_SPACINGS if args.all else [args.spacing]
    for s in spacings:
        out = variant_zip(s, args.shape_mode)
        if out.exists() and not args.force:
            print(f"{out.name} exists, skipping (use --force)")
            continue
        print(f"\n=== building {variant_name(s, args.shape_mode)} (shape_mode={args.shape_mode}) ===")
        stats = build_variant(s, shape_mode=args.shape_mode)
        if args.validate:
            validate_against_committed(stats)


if __name__ == "__main__":
    main()
