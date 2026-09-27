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

## Planned Changes

- **Drop synthetic stops a pedestrian can't reach (decided 2026-09-27)** — With synthetic stops every 250 m, OTP 2.10.0 flagged 1,193 of 10,436 as `IsolatedStop` ("only 0s of walking possible"), almost all on two highway corridors crossing Lake Mariout where walking is banned in OSM. Vehicles don't stop there either, so these stops add search work and help nobody. Plan: remove the stops listed in OTP's `IsolatedStop` report, then rebuild. See [hail-and-ride](concepts/hail-and-ride.md).
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
