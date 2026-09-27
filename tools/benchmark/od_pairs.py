#!/usr/bin/env python3
"""
Generate the fixed, seeded OD (origin-destination) pair set for the benchmark.

Every variant must be queried with *identical* OD pairs, otherwise duration
differences between spacings are confounded by different trips.  So the pairs
are generated once, with a fixed RNG seed, and written to
`tools/benchmark/data/od_pairs.csv`.  All runs read that CSV; nothing re-randomises.

SAMPLING DESIGN
---------------
Alexandria's routes stretch from the city centre out to Borg el Arab, so the
feed's bounding box is roughly 49 km N-S by 55 km E-W while most stops sit in a
narrow coastal strip.  Uniform sampling over the bbox would put nearly every
pair in empty desert; sampling stops directly would clump pairs downtown where
stop density is highest (and would also bias the measurement, since an OD pair
that *is* a stop is the easy case for a discretized feed).

So:

  1. Overlay a `--grid` x `--grid` lat/lon grid on the union of the stops.txt and
     shapes.txt extent.
  2. Keep only *served* cells — cells containing at least one shape point.  This
     is what restricts sampling to the transit service area.
  3. Assign origins round-robin across served cells (after a seeded shuffle), so
     each served cell contributes an equal number of origins regardless of how
     many stops or shape points it contains.  This is the "not clustered
     downtown" property.
  4. Stratify *also* by trip length, round-robin over `--bands` (default
     1-3 / 3-8 / 8-20 / 20-70 km).  Without this, uniform destination cells over
     a 55 km-wide extent give a median separation of ~20 km, and since
     discretization error is an *absolute* quantity (order spacing/2 of extra
     walk at each end) it is diluted to invisibility on long trips.  Equal mass
     per band is what makes the deviation-vs-spacing curve readable.
  5. Place each endpoint by picking a random shape point inside the chosen cell
     and offsetting it by a random bearing and a random radius in
     [0, --jitter] metres.  Endpoints are therefore plausible trip ends near the
     network but almost never exactly on a stop.
  6. Reject pairs whose great-circle separation is below `--min-km` (default
     1.0 km), which would resolve to walk-only itineraries and measure nothing.

Candidate generation draws the destination cell from the origin's 3x3 grid
neighbourhood half the time and uniformly over served cells the other half,
purely so that short-band slots are fillable for remote cells.  Any (cell, band)
slot that still cannot be filled is reported in `od_pairs_meta.json` under
`unfilled_slots` and topped up from the leftover candidate pool, so the CSV
always has exactly `--n` rows.

KNOWN BIAS (state it in the write-up): anchoring endpoints to shape points means
this measures deviation for trips that *are* servable by the network, not
city-wide accessibility.  That is the intended scope — research-plan.md Phase 3
says "purely spatial ... algorithmic deviation, not user outcomes".

USAGE
-----
    python3 tools/benchmark/od_pairs.py                 # 800 pairs, seed 42
    python3 tools/benchmark/od_pairs.py --n 800 --seed 42 --grid 12 --out /tmp/od.csv
    python3 tools/benchmark/od_pairs.py --summary       # describe the existing CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter
from pathlib import Path

from variants import BASE_ZIP, DATA_DIR, extract_base, haversine, read_csv_from_zip

OD_CSV = DATA_DIR / "od_pairs.csv"
OD_META = DATA_DIR / "od_pairs_meta.json"

FIELDS = [
    "pair_id",
    "from_lat",
    "from_lon",
    "to_lat",
    "to_lon",
    "from_cell",
    "to_cell",
    "band",
    "straight_km",
]

DEFAULT_BANDS = "1-3,3-8,8-20,20-70"


def parse_bands(spec: str) -> list[tuple[float, float]]:
    out = []
    for part in spec.split(","):
        lo, hi = part.split("-")
        out.append((float(lo), float(hi)))
    return out


def band_of(km: float, bands) -> str | None:
    for lo, hi in bands:
        if lo <= km < hi:
            return f"{lo:g}-{hi:g}km"
    return None


def _extent(stops, shapes):
    lats = [float(s["stop_lat"]) for s in stops] + [
        float(s["shape_pt_lat"]) for s in shapes
    ]
    lons = [float(s["stop_lon"]) for s in stops] + [
        float(s["shape_pt_lon"]) for s in shapes
    ]
    return min(lats), max(lats), min(lons), max(lons)


def _offset(lat, lon, bearing_rad, dist_m):
    """Move (lat, lon) `dist_m` metres along `bearing_rad`. Flat-earth is fine
    at these distances (<1 km) and keeps this dependency-free."""
    dlat = (dist_m * math.cos(bearing_rad)) / 111_320.0
    dlon = (dist_m * math.sin(bearing_rad)) / (
        111_320.0 * max(math.cos(math.radians(lat)), 1e-6)
    )
    return lat + dlat, lon + dlon


def generate(
    n: int = 800,
    seed: int = 42,
    grid: int = 12,
    jitter_m: float = 400.0,
    min_km: float = 1.0,
    bands_spec: str = DEFAULT_BANDS,
    candidates_per_cell: int = 600,
    base_zip: Path = BASE_ZIP,
) -> tuple[list[dict], dict]:
    if not Path(base_zip).exists():
        extract_base()
    stops = read_csv_from_zip(str(base_zip), "stops.txt")
    shapes = read_csv_from_zip(str(base_zip), "shapes.txt")
    lat_min, lat_max, lon_min, lon_max = _extent(stops, shapes)
    lat_step = (lat_max - lat_min) / grid
    lon_step = (lon_max - lon_min) / grid

    def cell_of(lat, lon):
        r = min(int((lat - lat_min) / lat_step), grid - 1)
        c = min(int((lon - lon_min) / lon_step), grid - 1)
        return f"r{r}c{c}"

    # served cells: cells that contain at least one shape point
    cell_points: dict[str, list[tuple[float, float]]] = {}
    for s in shapes:
        lat, lon = float(s["shape_pt_lat"]), float(s["shape_pt_lon"])
        cell_points.setdefault(cell_of(lat, lon), []).append((lat, lon))

    rng = random.Random(seed)
    served = sorted(cell_points)
    rng.shuffle(served)
    if not served:
        raise SystemExit("no served cells — check the base feed")
    served_set = set(served)
    bands = parse_bands(bands_spec)
    band_names = [f"{lo:g}-{hi:g}km" for lo, hi in bands]

    def neighbours(cell):
        r, c = (int(x) for x in cell[1:].split("c"))
        out = [
            f"r{r+dr}c{c+dc}"
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if f"r{r+dr}c{c+dc}" in served_set
        ]
        return out or [cell]

    def draw_point(cell):
        lat, lon = rng.choice(cell_points[cell])
        return _offset(lat, lon, rng.uniform(0, 2 * math.pi), rng.uniform(0, jitter_m))

    # --- candidate pool, bucketed by (origin cell, band) ---
    pool: dict[tuple[str, str], list[dict]] = {}
    leftovers: dict[str, list[dict]] = {c: [] for c in served}
    for from_cell in served:
        nbrs = neighbours(from_cell)
        for k in range(candidates_per_cell):
            to_cell = rng.choice(nbrs) if k % 2 == 0 else rng.choice(served)
            flat, flon = draw_point(from_cell)
            tlat, tlon = draw_point(to_cell)
            km = haversine(flat, flon, tlat, tlon) / 1000.0
            if km < min_km:
                continue
            band = band_of(km, bands)
            cand = {
                "from_lat": round(flat, 6),
                "from_lon": round(flon, 6),
                "to_lat": round(tlat, 6),
                "to_lon": round(tlon, 6),
                "from_cell": from_cell,
                "to_cell": to_cell,
                "band": band or "other",
                "straight_km": round(km, 3),
            }
            if band:
                pool.setdefault((from_cell, band), []).append(cand)
            else:
                leftovers[from_cell].append(cand)

    # --- fill (cell, band) slots round-robin ---
    selected: list[dict] = []
    unfilled: list[str] = []
    slots = [(c, b) for c in served for b in band_names]
    slot_i = 0
    exhausted = 0
    while len(selected) < n and exhausted < len(slots):
        cell, band = slots[slot_i % len(slots)]
        slot_i += 1
        bucket = pool.get((cell, band))
        if bucket:
            selected.append(bucket.pop())
            exhausted = 0
        else:
            unfilled.append(f"{cell}/{band}")
            exhausted += 1

    # --- top up from anything left, keeping cells balanced ---
    if len(selected) < n:
        spare = [c for b in pool.values() for c in b] + [
            c for b in leftovers.values() for c in b
        ]
        rng.shuffle(spare)
        selected.extend(spare[: n - len(selected)])

    if len(selected) < n:
        raise SystemExit(
            f"only produced {len(selected)}/{n} pairs; raise --candidates-per-cell"
        )

    selected.sort(key=lambda p: (p["from_cell"], p["band"], p["straight_km"]))
    pairs = [{"pair_id": f"od{i:04d}", **p} for i, p in enumerate(selected)]

    dists = sorted(p["straight_km"] for p in pairs)
    meta = {
        "n": len(pairs),
        "seed": seed,
        "grid": grid,
        "jitter_m": jitter_m,
        "min_km": min_km,
        "bands": bands_spec,
        "candidates_per_cell": candidates_per_cell,
        "base_zip_sha_note": "see data/base/base_meta.json",
        "extent": {
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_min": lon_min,
            "lon_max": lon_max,
        },
        "cells_total": grid * grid,
        "cells_served": len(served),
        "straight_km": {
            "min": dists[0],
            "p25": dists[len(dists) // 4],
            "median": dists[len(dists) // 2],
            "p75": dists[3 * len(dists) // 4],
            "max": dists[-1],
            "mean": round(sum(dists) / len(dists), 3),
        },
        "pairs_per_band": dict(Counter(p["band"] for p in pairs)),
        "unfilled_slots": sorted(set(unfilled)),
        "origins_per_cell": dict(Counter(p["from_cell"] for p in pairs)),
    }
    return pairs, meta


def write(pairs, meta, out: Path = OD_CSV) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(pairs)
    OD_META.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {len(pairs)} pairs -> {out}")
    skip = {"origins_per_cell"}
    print(json.dumps({k: v for k, v in meta.items() if k not in skip}, indent=2))


def load(out: Path = OD_CSV, limit: int | None = None) -> list[dict]:
    """Read the frozen OD pairs.

    `limit` returns an *evenly spaced* subsample rather than the head. The CSV is
    sorted by (from_cell, band, straight_km), so the first N rows would all come
    from one grid cell and one distance band — useless as a smoke sample. Striding
    keeps the subsample deterministic and spread over cells and bands alike.
    """
    with open(out) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("from_lat", "from_lon", "to_lat", "to_lon", "straight_km"):
            r[k] = float(r[k])
    if not limit or limit >= len(rows):
        return rows
    step = len(rows) / limit
    return [rows[int(i * step)] for i in range(limit)]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Seeded, grid-stratified OD pairs")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--grid", type=int, default=12)
    ap.add_argument("--jitter", type=float, default=400.0, help="metres off the shape")
    ap.add_argument("--min-km", type=float, default=1.0)
    ap.add_argument("--bands", default=DEFAULT_BANDS, help="km bands, e.g. 1-3,3-8,8-20,20-70")
    ap.add_argument("--candidates-per-cell", type=int, default=600)
    ap.add_argument("--out", type=Path, default=OD_CSV)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--summary", action="store_true", help="describe existing CSV only")
    args = ap.parse_args(argv)

    if args.summary:
        rows = load(args.out)
        print(f"{len(rows)} pairs in {args.out}")
        print(OD_META.read_text() if OD_META.exists() else "(no meta)")
        return

    if args.out.exists() and not args.force:
        raise SystemExit(f"{args.out} exists — refusing to regenerate without --force")

    pairs, meta = generate(
        n=args.n,
        seed=args.seed,
        grid=args.grid,
        jitter_m=args.jitter,
        min_km=args.min_km,
        bands_spec=args.bands,
        candidates_per_cell=args.candidates_per_cell,
    )
    write(pairs, meta, args.out)


if __name__ == "__main__":
    main()
