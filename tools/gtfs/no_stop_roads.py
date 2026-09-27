#!/usr/bin/env python3
"""
Find synthetic stops that sit on roads where vehicles don't stop.

Alexandria's buses and microbuses are hail-and-ride, but not on every stretch of
road: they don't stop on highways, flyovers, tunnels or ramps (confirmed from local
knowledge on 2026-09-27, see knowledge/dataset.md). OSM closes those roads to
pedestrians, so the rule is:

  1. For each synthetic stop, find the road its own route runs on: the nearest
     drivable OSM way within 30 m that runs parallel to the route shape. The
     parallel check keeps a flyover from matching the street it crosses.
  2. If that road forbids walking, vehicles don't stop there: drop the stop.
  3. If no drivable road runs alongside (shape and OSM disagree), keep the stop if
     any walkable way is within 30 m, otherwise drop it.

This is the same rule the hail-and-ride OTP fork applies, written against OSM tags
instead of OTP's street graph.

Usage:
    uv run --project tools/gtfs python tools/gtfs/no_stop_roads.py FEED.zip OSM.pbf -o drop.json

Output JSON:
    {"rule": ..., "stops": {"SYN_...": [lat, lon], ...}, "reasons": {"SYN_...": "road name", ...},
     "by_road": {"road name": n, ...}}
The "stops" map is what tools/benchmark/variants.py --drop-stops reads.
"""

import argparse
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict

import osmium

SYN_PREFIX = "SYN_"
SEARCH_M = 30.0
PARALLEL_DEG = 30.0
CELL_M = 50.0
BBOX_MARGIN_DEG = 0.01  # ~1 km around the feed

DRIVABLE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road",
}


def walk_allowed(tags) -> bool:
    """Whether OSM lets pedestrians use this way (explicit foot tags win)."""
    foot = tags.get("foot")
    if foot in ("yes", "designated", "permissive"):
        return True
    if foot in ("no", "private", "use_sidepath"):
        return False
    if tags.get("motorroad") == "yes":
        return False
    if tags.get("highway") in ("motorway", "motorway_link"):
        return False
    return tags.get("access") not in ("no", "private")


def road_label(tags) -> str:
    return tags.get("name:ar") or tags.get("name") or tags.get("ref") or tags.get("highway")


def read_csv(z, name):
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig")))


class Projection:
    """Local equirectangular metres around the feed; plenty for 30 m lookups."""

    def __init__(self, lat0):
        self.kx = math.cos(math.radians(lat0)) * 111_195.0
        self.ky = 111_195.0

    def __call__(self, lat, lon):
        return lon * self.kx, lat * self.ky


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(ax + t * vx - px, ay + t * vy - py)


def undirected_angle(ax, ay, bx, by, cx, cy, dx, dy) -> float:
    a = math.degrees(math.atan2(by - ay, bx - ax))
    b = math.degrees(math.atan2(dy - cy, dx - cx))
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def synthetic_stops_with_bearing(z, proj):
    """SYN stop -> (lat, lon, x, y, route shape segment it lies on)."""
    stops = {s["stop_id"]: s for s in read_csv(z, "stops.txt") if s["stop_id"].startswith(SYN_PREFIX)}
    shape_of_trip = {t["trip_id"]: t["shape_id"] for t in read_csv(z, "trips.txt")}
    shape_of_stop = {}
    for st in read_csv(z, "stop_times.txt"):
        if st["stop_id"] in stops and st["stop_id"] not in shape_of_stop:
            shape_of_stop[st["stop_id"]] = shape_of_trip[st["trip_id"]]
    shapes = defaultdict(list)
    for r in read_csv(z, "shapes.txt"):
        shapes[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lat"]), float(r["shape_pt_lon"])))
    shape_xy = {sid: [proj(la, lo) for _, la, lo in sorted(pts)] for sid, pts in shapes.items()}

    out = {}
    for sid, s in stops.items():
        if sid not in shape_of_stop:
            continue  # unused synthetic stop; the generators already drop these
        lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
        x, y = proj(lat, lon)
        pts = shape_xy[shape_of_stop[sid]]
        i = min(range(len(pts) - 1), key=lambda k: seg_dist(x, y, *pts[k], *pts[k + 1]))
        out[sid] = (lat, lon, x, y, pts[i], pts[i + 1])
    return out


def load_roads(pbf, proj, bbox):
    """Drivable and walkable OSM way segments inside bbox, bucketed on a grid."""
    min_lat, min_lon, max_lat, max_lon = bbox
    ways = []  # (drivable, walkable, label)
    segs = []  # (ax, ay, bx, by, way_index)
    grid = defaultdict(list)
    fp = osmium.FileProcessor(pbf).with_locations().with_filter(osmium.filter.KeyFilter("highway"))
    for w in fp:
        if not w.is_way():
            continue
        locs = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
        if len(locs) < 2 or not any(min_lat <= la <= max_lat and min_lon <= lo <= max_lon for la, lo in locs):
            continue
        tags = {t.k: t.v for t in w.tags}
        drivable = tags.get("highway") in DRIVABLE
        walkable = walk_allowed(tags)
        if not drivable and not walkable:
            continue
        wi = len(ways)
        ways.append((drivable, walkable, road_label(tags)))
        xy = [proj(la, lo) for la, lo in locs]
        for (ax, ay), (bx, by) in zip(xy, xy[1:]):
            si = len(segs)
            segs.append((ax, ay, bx, by, wi))
            for cx in range(int(min(ax, bx) // CELL_M), int(max(ax, bx) // CELL_M) + 1):
                for cy in range(int(min(ay, by) // CELL_M), int(max(ay, by) // CELL_M) + 1):
                    grid[(cx, cy)].append(si)
    return ways, segs, grid


def classify(stop, ways, segs, grid):
    """(drop?, reason) for one synthetic stop."""
    _, _, x, y, (rax, ray), (rbx, rby) = stop
    cx, cy = int(x // CELL_M), int(y // CELL_M)
    candidates = {si for dx in (-1, 0, 1) for dy in (-1, 0, 1) for si in grid.get((cx + dx, cy + dy), ())}
    best_road, best_walk = None, None
    for si in candidates:
        ax, ay, bx, by, wi = segs[si]
        d = seg_dist(x, y, ax, ay, bx, by)
        if d > SEARCH_M:
            continue
        drivable, walkable, _ = ways[wi]
        if drivable and undirected_angle(rax, ray, rbx, rby, ax, ay, bx, by) <= PARALLEL_DEG:
            if best_road is None or d < best_road[0]:
                best_road = (d, wi)
        if walkable and (best_walk is None or d < best_walk[0]):
            best_walk = (d, wi)
    if best_road:
        _, walkable, label = ways[best_road[1]]
        return (not walkable), label
    if best_walk:
        return False, "no parallel drivable road, walkable street nearby"
    return True, "no street within 30 m"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find synthetic stops on roads where vehicles don't stop.")
    ap.add_argument("feed", help="GTFS zip with synthetic (SYN_) stops")
    ap.add_argument("osm", help="OSM .pbf covering the feed")
    ap.add_argument("-o", "--out", required=True, help="output JSON")
    args = ap.parse_args(argv)

    z = zipfile.ZipFile(args.feed)
    all_stops = read_csv(z, "stops.txt")
    lats = [float(s["stop_lat"]) for s in all_stops]
    lons = [float(s["stop_lon"]) for s in all_stops]
    proj = Projection(sum(lats) / len(lats))
    bbox = (min(lats) - BBOX_MARGIN_DEG, min(lons) - BBOX_MARGIN_DEG,
            max(lats) + BBOX_MARGIN_DEG, max(lons) + BBOX_MARGIN_DEG)

    stops = synthetic_stops_with_bearing(z, proj)
    ways, segs, grid = load_roads(args.osm, proj, bbox)

    drop, reasons, by_road = {}, {}, Counter()
    for sid, stop in stops.items():
        dropped, reason = classify(stop, ways, segs, grid)
        if dropped:
            drop[sid] = [stop[0], stop[1]]
            reasons[sid] = reason
            by_road[reason] += 1

    result = {
        "rule": "drop synthetic stops whose route's parallel drivable road (<= 30 m) forbids walking, "
                "or with no street within 30 m",
        "feed": args.feed,
        "synthetic_stops_checked": len(stops),
        "stops": drop,
        "reasons": reasons,
        "by_road": dict(by_road.most_common()),
    }
    with open(args.out, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"{len(drop)} of {len(stops)} synthetic stops are on roads where vehicles don't stop")
    for road, n in by_road.most_common(12):
        print(f"  {n:5d}  {road}")


if __name__ == "__main__":
    main()
