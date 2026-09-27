# Knowledge Base

This is the learning journal for the Alexandria Public Transport project. Concepts are documented in the order they were encountered. Reading this top to bottom tells the full story.

---

## Architecture

Three backend services in Docker, one React Native mobile app:

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

> Map tiles come from `tile.openstreetmap.org` (free, no Docker service needed).

---

## Concepts

### 1. [Multimodal Trip Planning](concepts/multimodal-trip-planning.md)

The name for what this project is building: combining multiple transport modes (walk + bus + tram + microbus) into one journey. OpenTripPlanner (OTP) is the open-source engine that does the routing math.

---

### 2. [OpenTripPlanner](concepts/opentripplanner.md)

The routing engine. Takes a street map + transit schedules and answers "what's the best way from A to B?" Running in Docker at `http://localhost:8080`. Exposes a GraphQL API. Rebuilds its graph (~3 min) whenever input data or config changes.

---

### 3. [OpenStreetMap](concepts/openstreetmap.md)

A free, editable world map built by volunteers. OTP needs this to know where roads and footpaths are — without it, the app can't calculate walking legs. Our file: `infra/otp/egypt-latest.osm.pbf` (~168MB), downloaded from Geofabrik.

---

### 4. [GTFS](concepts/gtfs.md)

The industry standard format for transit schedules. A ZIP of CSVs that tells OTP: where the stops are, what routes exist, when vehicles depart/arrive, and which dates they run. Our data: 441 stops, 192 route patterns across Alexandria, from the DT4A 2022 initiative.

---

### 5. [Hail and Ride](concepts/hail-and-ride.md)

Alexandria transit doesn't follow fixed stops. Microbuses, buses, and minibuses pick up and drop off anywhere along the route. Standard GTFS doesn't model this well. OTP has partial support that's currently broken, so the workaround is generating synthetic stops every 100–200 meters.

---

### 6. [Architecture](concepts/architecture.md)

How the pieces connect. Two backend services (OTP, Photon) in `docker-compose.yml`, plus external map tiles from OSM. The React Native app is just a client — it sends HTTP requests and displays results. Each service maps to a Google Maps equivalent: OTP = Directions, Photon = Geocoding.

---

### 7. [Tile Server](concepts/tile-server.md)

Serves the visual map to the app. The world is pre-sliced into small 256×256 pixel squares (tiles) at multiple zoom levels. The phone requests just the ~20 tiles visible on screen, stitched together as the map you see. **Decision:** Using free external OSM tiles for now — same as OTP's debug client. Self-hosted tiles and offline caching are deferred.

---

## Other Docs

| File | Purpose |
|------|---------|
| [dataset.md](dataset.md) | Log of every change we make to the GTFS/OSM data |
| [vision.md](vision.md) | Broader app vision and roadmap |
