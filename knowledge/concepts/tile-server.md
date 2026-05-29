# Tile Server

**Context in the journey:** The third backend service — what shows the visual map in the app.

**What it is:** Not a special technology. Just a web server that answers "give me the map chunk for this area at this zoom level." Returns small 256×256 pixel squares ("tiles") that the app stitches together into the map you see.

**Why tiles?** The full map of Egypt at street level is enormous (terabytes at full detail). You can't ship it to a phone or render it all at once. The world is pre-sliced into tiles at multiple zoom levels. The phone says "I'm looking at zoom 14, coordinates X/Y — give me just those ~20 tiles." You only pay for what's on screen.

Think of it like a book: you don't download 10,000 pages. You turn to page 47 when you need it.

**The pipeline:**

```
egypt-latest.osm.pbf    (raw data dump — not a map)
        │
        ▼  [One-time build: ~30 min]
 egypt.mbtiles           (pre-sliced map tiles in one file)
        │
        ▼  [Runtime: single Docker container]
 tileserver-gl           (serves tiles on demand)
        │
        ▼
 React Native app        (MapLibre renders them)
```

**Key format — MBTiles:** A single SQLite file containing all pre-computed tiles. The tile server opens it and serves the right chunks on request. One file = the entire map at all zoom levels. For Egypt: ~500MB–2GB.

**Our plan:** Use free external OSM tiles for now (`tile.openstreetmap.org`). Same approach OTP's own debug client uses. Self-hosted (PMTiles or MBTiles) can be added later as a dedicated docker-compose service.

**Offline note:** External tiles need internet, but this doesn't matter right now — OTP is server-side, so the app requires a connection either way. Self-hosted tiles don't improve offline capability unless you also embed OTP on-device (separate future decision).

**Status:** Next to evaluate and add to `docker-compose.yml`.

**Resources**
- [tileserver-gl](https://github.com/maptiler/tileserver-gl)
- [MapLibre (renders tiles in app)](https://maplibre.org/)
