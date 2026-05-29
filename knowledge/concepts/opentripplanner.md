# OpenTripPlanner (OTP)

**Context in the journey:** Discovered as the engine that powers multimodal trip planning.

**What it is:** An open-source routing engine. You feed it:
1. GTFS data (transit schedules and stops)
2. OSM data (street map)

It builds a "graph" and can answer "what's the best way from A to B?"

**How we use it:** Running in Docker at `http://localhost:8080`. Exposes a GraphQL API at `/otp/gtfs/v1` and a debug UI at `/`.

**Key concepts:**
- **Graph** — OTP pre-builds a network of streets + transit lines, stores it as `graph.obj`
- **GraphQL API** — The modern query interface (replaced the old REST API in 2025)
- **Modes** — OTP routes with WALK, BUS, TRAM, etc. We use `[BUS, WALK]` for Alexandria
- **build-config.json** — Config file telling OTP which dates to serve (ours: 2022–2099)

**Resources**
- [OTP docs](https://docs.opentripplanner.org/)
- [OTP GraphQL API](https://docs.opentripplanner.org/api/dev-2.x/graphql-gtfs/)
