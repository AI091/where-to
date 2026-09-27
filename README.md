# Alexandria Public Transport

Trip planning for Alexandria, Egypt using OpenTripPlanner.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Compose plugin)

## First-time setup

```bash
# 1. Download Egypt OSM data (~168MB)
wget -O otp/egypt-latest.osm.pbf https://download.geofabrik.de/africa/egypt-latest.osm.pbf

# 2. Build the graph (~2min, writes otp/graph.obj)
docker compose run --rm otp --build --save

# 3. Start OTP
docker compose up -d
```

OTP is now running at **http://localhost:8080**.

## Usage

**GraphQL API** at `http://localhost:8080/otp/gtfs/v1`:

```bash
curl -X POST http://localhost:8080/otp/gtfs/v1 \
  -H "Content-Type: application/json" \
  -d '{"query":"{ plan(from:{lat:31.2,lon:29.9}, to:{lat:31.25,lon:29.95}, date:\"2023-01-15\", time:\"08:00:00\", transportModes:[{mode:BUS},{mode:WALK}]) { itineraries { duration legs { mode startTime endTime from { name } to { name } route { shortName } } } } }"}'
```

Replace `date` with any date in 2023 (the GTFS calendar range).

**GraphiQL IDE** at `http://localhost:8080/graphiql` — interactive query builder.

## Stop / Rebuild

```bash
docker compose down                         # stop
docker compose run --rm otp --build --save  # rebuild graph (after changing GTFS/OSM/config)
docker compose up -d --force-recreate otp   # restart OTP on the new graph
```
