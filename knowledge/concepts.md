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

**Status:** Need to set up OTP with Docker.

---

## Resources

| Concept | Link |
|---------|------|
| OpenTripPlanner docs | https://docs.opentripplanner.org/ |
| GTFS reference | https://gtfs.org/ |
| OSM beginners' guide | https://wiki.openstreetmap.org/wiki/Beginners%27_guide |
