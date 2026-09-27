# GTFS (General Transit Feed Specification)

**Context in the journey:** The format our Alexandria transit data came in.

**What it is:** The industry standard for transit schedules and stops. It's just a ZIP file containing CSVs (`stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `calendar.txt`, etc.).

**Why we need it:** This tells OTP:
- Where the stops are (lat/lon)
- What routes exist
- When vehicles depart and arrive
- Which stops each trip visits, in what order

**Key files:**
| File | What it contains |
|------|------------------|
| `stops.txt` | Stop name, ID, latitude, longitude |
| `routes.txt` | Route ID, short name, long name, mode |
| `trips.txt` | Links routes to specific journeys |
| `stop_times.txt` | Arrival/departure time at each stop |
| `calendar.txt` | Which dates each trip runs |

**Our file:** `infra/otp/alex_gtfs.zip` — 441 stops, 192 patterns, 104 routes across Alexandria. Source: DT4A 2022 initiative.

**Resources**
- [GTFS Reference](https://gtfs.org/)
