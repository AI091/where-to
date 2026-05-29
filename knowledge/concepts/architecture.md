# Architecture

**Context in the journey:** Figuring out all the pieces that need to run together.

**The big picture:**

```
┌─────────────────────────────────────────────┐
│              DOCKER (docker-compose)         │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │   OTP    │  │  Photon  │  │Tileserver │  │
│  │ :8080    │  │ :2322    │  │  (TBD)    │  │
│  │ routing  │  │ geocoding│  │ map tiles │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │              │        │
└───────┼──────────────┼──────────────┼────────┘
        │              │              │
   ┌────▼──────────────▼──────────────▼────┐
   │          REACT NATIVE APP              │
   │                                        │
   │  "Plan trip" ───────► OTP              │
   │  "Search address" ──► Photon           │
   │  "Show map" ────────► Tileserver       │
   └────────────────────────────────────────┘
```

**How each service maps to Google Maps:**

| Our service | Google Maps equivalent | Status |
|-------------|----------------------|--------|
| OTP | Directions API | Running |
| Photon | Geocoding API | Next |
| Tileserver | Map tile servers | Next |

The React Native app is just a client. All data crunching happens server-side.

**Resources**
- [Photon geocoder](https://photon.komoot.io/)
