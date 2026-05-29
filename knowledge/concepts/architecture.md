# Architecture

**Context in the journey:** Figuring out all the pieces that need to run together.

**The big picture:**

```
┌─────────────────────────────────────────────┐
│              DOCKER (docker-compose)         │
│                                              │
│  ┌──────────┐  ┌──────────┐                 │
│  │   OTP    │  │  Photon  │                 │
│  │ :8080    │  │ :2322    │                 │
│  │ routing  │  │ geocoding│                 │
│  └────┬─────┘  └────┬─────┘                 │
│       │              │                       │
└───────┼──────────────┼───────────────────────┘
        │              │
   ┌────▼──────────────▼──────────────────┐
   │         REACT NATIVE APP              │
   │                                        │
   │  "Plan trip" ────► OTP                 │
   │  "Search" ───────► Photon              │
   │  Map tiles ───────► OSM (external)     │
   └────────────────────────────────────────┘
```

> Map tiles come from `tile.openstreetmap.org` (free, no Docker service needed). Self-hosted tiles can be added later as a tileserver container.

**How each service maps to Google Maps:**

| Our service | Google Maps equivalent | Status |
|-------------|----------------------|--------|
| OTP | Directions API | Running |
| Photon | Geocoding API | Next |
| Tileserver | Map tile servers | Next |

The React Native app is just a client. All data crunching happens server-side.

**Resources**
- [Photon geocoder](https://photon.komoot.io/)
