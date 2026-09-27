#!/usr/bin/env python3
"""
Build tools/gtfs/names.csv, the Arabic names for stops, places and vehicle types.

Run once to create the file; after that, names.csv is the source of truth and is
edited by hand. Kept in the repo so it's clear where every name came from.

Sources, in order of trust:
  dt4a   official Arabic from the DT4A survey data in data/alexandria/data/
         (processed stops, terminals, and the endpoints of identified routes)
  draft  researched names for stops DT4A left without Arabic, each with a
         confidence level and its evidence (OSM or a web source)

Usage:
    python3 tools/gtfs/build_names.py DRAFT.json [DRAFT.json ...]
Each DRAFT.json is a list of {"name_en", "name_ar", "confidence", "evidence", "note"}.
"""

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DT4A = REPO / "data" / "alexandria" / "data"
OUT = Path(__file__).resolve().parent / "names.csv"
FIELDS = ["kind", "name_en", "name_ar", "source", "confidence", "evidence", "note"]

# Defaults for vehicle types; a draft entry named VEHICLE_LABELS overrides them.
VEHICLES = {"Microbus": "ميكروباص", "Tomnaya": "تمناية", "Bus": "أتوبيس", "Minibus": "ميني باص"}


def features(path):
    return [f["properties"] for f in json.loads(path.read_text())["features"]]


def main(draft_paths):
    rows = {}  # (kind, name_en) -> row; first source wins

    def add(kind, en, ar, source, confidence="", evidence="", note=""):
        en, ar = (en or "").strip(), (ar or "").strip()
        if en and ar and (kind, en) not in rows:
            rows[(kind, en)] = dict(kind=kind, name_en=en, name_ar=ar, source=source,
                                    confidence=confidence, evidence=evidence, note=note)

    for p in features(DT4A / "processed_data" / "alex_processed_stops.geojson"):
        add("stop", p["name"], p.get("name_local"), "dt4a", "high", "alex_processed_stops.geojson")
    for p in features(DT4A / "processed_data" / "alex_terminals.geojson"):
        add("stop", p["name"], p.get("name_ar"), "dt4a", "high", "alex_terminals.geojson")
    for p in features(DT4A / "raw_data" / "alex_identified_routes.geojson"):
        add("place", p["origin_name"], p.get("origin_name_local"), "dt4a", "high", "alex_identified_routes.geojson")
        add("place", p["destination_name"], p.get("destination_name_local"), "dt4a", "high", "alex_identified_routes.geojson")

    vehicles = dict(VEHICLES)
    for path in draft_paths:
        for d in json.loads(Path(path).read_text()):
            if d["name_en"] == "VEHICLE_LABELS":
                for part in d["name_ar"].split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        vehicles[k.strip()] = v.strip()
                continue
            kind = "place" if d["name_en"] == "Green Plaza Mall" else "stop"
            add(kind, d["name_en"], d["name_ar"], "draft", d.get("confidence", ""), d.get("evidence", ""), d.get("note", ""))
    for en, ar in vehicles.items():
        add("vehicle", en, ar, "draft", "", "")

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for kind in ("vehicle", "place", "stop"):
            w.writerows(sorted((r for r in rows.values() if r["kind"] == kind), key=lambda r: r["name_en"]))
    print(f"wrote {OUT} with {len(rows)} names")


if __name__ == "__main__":
    main(sys.argv[1:])
