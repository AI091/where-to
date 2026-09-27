# Hail-and-Ride

**Context in the journey:** Realized Alexandria transit doesn't follow fixed stops.

**What it is:** A transit pattern where passengers can board and alight anywhere safe along the route — not just at designated stops. Common in informal transit systems.

**Why it matters in Alexandria:** Microbuses, buses, and minibuses all operate this way. Standard GTFS with fixed stops doesn't model it well.

**How to simulate it in OTP:** Generate synthetic stops at regular intervals (every 100–200m) along each route's path. OTP sees extra stops everywhere and routes accordingly.

**GTFS native support:** GTFS has `continuous_pickup` and `continuous_drop_off` fields (2019) for this. OTP 2 reads them and then ignores them, with no warning, so routes marked as hail-and-ride still only stop at fixed stops ([issue #7304](https://github.com/opentripplanner/OpenTripPlanner/issues/7304)). GTFS-Flex, OTP's feature for on-demand transit, doesn't fit either: it doesn't follow route shapes and allows only one flex leg per trip. OTP 1 supported flag stops in 2019, but that was lost in the OTP 2 rewrite.

**Workaround:** Synthetic stops in the GTFS data (planned edit to our dataset).

**Not every stretch is hail-and-ride:** Hail-and-ride belongs to stretches of road, not to whole routes. The same microbus stops anywhere downtown, doesn't stop on a highway, then stops anywhere again on the other side:

```
Route:  ═══●══════════●═══[ highway over the lake ]═══●══════════●═══
           hail-and-ride     no stopping here          hail-and-ride
```

GTFS models this per stretch: `continuous_pickup` / `continuous_drop_off` in `stop_times.txt` apply from that stop to the next one, and override the route-wide value in `routes.txt`. Our feed never uses this. All 104 routes have `continuous_pickup=1`, which means "no hail-and-ride anywhere".

**Example (2026-09-27):** With synthetic stops every 250 m, OTP flagged 1,193 of them as isolated: nobody can walk to them, because the map bans walking on the road they sit on. Almost all are on two highway corridors crossing Lake Mariout (red below). Decision: drop synthetic stops a pedestrian can't reach.

![Isolated synthetic stops on the Lake Mariout highways](../images/lake-mariout-isolated-stops.png)

**Resources**
- [GTFS continuous stop extension](https://gtfs.org/schedule/reference/#stop_timestxt)
- [OTP issue: continuous pickup/dropoff doesn't work](https://github.com/opentripplanner/OpenTripPlanner/issues/7304)
