#!/usr/bin/env python3
"""
Temporary experiment: Generate synthetic hail-and-ride stops along route shapes.

What this does:
1. Reads shapes.txt (route path geometries), sorted by shape_pt_sequence
2. For each shape, walks the path and generates a synthetic stop every ~200m
3. Interpolates arrival/departure times proportional to position on the route
4. Interleaves synthetic stops between real stops by stop_sequence
5. Writes output CSVs that can be merged into the GTFS zip

Usage:
    cd /home/ahmed/where-to/otp
    python3 ../scripts/generate_hail_ride_stops.py

Output:
    - synthetic_stops.csv
    - synthetic_stop_times.csv
"""

import csv
import math
import itertools


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two lat/lon points."""
    R = 6371000  # Earth radius in meters
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def interpolate(lat1, lon1, lat2, lon2, ratio):
    """Interpolate a point between two lat/lon points at given ratio (0-1)."""
    return lat1 + (lat2 - lat1) * ratio, lon1 + (lon2 - lon1) * ratio


def build_shape_with_distances(shape_points):
    """
    Convert a list of (lat, lon) into a list of (lat, lon, cumulative_distance_from_start).
    Handles zero-length segments gracefully.
    """
    result = []
    total = 0.0
    result.append((shape_points[0][0], shape_points[0][1], 0.0))

    for i in range(1, len(shape_points)):
        lat1, lon1 = shape_points[i - 1]
        lat2, lon2 = shape_points[i]
        d = haversine(lat1, lon1, lat2, lon2)
        if d < 0.01:  # Skip near-identical points
            continue
        total += d
        result.append((lat2, lon2, total))

    return result, total


def generate_synthetic_stops(shape_with_dist, interval_meters):
    """
    Walk along a shape and generate synthetic stops every `interval_meters`.

    shape_with_dist: list of (lat, lon, distance_from_start) tuples
    Returns: list of (lat, lon, distance_from_start)
    """
    synthetic = []
    next_stop_dist = interval_meters
    max_dist = shape_with_dist[-1][2]

    for i in range(1, len(shape_with_dist)):
        lat1, lon1, d1 = shape_with_dist[i - 1]
        lat2, lon2, d2 = shape_with_dist[i]
        seg_len = d2 - d1

        while next_stop_dist <= d2 and next_stop_dist <= max_dist:
            ratio = (next_stop_dist - d1) / seg_len
            lat, lon = interpolate(lat1, lon1, lat2, lon2, ratio)
            synthetic.append((lat, lon, next_stop_dist))
            next_stop_dist += interval_meters

    return synthetic


def time_to_seconds(t):
    """Convert GTFS time HH:MM:SS to seconds since midnight."""
    parts = t.split(':')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def interpolate_time(t1_str, t2_str, ratio):
    """Get a time string between t1 and t2 at the given ratio (0-1)."""
    t1 = time_to_seconds(t1_str)
    t2 = time_to_seconds(t2_str)
    t = t1 + (t2 - t1) * ratio
    h, m = divmod(int(t), 3600)
    m, s = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def find_nearest_point_on_shape(lat, lon, shape_with_dist):
    """Find the distance along a shape for a given lat/lon (closest point)."""
    best_dist = float('inf')
    best_pos = 0.0
    for slat, slon, sdist in shape_with_dist:
        d = haversine(lat, lon, slat, slon)
        if d < best_dist:
            best_dist = d
            best_pos = sdist
    return best_pos


def read_gtfs_file(zip_path, filename):
    """Read a CSV file from the GTFS zip."""
    import zipfile
    with zipfile.ZipFile(zip_path, 'r') as z:
        with z.open(filename) as f:
            return list(csv.DictReader(f.read().decode('utf-8').splitlines()))


def main():
    GTFS_ZIP = '/home/ahmed/where-to/otp/alex_gtfs.zip'
    INTERVAL = 200  # meters between synthetic stops

    print(f"Reading GTFS from {GTFS_ZIP}...")

    shapes_raw = read_gtfs_file(GTFS_ZIP, 'shapes.txt')
    routes = read_gtfs_file(GTFS_ZIP, 'routes.txt')
    trips = read_gtfs_file(GTFS_ZIP, 'trips.txt')
    stoptimes = read_gtfs_file(GTFS_ZIP, 'stop_times.txt')
    stops = read_gtfs_file(GTFS_ZIP, 'stops.txt')

    print(f"Found {len(routes)} routes, {len(trips)} trips, {len(stoptimes)} stop_times")

    # Build shapes: shape_id -> sorted list of (lat, lon)
    shapes_sorted = {}
    for row in shapes_raw:
        sid = row['shape_id']
        if sid not in shapes_sorted:
            shapes_sorted[sid] = []
        shapes_sorted[sid].append((int(row['shape_pt_sequence']), float(row['shape_pt_lat']), float(row['shape_pt_lon'])))

    # Sort by sequence number, then drop it
    shapes_by_id = {}
    for sid, pts in shapes_sorted.items():
        pts.sort(key=lambda p: p[0])
        shapes_by_id[sid] = [(p[1], p[2]) for p in pts]

    # Build shape -> distance map (for time interpolation)
    shape_with_dist_cache = {}
    for sid, pts in shapes_by_id.items():
        shape_with_dist_cache[sid] = build_shape_with_distances(pts)

    # Stops lookup: stop_id -> (lat, lon)
    stops_by_id = {s['stop_id']: (float(s['stop_lat']), float(s['stop_lon'])) for s in stops}

    # Build: route -> shape_id
    route_to_shape = {}
    for t in trips:
        rid = t['route_id']
        if rid not in route_to_shape and t.get('shape_id'):
            route_to_shape[rid] = t['shape_id']

    all_synthetic_stops = []
    all_synthetic_stop_times = []
    stop_id_counter = itertools.count(100000)

    processed_routes = 0
    for route in routes:
        rid = route['route_id']
        if rid not in route_to_shape:
            continue

        shape_id = route_to_shape[rid]
        if shape_id not in shapes_by_id or shape_id not in shape_with_dist_cache:
            continue

        raw_pts = shapes_by_id[shape_id]
        swd, total_dist = shape_with_dist_cache[shape_id]
        synthetic = generate_synthetic_stops(swd, INTERVAL)

        if not synthetic:
            continue

        processed_routes += 1
        print(f"Route {route.get('route_short_name', rid)} ({shape_id[:12]}...): "
              f"{len(synthetic)} synthetic stops, {total_dist:.0f}m total")

        # Create synthetic stops
        route_syn_stops = []
        for lat, lon, dist in synthetic:
            sid = f"SYN_{next(stop_id_counter)}"
            route_syn_stops.append({
                'stop_id': sid,
                'stop_name': f"Hail {route.get('route_short_name', 'unknown')}",
                'stop_lat': f"{lat:.6f}",
                'stop_lon': f"{lon:.6f}",
                'distance': dist,
            })
        all_synthetic_stops.extend(route_syn_stops)

        # For each trip on this route, interleave synthetic stops
        route_trips = [t for t in trips if t['route_id'] == rid]
        for trip in route_trips:
            trip_id = trip['trip_id']

            existing = sorted(
                [st for st in stoptimes if st['trip_id'] == trip_id],
                key=lambda s: int(s['stop_sequence'])
            )
            if len(existing) < 2:
                continue

            # For each real stop, find its distance along the shape
            real_stops_with_dist = []
            for st in existing:
                sid = st['stop_id']
                if sid in stops_by_id:
                    slat, slon = stops_by_id[sid]
                    pos = find_nearest_point_on_shape(slat, slon, swd)
                    real_stops_with_dist.append((st, pos))

            # For each synthetic stop, find which two real stops it's between
            # and interpolate its time + sequence
            synthetic_with_segments = []
            for syn in route_syn_stops:
                syn_dist = syn['distance']
                # Find the real stops before and after this synthetic stop
                before = None
                after = None
                for rst, rdist in real_stops_with_dist:
                    if rdist <= syn_dist:
                        before = (rst, rdist)
                    if rdist >= syn_dist and after is None:
                        after = (rst, rdist)
                if before and after and before[1] < after[1]:
                    synthetic_with_segments.append((syn, before, after))

            # Now create stop_times: interleave synthetic stops with real stops
            new_sequence = 0
            syn_idx = 0
            for rst, rdist in real_stops_with_dist:
                # Output all synthetic stops before this real stop
                while syn_idx < len(synthetic_with_segments):
                    syn_stop, before, after = synthetic_with_segments[syn_idx]
                    if before[0]['stop_id'] != rst['stop_id']:
                        break
                    # Interpolate time
                    ratio = ((syn_stop['distance'] - before[1])
                             / (after[1] - before[1]))
                    arr = interpolate_time(before[0]['arrival_time'], after[0]['arrival_time'], ratio)
                    dep = interpolate_time(before[0]['departure_time'], after[0]['departure_time'], ratio)

                    all_synthetic_stop_times.append({
                        'trip_id': trip_id,
                        'stop_id': syn_stop['stop_id'],
                        'stop_sequence': str(new_sequence),
                        'arrival_time': arr,
                        'departure_time': dep,
                        'timepoint': '0',
                    })
                    new_sequence += 1
                    syn_idx += 1

    print(f"\nProcessed {processed_routes} routes")
    print(f"Generated {len(all_synthetic_stops)} synthetic stops")
    print(f"Generated {len(all_synthetic_stop_times)} synthetic stop_times")

    # Write output
    if all_synthetic_stops:
        with open('synthetic_stops.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['stop_id', 'stop_name', 'stop_lat', 'stop_lon'])
            writer.writeheader()
            for s in all_synthetic_stops:
                writer.writerow({k: s[k] for k in ['stop_id', 'stop_name', 'stop_lat', 'stop_lon']})
        print("Wrote synthetic_stops.csv")

    if all_synthetic_stop_times:
        with open('synthetic_stop_times.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'trip_id', 'stop_id', 'stop_sequence', 'arrival_time', 'departure_time', 'timepoint'
            ])
            writer.writeheader()
            writer.writerows(all_synthetic_stop_times)
        print("Wrote synthetic_stop_times.csv")


if __name__ == '__main__':
    main()
