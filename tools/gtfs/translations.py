#!/usr/bin/env python3
"""
Add Arabic names to a GTFS feed as translations.txt, from tools/gtfs/names.csv.

GTFS keeps one name per stop or route; translations.txt adds other languages
without touching the originals. OTP reads it and answers in Arabic when a request
sends `Accept-Language: ar`.

What gets translated:
  stops.stop_name         real stops: their name in names.csv
                          synthetic stops (SYN_): the Arabic name of the road the
                          route runs on there (from no_stop_roads.py --roads output),
                          otherwise "قرب <nearest real stop>"
  routes.route_long_name  "A - B" with each place translated via names.csv
  routes.route_short_name the vehicle type ("Microbus", "Bus 480", ...)

Usage:
    python3 tools/gtfs/translations.py FEED.zip OUT.zip [--roads NO_STOP_ROADS.json]
"""

import argparse
import csv
import io
import json
import math
import re
import zipfile
from pathlib import Path

NAMES = Path(__file__).resolve().parent / "names.csv"
FIELDS = ["table_name", "field_name", "language", "translation", "record_id", "record_sub_id", "field_value"]
ARABIC = re.compile(r"[؀-ۿ]")


def read_csv(z, name):
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig")))


def norm(s):
    """'El-Mandara' and 'El Mandara' are the same name."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_names():
    names = {}
    with NAMES.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            names[(r["kind"], r["name_en"])] = r["name_ar"]
    return names


def stop_name_ar(name_en, names, loose):
    """A stop's Arabic name; stops named after a place fall back to the place's name."""
    name_en = name_en.strip()
    return names.get(("stop", name_en)) or loose.get(norm(name_en))


def vehicle_label(short_name, names):
    """'Bus 480' -> 'أتوبيس 480', 'Microbus' -> 'ميكروباص'."""
    kind, _, number = short_name.strip().partition(" ")
    label = names.get(("vehicle", kind))
    if not label:
        return None
    return f"{label} {number}".strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add Arabic translations.txt to a GTFS feed.")
    ap.add_argument("feed")
    ap.add_argument("out")
    ap.add_argument("--roads", help="no_stop_roads.py output, for synthetic stop names")
    args = ap.parse_args(argv)

    names = load_names()
    roads = json.loads(Path(args.roads).read_text())["roads"] if args.roads else {}
    z = zipfile.ZipFile(args.feed)
    stops, routes = read_csv(z, "stops.txt"), read_csv(z, "routes.txt")

    # Loose index: stops first, then places, keyed by the name without spaces or hyphens.
    loose = {}
    for kind in ("place", "stop"):
        loose.update({norm(en): ar for (k, en), ar in names.items() if k == kind})
    real = [s for s in stops if not s["stop_id"].startswith("SYN_")]
    real_ar = {s["stop_id"]: stop_name_ar(s["stop_name"], names, loose) for s in real}

    def nearest_real_ar(lat, lon):
        best = min((s for s in real if real_ar[s["stop_id"]]),
                   key=lambda s: math.hypot(float(s["stop_lat"]) - lat, (float(s["stop_lon"]) - lon) * 0.86))
        return real_ar[best["stop_id"]]

    out, missing = [], {"stops": 0, "routes": 0}

    def tr(table, field, record_id, text):
        out.append(dict(table_name=table, field_name=field, language="ar", translation=text,
                        record_id=record_id, record_sub_id="", field_value=""))

    for s in stops:
        sid = s["stop_id"]
        if sid.startswith("SYN_"):
            # OSM joins some names with an English comma ("طريق خورشيد, العوايد").
            road = roads.get(sid, "").replace(", ", "، ").replace(",", "،")
            text = road if ARABIC.search(road) else f"قرب {nearest_real_ar(float(s['stop_lat']), float(s['stop_lon']))}"
        else:
            text = real_ar.get(sid)
        if text:
            tr("stops", "stop_name", sid, text)
        else:
            missing["stops"] += 1

    for r in routes:
        parts = [names.get(("place", p.strip())) for p in r["route_long_name"].split(" - ")]
        if all(parts):
            tr("routes", "route_long_name", r["route_id"], " - ".join(parts))
        else:
            missing["routes"] += 1
        label = vehicle_label(r["route_short_name"], names)
        if label:
            tr("routes", "route_short_name", r["route_id"], label)

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in z.infolist():
            if item.filename != "translations.txt":
                zout.writestr(item, z.read(item.filename))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
        zout.writestr("translations.txt", buf.getvalue().encode("utf-8"))
    print(f"wrote {args.out}: {len(out)} translations; untranslated stops {missing['stops']}, routes {missing['routes']}")


if __name__ == "__main__":
    main()
