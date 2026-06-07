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

## Planned Changes

- **Hail-and-ride support** — Most transit in Alexandria (microbuses, buses, minibuses) operates on a hail-and-ride basis: passengers can board/alight anywhere along the route, not just at fixed stops. The current GTFS has fixed stops. To support this, we'd need to generate synthetic stops every X meters along route shapes.
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
