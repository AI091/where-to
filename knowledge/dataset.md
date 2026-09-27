# Dataset: Alexandria Public Transport

## Source
- **Project:** DT4A Capacity Building & Mapping Initiative
- **Partners:** DigitalTransport4Africa, Transport for Cairo, AfD
- **Collection:** 80 students, Arab Academy for Science & Technology
- **Period:** Nov 14 – Dec 15, 2022
- **Coverage:** 104 transit routes across Alexandria
- **License:** CC BY-NC 4.0

## Types of transport in the data
- **Microbus** (14-seater, orange plates) — informal/flexible routing
- **Tomnaya** (8-seater, blue plates) — smaller paratransit
- **Cooperative** (29-seater, grey plates)
- **APTA** (public bus)
- **LTRA** (minibus)

## Changes Log

| Date | Change | Reason |
|------|--------|--------|
| 2026-05-29 | Extended `calendar.txt` end date `20231230` → `20991231` | Dataset was locked to 2023. Extended so OTP routes for any date. |
| 2026-05-30 | Generated 7,419 synthetic hail-and-ride stops along 104 route shapes (every ~200m) | Alexandria transit is hail-and-ride; passengers board/alight anywhere. GTFS only had fixed stops. |
| 2026-05-30 | Merged synthetic stops into `alex_gtfs.zip`; re-sequenced 15,508 stop_times with position-based time interpolation | Initial merge sorted by shape position but kept original times, causing non-monotonic times. OTP rejected all transit patterns. Fixed by regenerating times proportional to distance along trip. Transit patterns restored (192) and routing is ~11 min faster. |
| 2026-09-27 | Regenerated synthetic stops **per shape** instead of per route: 13,616 synthetic stops (was 7,419), 15,607 stop_times (was 15,508). Rebuilt from the pre-synthetic feed at commit `b1479e6`. | `generate_hail_ride_stops.py` used the first trip's shape for the whole route, but 88 of 104 routes have two shapes (one per direction). The other direction's trips got stops sampled along the wrong streets: ~20% of synthetic stop_times sat >50 m off their trip's own alignment, worst 6.6 km. Now every synthetic stop lies on its own trip's shape (max offset 0 m). |
| 2026-09-28 | **Published feed for the anzelfein.com route pages** (a derived copy; the OTP-served `infra/otp/alex_gtfs.zip` is unchanged): synthetic stops every 250 m per shape, minus 3,167 on roads where vehicles don't stop (`tools/gtfs/no_stop_roads.py`), giving 7,710 stops; plus `translations.txt` with 7,918 Arabic names from `tools/gtfs/names.csv`. Nine low-confidence landmark names were replaced with the OSM-verified street and area (e.g. «ترعة البرلس» → «ترعة البرنس», «مسجد الرحمن» → «شارع عمر لطفي - الشاطبي»); the old names are in each row's `note`. English commas in OSM road names became «،». | The route pages are public and Arabic, so they need the road rule (no boarding on highways, flyovers or tunnels) and names people can trust. Built with `tools/gtfs/translations.py` on `tools/benchmark/data/variants/spacing_250m_walkable.zip`. |

## Planned Changes

- **Drop synthetic stops on roads where vehicles don't stop (decided 2026-09-27)** — Confirmed from local knowledge: microbuses and buses don't stop on highways (Cairo–Alexandria Desert Road, International Coastal Road, Suez Canal Road, Ring Road, Agricultural Road), flyovers, tunnels or ramps. Rule: a synthetic stop is dropped if the road its own route runs on (the nearest parallel drivable OSM road within 30 m) forbids walking. At 250 m spacing this drops 3,167 of 10,436 synthetic stops (the hail-and-ride fork's version of the same rule: 3,089; 99% agreement). Applied to the route-pages feed on 2026-09-28 (see the log); not yet to the served feed. The first plan used OTP's `IsolatedStop` report (1,193 stops), but that misses 1,909 stops that OTP linked to a nearby frontage road or the street under a flyover. See [hail-and-ride](concepts/hail-and-ride.md).
- **Arabic names via `translations.txt` (drafted 2026-09-27)** — The feed is English-only. `tools/gtfs/names.csv` holds 323 Arabic names: 139 official from the DT4A survey files (stops, terminals, route endpoints) and the rest researched (OSM + web search), each marked `dt4a` or `draft` with a confidence level and evidence. Four official spellings were normalized to standard Arabic (العصافره → العصافرة, سموحه → سموحة, الرابعه → الرابعة, الملاحه → الملاحة), and microbus terminals use «موقف»; the originals are in each row's `note`. `tools/gtfs/translations.py` turns it into `translations.txt`; synthetic stops get the name of the road they sit on (from OSM), otherwise «قرب <nearest real stop>». So far only applied to a benchmark copy of the 250 m + road-rule feed for the draft route pages; the served feed is unchanged.
- **Tram/Train status** — Some tram/train lines are currently out of service. May need to remove or flag these routes.
- **New routes/lines** — Any new transit lines not in the 2022 data.

## Known Issues / Data Gaps

| Issue | Status | Notes |
|-------|--------|-------|
| **OTP itinerary ordering** | Temporary fix applied | OTP sorts by "generalized cost" (walk penalty + wait time + transfers), not raw duration. This caused a 48 min walk-only itinerary to rank above a 28 min transit trip. We now sort by `duration` in the Go server, but this may hide better trade-offs (e.g., less walking). **Needs investigation:** tune OTP cost parameters or expose generalized cost in the API so the client can decide. |
| **Missing Maamorow – Tabya lanes** | Unresolved | Buses and microbuses serving the Maamorow ↔ Tabya corridor are absent from the dataset. This is a major transit axis in Alexandria. Likely missing from the 2022 student survey. **Needs:** source GTFS or trace data for these routes. |

## How the dataset is used
- GTFS file (`alex_gtfs.zip`) is consumed by OpenTripPlanner
- OSM street data (`egypt-latest.osm.pbf`) provides the walking network
- All served via OTP Docker container at `http://localhost:8080`
