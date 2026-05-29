# Knowledge Base

> This is a living document. The user decides what goes in here.

---

## Starting Point: The Goal

I want to build an app that tells people how to get from point A to point B in Alexandria using different kinds of transport — bus, tram, walking, maybe more. I don't know the domain terms yet; I'm learning as I go.

---

## Encounter 1: Multimodal Trip Planning

**What I learned:** There's a name for what I'm trying to build — **multimodal trip planning**. It means combining multiple transport modes (walk + bus + tram) into one journey, not just looking up a single bus route.

**Tool discovered:** [OpenTripPlanner (OTP)](https://docs.opentripplanner.org/) — an open-source engine that does exactly this. It takes a street map + transit schedules and finds optimal routes.

---

## Encounter 2: What OTP Needs to Run

I explored the `otp/` folder I had (now deleted). OTP needs **two** inputs to build its routing graph:

1. **GTFS data** — the transit schedules and stops. I already have this in `alexandria/data/alex_gtfs.zip`.
2. **A street map** — so OTP knows how people walk to/from stops. This comes from **OpenStreetMap (OSM)**.

**What is OSM?** A free, editable map of the world built by volunteers. Think Wikipedia, but for maps. OTP consumes OSM data in a binary format called `.pbf`.

**What is GTFS?** The industry standard format for transit schedules. It's just a ZIP file full of CSVs (`stops.txt`, `routes.txt`, `trips.txt`, etc.).

---

**Status:** OTP is now running with Docker at `http://localhost:8080`.

---

## Encounter 3: Hail-and-Ride

**What I learned:** Not all transit follows fixed stops. In Alexandria, many transit modes — microbuses, buses, and minibuses — are effectively **hail-and-ride**: passengers can flag them down anywhere safe along the route, and drop-offs happen anywhere on request. This is common for informal/paratransit in many cities.

**Why it matters:** Standard GTFS with fixed stops doesn't model this well. To simulate hail-and-ride in a trip planner, you typically generate synthetic stops at regular intervals (e.g., every 100–200m) along each route's path. That way OTP knows passengers can board/alight at any of those points.

**GTFS support:** GTFS has `continuous_pickup` and `continuous_drop_off` fields (introduced in 2019) that can mark a route as allowing boarding/alighting between stops. OTP has partial support via its GTFS Flex module, but the routing logic doesn't yet produce hail-and-ride results reliably.

**Status in OTP:** A [Feb 2026 issue](https://github.com/opentripplanner/OpenTripPlanner/issues/7304) confirms that configuring OTP for continuous pickup/dropoff is broken — routes marked as hail-and-ride still only stop at fixed stops. For now, generating synthetic stops at regular intervals is the workaround.

**Resources**
- [GTFS continuous stop extension](https://gtfs.org/schedule/reference/#stop_timestxt)
- [OTP issue: continuous pickup/dropoff doesn't work](https://github.com/opentripplanner/OpenTripPlanner/issues/7304)

---

## Resources

| Concept | Link |
|---------|------|
| OpenTripPlanner docs | https://docs.opentripplanner.org/ |
| GTFS reference | https://gtfs.org/ |
| OSM beginners' guide | https://wiki.openstreetmap.org/wiki/Beginners%27_guide |
