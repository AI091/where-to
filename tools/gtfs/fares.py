#!/usr/bin/env python3
"""
Match our routes to the governorate's official fare list (fares_2026_03.tsv).

The list names each line by its two ends in local shorthand («المحطة /الحضرة»),
so both our route's Arabic ends and the list's ends are normalized before
comparing (المحطة = محطة مصر, الموقف = الموقف الجديد, hamza and ة/ه folded,
leading ال dropped). A route gets a fare only when both ends match; the rest get
nothing rather than a guess.

Usage:
    python3 tools/gtfs/fares.py FEED_WITH_TRANSLATIONS.zip OUT.json
Output: {"1:<route_id>": fare_in_egp, ...}
"""

import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

FARES = Path(__file__).resolve().parent / "fares_2026_03.tsv"
# Local shorthand in the list → our names.
SHORTHAND = {"المحطة": "محطة مصر", "الموقف": "الموقف الجديد", "عوايد": "العوايد", "المطار": "مطار النزهة", "النزهة": "مطار النزهة"}


def norm(name: str) -> str:
    name = SHORTHAND.get(name.strip(), name.strip())
    name = re.sub(r"\(.*?\)", "", name)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        name = name.replace(a, b)
    return re.sub(r"\s+", "", re.sub(r"^ال", "", name.strip()))


def main(feed: str, out: str):
    fares = {}
    rows = [l for l in FARES.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    for row in csv.DictReader(rows, delimiter="\t"):
        a, _, b = row["line"].partition("/")
        try:
            fares[frozenset({norm(a), norm(b)})] = float(row["fare_egp"])
        except ValueError:
            continue

    z = zipfile.ZipFile(feed)
    arabic = {
        r["record_id"]: r["translation"]
        for r in csv.DictReader(io.TextIOWrapper(z.open("translations.txt"), "utf-8"))
        if r["table_name"] == "routes" and r["field_name"] == "route_long_name"
    }
    matched = {}
    for route_id, name in arabic.items():
        key = frozenset(norm(p) for p in name.split(" - "))
        if key in fares:
            matched[f"1:{route_id}"] = fares[key]
    Path(out).write_text(json.dumps(dict(sorted(matched.items())), ensure_ascii=False, indent="\t") + "\n")
    print(f"{len(matched)} of {len(arabic)} routes have an official fare")


if __name__ == "__main__":
    main(*sys.argv[1:3])
