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

## Planned Changes

- **Hail-and-ride support** — Most transit in Alexandria (microbuses, buses, minibuses) operates on a hail-and-ride basis: passengers can board/alight anywhere along the route, not just at fixed stops. The current GTFS has fixed stops. To support this, we'd need to generate synthetic stops every X meters along route shapes.
- **Tram/Train status** — Some tram/train lines are currently out of service. May need to remove or flag these routes.
- **New routes/lines** — Any new transit lines not in the 2022 data.

## How the dataset is used
- GTFS file (`alex_gtfs.zip`) is consumed by OpenTripPlanner
- OSM street data (`egypt-latest.osm.pbf`) provides the walking network
- All served via OTP Docker container at `http://localhost:8080`
