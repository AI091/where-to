# Hail-and-Ride

**Context in the journey:** Realized Alexandria transit doesn't follow fixed stops.

**What it is:** A transit pattern where passengers can board and alight anywhere safe along the route — not just at designated stops. Common in informal transit systems.

**Why it matters in Alexandria:** Microbuses, buses, and minibuses all operate this way. Standard GTFS with fixed stops doesn't model it well.

**How to simulate it in OTP:** Generate synthetic stops at regular intervals (every 100–200m) along each route's path. OTP sees extra stops everywhere and routes accordingly.

**GTFS native support:** GTFS has `continuous_pickup` and `continuous_drop_off` fields (2019) for this. OTP has partial support via FlexRouting, but [as of Feb 2026 it's broken](https://github.com/opentripplanner/OpenTripPlanner/issues/7304) — routes marked as hail-and-ride still only stop at fixed stops.

**Workaround:** Synthetic stops in the GTFS data (planned edit to our dataset).

**Resources**
- [GTFS continuous stop extension](https://gtfs.org/schedule/reference/#stop_timestxt)
- [OTP issue: continuous pickup/dropoff doesn't work](https://github.com/opentripplanner/OpenTripPlanner/issues/7304)
