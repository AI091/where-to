# Phase 3 benchmark harness — synthetic-stop discretization cost

Measures what discretization costs on the Alexandria feed: generate the same GTFS
feed at several synthetic-stop spacings, route the *same* OD pairs through each,
and compare against a dense baseline that stands in for true continuous
boarding. Spec: [`knowledge/research-plan.md`](../knowledge/research-plan.md)
Phase 3. Why discretization is the only option in OTP today:
[`knowledge/research/phase1-verdict.md`](../knowledge/research/phase1-verdict.md).

Nothing here modifies source data. `otp/alex_gtfs.zip`, `otp/egypt-latest.osm.pbf`,
`scripts/`, `docker-compose.yml` and the service on `:8080` are all read-only from
this directory's point of view, so AGENTS.md rule 13 (log dataset changes) is not
triggered — every feed produced here is a derived variant under `data/`.

## Layout

| File | What it does |
|---|---|
| `variants.py` | Builds GTFS variants at any spacing from the pre-synthetic-stops feed |
| `od_pairs.py` | Generates the frozen, seeded, grid+distance-stratified OD pair set |
| `run_otp.py` | Builds and serves one variant in an isolated OTP container on `:8081` |
| `query.py` | Runs the OD pairs against a served variant, saves raw + tabulated results |
| `metrics.py` | Deviation metrics — **stubs only**, see [TODO](#todo) |
| `data/` | All generated output (gitignored via `benchmark/.gitignore`) |

Stdlib only — no `pip install`, no venv needed. Tested on Python 3.14.

```
data/
  base/alex_gtfs_base.zip        the fixed-stops seed feed + base_meta.json
  variants/<variant>.zip         one derived feed per spacing + <variant>.json stats
  od_pairs.csv                   800 frozen OD pairs + od_pairs_meta.json
  otp/<variant>/                 isolated OTP input dir: gtfs zip, hardlinked pbf,
                                 build-config.json, graph.obj, build.log, run_meta.json
  results/<variant>/             raw/<pair_id>.json, queries.csv, itineraries.csv,
                                 query_meta.json
```

## Where the original (pre-synthetic-stops) feed was found

`otp/alex_gtfs.zip` is *already* discretized — 7,419 synthetic stops at ~200 m,
merged in on 2026-05-30 — so it cannot seed the variants. Two intact copies of
the fixed-stops feed exist:

1. **`alexandria/data/alex_gtfs.zip`** — the untouched DT4A download. 441 stops,
   2,547 stop_times, 0 synthetic stops, `calendar.txt` ending `20231230`.
2. **`git show b1479e6:otp/alex_gtfs.zip`** — same GTFS content with
   `calendar.txt` extended to `20991231` (dataset.md change #1). `b1479e6` is the
   last commit before `d1c5e5a` "Merge synthetic stops into alex_gtfs.zip".

**The harness seeds from (2).** The calendar extension is a standing project
decision rather than a benchmark variable, and without it OTP has no service on
any date we query. No reconstruction from a "non-synthetic subset" was needed.
`variants.py extract-base` copies that blob to `data/base/alex_gtfs_base.zip` and
asserts it contains zero `SYN_*` stops.

## Quick start

```bash
cd /home/ahmed/where-to

python3 benchmark/variants.py extract-base          # data/base/alex_gtfs_base.zip
python3 benchmark/od_pairs.py                       # data/od_pairs.csv (seed 42, n=800)

python3 benchmark/variants.py build --spacing 500   # data/variants/spacing_500m.zip
python3 benchmark/run_otp.py up --variant spacing_500m   # build graph + serve on :8081
python3 benchmark/query.py --variant spacing_500m --limit 20
python3 benchmark/run_otp.py stop --variant spacing_500m
```

`run_otp.py status` shows which benchmark containers exist, which variants have a
graph, and confirms the project's own ports are untouched.

## Running the full matrix

The graph build is the long pole (~4 min each, single-threaded phases dominate)
and only one variant can serve on `:8081` at a time, so the matrix is sequential.
Build every feed first — that part is seconds — then loop.

```bash
cd /home/ahmed/where-to

# 1. seed feed + frozen OD pairs (once)
python3 benchmark/variants.py extract-base
python3 benchmark/od_pairs.py --n 800 --seed 42

# 2. all seven feeds: fixed control, four study spacings, two dense baselines
python3 benchmark/variants.py build --all
python3 benchmark/variants.py list

# 3. build a graph, serve it, query all 800 pairs, tear it down — per variant
for v in fixed spacing_1000m spacing_500m spacing_250m spacing_100m spacing_25m spacing_10m; do
  python3 benchmark/run_otp.py up --variant "$v" --xmx 6G  || { echo "FAILED $v"; continue; }
  python3 benchmark/query.py    --variant "$v"
  python3 benchmark/run_otp.py stop --variant "$v"
done
python3 benchmark/run_otp.py stop-all

# 4. metrics (NOT IMPLEMENTED YET — see TODO)
python3 benchmark/metrics.py list
python3 benchmark/metrics.py report --baseline spacing_10m
```

Keep `--xmx` identical across variants or the RSS numbers are not comparable.
`variants.py build --all` skips feeds that already exist; pass `--force` to redo.

All seven feeds generate in **5.6 s total** (verified 2026-07-30):

| variant | synthetic stops | stop_times | zip |
|---|---|---|---|
| `fixed` | 0 | 2,547 | 0.32 MB |
| `spacing_1000m` | 2,567 | 5,114 | 0.37 MB |
| `spacing_500m` | 5,197 | 7,744 | 0.42 MB |
| `spacing_250m` | 10,436 | 12,983 | 0.53 MB |
| `spacing_100m` | 26,148 | 28,695 | 0.84 MB |
| `spacing_25m` | 104,658 | 107,205 | 2.35 MB |
| `spacing_10m` | **261,680** | 264,227 | 5.08 MB |

The 10 m feed is the risk in the matrix: 262k stops all need street-linking during
graph build, and it has not been built yet. Budget generously — the 500 m build
took 190 s and 5.5 GB of a 6 GB heap for 5,638 stops. If it OOMs, raise `--xmx`
(the host has 30 GB) and re-run that variant alone; if it still fails, that is
itself a reportable result for the community post, since it bounds how fine a
discretization OTP can ingest at all.

Disk: each variant's OTP dir holds a ~543 MB `graph.obj`, so the full matrix needs
roughly **4 GB** plus the hardlinked pbf (shared, not duplicated).

## Isolation from the running project

`run_otp.py` never calls `docker compose`. It only uses `docker run/stop/rm`, and:

- every container it creates is named `otp-bench-*`; it refuses to stop or remove
  anything without that prefix (`_assert_ours`);
- it publishes `127.0.0.1:8081` only, and refuses ports 8080 (project OTP) and
  8090 (project Go server) outright;
- it aborts if 8081 is occupied by anything that is not its own container;
- it bind-mounts `benchmark/data/otp/<variant>/`, never `otp/`. The 176 MB OSM
  extract is **hardlinked** into each variant dir (falling back to a copy), so it
  is not duplicated seven times and `otp/egypt-latest.osm.pbf` is never written.
  The GTFS zip is a real copy, so OTP cannot write back into `data/variants/`.

## Design decisions

**Per-trip shapes, not per-route (deviation from `scripts/`).**
`generate_hail_ride_stops.py` derives `route_to_shape` from each route's *first*
trip and generates one synthetic stop set per route. This feed has 192 trips and
192 distinct `shape_id`s — 88 of 104 routes carry two shapes, one per
`direction_id`. Under the legacy rule the direction-1 trip of those 88 routes gets
stops sampled along the direction-0 alignment. That is a latent data bug in the
feed currently shipped in `otp/alex_gtfs.zip`, and fatal for a benchmark whose
subject *is* spatial discretization error. Default is therefore
`--shape-mode per-trip`; `--shape-mode legacy-per-route` reproduces the old
behaviour for validation and writes to `spacing_<n>m_legacy.zip`.

**Reuse of the existing preprocessing.** `variants.py` imports the geometry and
time primitives (`haversine`, `build_shape_with_distances`,
`generate_synthetic_stops`, `time_to_seconds`, `seconds_to_time`,
`read_csv_from_zip`) directly from `scripts/`. Only the driver is new, because the
originals hardcode `INTERVAL = 200` and absolute paths, round-trip through
intermediate CSVs, and re-derive each synthetic stop's along-shape position with
an O(stops x shape_points) nearest-point scan — about 10^9 haversine calls at
10 m spacing. The driver carries the exact distance from generation through to
merging instead. The **merge rule is unchanged**: combine real + synthetic
stop_times, sort by along-shape distance, re-sequence, and regenerate all times
as a constant-speed interpolation between the trip's first and last real stop.

**Validated against the committed feed.** `variants.py build --spacing 200
--shape-mode legacy-per-route --validate` reproduces the 2026-05-30 pipeline:

| | this harness | committed `otp/alex_gtfs.zip` |
|---|---|---|
| synthetic stops generated | 7,419 | 7,419 |
| synthetic stops kept | 7,269 | 7,419 |
| total stop_times | **15,508** | **15,508** |

`stop_times` matches exactly, so the merge is faithful. The 150-stop difference is
deliberate: the harness drops synthetic stops that no trip ended up referencing,
since OTP would still street-link an orphan stop and inflate the graph.

**A `fixed` control variant (`--spacing 0`).** Not in the spec, but it is the only
way to separate "cost of discretization" from "cost of transit routing at all",
and it is free.

**OD pair stratification is two-dimensional.** Grid cells alone gave a median
straight-line separation of 20 km, because the feed's extent runs out to Borg el
Arab. Discretization error is an *absolute* quantity (order spacing/2 of extra
walk per end), so it vanishes into the noise on 20 km trips. Pairs are therefore
stratified over served grid cells **and** over distance bands
(1-3 / 3-8 / 8-20 / 20-70 km, 200 pairs each). Endpoints are anchored to a random
shape point in the chosen cell, then offset by a random bearing and 0-400 m — so
they are plausible trip ends near the network but almost never exactly on a stop.

**Two-phase container run.** `--build --save` in a throwaway `--rm` container
gives a clean build wall time and `graph.obj` size; `--load --serve` in a
detached container gives load time and post-warmup RSS. The build log is kept and
scraped for the trip-pattern count, which is the cheapest available tripwire for
the 2026-05-30 failure mode (non-monotonic synthetic stop_times cause OTP to
silently discard every transit pattern, with no error).

## Smoke test results

One variant only, as scoped. Host: 16 cores, 30 GB RAM, Docker,
`opentripplanner/opentripplanner:latest` = **OTP 2.10.0-SNAPSHOT**
(commit `cfbc1f62`, dev-2.x), `JAVA_TOOL_OPTIONS=-Xmx6G`.

### Variant generation — `spacing_500m`

| | |
|---|---|
| seed feed | `b1479e6:otp/alex_gtfs.zip` — 441 stops, 2,547 stop_times |
| generation wall time | **0.46 s** |
| synthetic stops generated / kept | 5,381 / **5,197** |
| total stops / stop_times | 5,638 / 7,744 |
| trips gaining synthetic stops | 192 / 192 |
| zip size | 423,009 B (seed: 318,295 B) |
| sha256 | `a506e1645c836f39cbee8b2dec2b6f486de961a110f39a6163294ce43bdbe4a7` |

Sanity check: consecutive synthetic stops measure 499.79 m apart.

### OD pairs

800 pairs, seed 42, 12x12 grid. 42 of 144 cells are served; 19-20 origins per
served cell; 200 pairs per distance band; no unfillable slots. Separation
min 1.02 km, p25 3.04, median 8.04, p75 20.03, max 67.19 km.

### Graph build and serve — `spacing_500m`

| | |
|---|---|
| graph build wall time (`--build --save`) | **190.3 s** |
| `graph.obj` | **542.8 MB** (542,806,097 B) |
| graph load time (`--load --serve`, to healthy) | 22.2 s |
| container RSS after 5 warmup queries | **5,474 MB** (cgroup anon; `memory.current` 5,571 MB; `docker stats` 5.127 GiB / 30.65 GiB) |
| OTP `Transit built.` | \|Stops\|=**5,638** \|Patterns\|=**192** \|ConstrainedTransfers\|=0 |
| timetable entries | 192 frequency-based, 0 single-trip |

Patterns 192 == trips 192, so no pattern was silently dropped — this feed's
synthetic stop_times are monotonic. RSS sits just under the 6 GB `-Xmx`, which is
exactly the caveat above: it measures the heap ceiling, not the graph. Note the
graph is dominated by the Egypt-wide OSM street network, not the transit data
(423 KB of GTFS producing a 543 MB graph), so cross-variant `graph.obj` deltas
will be small differences of a large number.

### Queries — 20 OD pairs

Evenly-spaced subsample of `data/od_pairs.csv`, `2026-08-03T08:00:00`, BUS+WALK,
`numItineraries=5`, serial, no warmup excluded beyond `run_otp.py`'s 5.

| | |
|---|---|
| pairs queried | 20 |
| GraphQL errors | **0** |
| pairs with >= 1 itinerary | **20 / 20** |
| pairs with a transit itinerary | 15 / 20 (the 5 misses are 1.1-1.4 km pairs where walk-only wins) |
| itineraries returned | 80 total, 70 containing a transit leg |
| itineraries boarding at a synthetic stop | **57 / 70** (40 with one SYN boarding, 17 with two) |
| transit legs per itinerary | 36x1, 29x2, 5x3 |
| walk distance on transit itineraries | median 1,646 m (min 106, max 3,000) |
| wall time | 4.5 s |

Latency (ms, single-threaded client):

| min | p50 | p90 | p95 | max | mean |
|---|---|---|---|---|---|
| 15.8 | **104.9** | 640.8 | 1139.7 | 1139.7 | 224.3 |

The tail is the long-distance band; the 1,139 ms outlier is the single 22 km pair.
With n=20 the p95/p99 are the same single observation — treat only p50 as meaningful
at this sample size.

Sample itinerary (`od0440`, 5.50 km, best of 5):

```
duration=932s  walkDistance=138m  walkTime=106s  waiting=180s
generalizedCost=1641  transfers=0
start=2026-08-03T08:00:00+03:00  end=2026-08-03T08:15:32+03:00
  WALK  103s   134m                 Origin            -> 1:SYN_104350 (Hail Bus 409)
  BUS   646s  5964m  route=Bus 409  1:SYN_104350      -> 1:435 (Navy Police Station)
  WALK    3s     3m                 1:435             -> Destination
```

This is the mechanism under test, visible in one trip: the rider walks 134 m to a
synthetic hail stop rather than to a surveyed stop. `waiting=180s` is one full
headway for Bus 409 — the frequency-trip artefact noted in [TODO](#todo).

### Isolation verified

`run_otp.py status` before and after: only `otp-bench-spacing_500m` ever existed,
bound to `127.0.0.1:8081->8080`; host `:8080` and `:8090` stayed free throughout;
`otp/egypt-latest.osm.pbf` link count went to 2 (hardlinked, not copied) and its
mtime is unchanged.

## TODO

- **`metrics.py` is stubs.** Every metric function raises `NotImplementedError`;
  the loaders and `stop_coords`/`stop_distance_m` are implemented and exercised.
  Deliberate: metrics get written against real result files from the full matrix,
  not guessed-at ones. Definitions and the open judgement calls are in the
  docstrings.
- **Full matrix not run.** Only `spacing_500m` (plus the `spacing_200m_legacy`
  validation feed) exists.
- **Toy-network analytic oracle** (research-plan.md Phase 3) not built. One flat
  route where the optimum is computable by hand, to certify the methodology.
- **Frequency-based feed.** `frequencies.txt` has one entry per trip and no
  `exact_times` column, so all 192 trips are headway trips and OTP charges a
  *full* headway as wait (phase1-verdict.md §2). Absolute durations are therefore
  not real travel times. The offset is spacing-invariant and cancels in the
  per-OD delta, but it inflates every duration and may distort ranking enough to
  change *which* itinerary is "best". Worth a sensitivity run with
  `frequencies.txt` stripped.
- **RSS is a weak metric.** With a fixed `-Xmx`, container RSS tracks the heap
  ceiling and GC timing more than graph size. `graph_obj_bytes` is the honest
  size signal. A better memory number would need JMX or a forced full GC.
- **Near-duplicate counts are filtered upstream.** OTP's itinerary filter chain
  and `numItineraries=5` suppress duplicates before the harness sees them, so
  metric 2 measures user-visible duplicates, not raw Raptor output. If counts come
  out at zero, re-run with a larger `numItineraries` before concluding anything.
- **The 1-3 km band is partly walk-only.** 5 of 20 smoke pairs (all 1.1-1.4 km)
  returned no transit itinerary at all, so they contribute nothing to the
  deviation metric. Either raise `--min-km` to ~1.5, or keep them and let
  `metrics.py` bucket them as `no_transit_either` — but do not let them dilute the
  band's effective n silently.
- **Graph size is dominated by OSM, not transit.** 423 KB of GTFS yields a 543 MB
  `graph.obj` because the street graph is Egypt-wide. Cross-variant `graph.obj`
  deltas will be small differences of a large number. Cropping the pbf to an
  Alexandria bbox would make the size metric legible, but changes the street
  network and so must be done identically for every variant, or not at all.
- **Stop-to-shape snapping is vertex-based**, inherited from `scripts/`: a real
  stop's along-shape position is the distance of the nearest shape *vertex*, not a
  perpendicular projection. Error is bounded by the shape's vertex spacing and is
  identical across variants, so it does not bias the comparison, but it does add
  noise to the interpolated times.
