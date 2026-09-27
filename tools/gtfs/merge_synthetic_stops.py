#!/usr/bin/env python3
"""
Fix: Merge synthetic stops properly into GTFS.

Problem: Synthetic stop_times were appended with duplicate/conflicting sequence numbers.
Solution: For each trip with synthetic stops, combine original + synthetic entries,
sort by position along route, renumber sequences monotonically.
"""

import csv
import math
import zipfile
import shutil
import os

OTP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'infra', 'otp')


def time_to_seconds(t):
    """Convert HH:MM:SS to seconds since midnight."""
    parts = t.split(':')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def seconds_to_time(s):
    """Convert seconds since midnight to HH:MM:SS."""
    h, m = divmod(int(s), 3600)
    m, s = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def read_csv_from_zip(zip_path, filename):
    with zipfile.ZipFile(zip_path, 'r') as z:
        with z.open(filename) as f:
            return list(csv.DictReader(f.read().decode('utf-8').splitlines()))


def write_csv_to_zip(zip_path, filename, rows, fieldnames):
    # Read existing zip contents
    temp_zip = zip_path + '.tmp'
    with zipfile.ZipFile(zip_path, 'r') as zin:
        with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename != filename:
                    zout.writestr(item, zin.read(item.filename))
            # Write the new file
            import io
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            zout.writestr(filename, buf.getvalue().encode('utf-8'))
    shutil.move(temp_zip, zip_path)


def main():
    GTFS_ZIP = os.path.join(OTP_DIR, 'alex_gtfs.zip')
    SYNTHETIC_STOPS_CSV = os.path.join(OTP_DIR, 'synthetic_stops.csv')
    SYNTHETIC_STOP_TIMES_CSV = os.path.join(OTP_DIR, 'synthetic_stop_times.csv')

    print("Reading original GTFS...")
    original_stops = read_csv_from_zip(GTFS_ZIP, 'stops.txt')
    original_stop_times = read_csv_from_zip(GTFS_ZIP, 'stop_times.txt')
    shapes = read_csv_from_zip(GTFS_ZIP, 'shapes.txt')
    trips = read_csv_from_zip(GTFS_ZIP, 'trips.txt')
    routes = read_csv_from_zip(GTFS_ZIP, 'routes.txt')

    print(f"Original: {len(original_stops)} stops, {len(original_stop_times)} stop_times")

    # Read synthetic data
    with open(SYNTHETIC_STOPS_CSV) as f:
        synthetic_stops = list(csv.DictReader(f))
    with open(SYNTHETIC_STOP_TIMES_CSV) as f:
        synthetic_stop_times = list(csv.DictReader(f))

    print(f"Synthetic: {len(synthetic_stops)} stops, {len(synthetic_stop_times)} stop_times")

    # Build lookups
    stops_by_id = {s['stop_id']: (float(s['stop_lat']), float(s['stop_lon'])) for s in original_stops}
    shapes_by_id = {}
    for row in shapes:
        sid = row['shape_id']
        if sid not in shapes_by_id:
            shapes_by_id[sid] = []
        shapes_by_id[sid].append((int(row['shape_pt_sequence']), float(row['shape_pt_lat']), float(row['shape_pt_lon'])))
    for sid in shapes_by_id:
        shapes_by_id[sid].sort(key=lambda p: p[0])
        shapes_by_id[sid] = [(p[1], p[2]) for p in shapes_by_id[sid]]

    trip_to_shape = {}
    for t in trips:
        if t.get('shape_id') and t['trip_id'] not in trip_to_shape:
            trip_to_shape[t['trip_id']] = t['shape_id']

    # Build shape distance cache
    shape_dists = {}
    for sid, pts in shapes_by_id.items():
        dists = []
        total = 0.0
        dists.append((pts[0][0], pts[0][1], 0.0))
        for i in range(1, len(pts)):
            d = haversine(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])
            total += d
            dists.append((pts[i][0], pts[i][1], total))
        shape_dists[sid] = dists

    def find_dist_on_shape(lat, lon, dists):
        best = float('inf')
        best_pos = 0.0
        for slat, slon, sdist in dists:
            d = haversine(lat, lon, slat, slon)
            if d < best:
                best = d
                best_pos = sdist
        return best_pos

    # Group stop_times by trip
    orig_by_trip = {}
    for st in original_stop_times:
        tid = st['trip_id']
        if tid not in orig_by_trip:
            orig_by_trip[tid] = []
        orig_by_trip[tid].append(st)

    syn_by_trip = {}
    for st in synthetic_stop_times:
        tid = st['trip_id']
        if tid not in syn_by_trip:
            syn_by_trip[tid] = []
        syn_by_trip[tid].append(st)

    # Build new stop_times
    new_stop_times = []
    affected_trips = 0

    for tid, orig_list in orig_by_trip.items():
        if tid not in syn_by_trip:
            # No synthetic stops — keep original as-is
            new_stop_times.extend(orig_list)
            continue

        affected_trips += 1
        shape_id = trip_to_shape.get(tid)
        if not shape_id or shape_id not in shape_dists:
            # No shape info — keep original
            new_stop_times.extend(orig_list)
            continue

        dists = shape_dists[shape_id]

        # Get position for each original stop
        orig_with_pos = []
        for st in orig_list:
            sid = st['stop_id']
            if sid in stops_by_id:
                lat, lon = stops_by_id[sid]
                pos = find_dist_on_shape(lat, lon, dists)
                orig_with_pos.append((st, pos))

        # Get position for each synthetic stop
        syn_with_pos = []
        for st in syn_by_trip[tid]:
            # Find the synthetic stop's lat/lon
            syn_stop_id = st['stop_id']
            syn_lat = None
            syn_lon = None
            for syn_stop in synthetic_stops:
                if syn_stop['stop_id'] == syn_stop_id:
                    syn_lat = float(syn_stop['stop_lat'])
                    syn_lon = float(syn_stop['stop_lon'])
                    break
            if syn_lat is not None:
                pos = find_dist_on_shape(syn_lat, syn_lon, dists)
                syn_with_pos.append((st, pos))

        # Combine and sort by position
        combined = orig_with_pos + syn_with_pos
        combined.sort(key=lambda x: x[1])

        # Find trip's first and last real stop times for interpolation
        first_real = orig_with_pos[0]
        last_real = orig_with_pos[-1]
        first_time = time_to_seconds(first_real[0]['arrival_time'])
        last_time = time_to_seconds(last_real[0]['arrival_time'])
        total_dist = last_real[1]

        # Regenerate times for ALL stops based on position fraction
        for i, (st, pos) in enumerate(combined):
            st['stop_sequence'] = str(i + 1)
            # Time = first_time + (last_time - first_time) * (pos / total_dist)
            if total_dist > 0:
                ratio = pos / total_dist
            else:
                ratio = 0
            t_secs = first_time + (last_time - first_time) * ratio
            t_str = seconds_to_time(int(t_secs))
            st['arrival_time'] = t_str
            st['departure_time'] = t_str
            new_stop_times.append(st)

    print(f"Affected trips: {affected_trips}")
    print(f"Total stop_times in output: {len(new_stop_times)}")

    # Write stops.txt (original + synthetic)
    all_stops = original_stops + synthetic_stops
    write_csv_to_zip(GTFS_ZIP, 'stops.txt', all_stops, ['stop_id', 'stop_name', 'stop_lat', 'stop_lon'])
    print(f"Wrote {len(all_stops)} stops")

    # Write stop_times.txt (merged and re-sequenced)
    write_csv_to_zip(GTFS_ZIP, 'stop_times.txt', new_stop_times,
                     ['trip_id', 'stop_id', 'stop_sequence', 'arrival_time', 'departure_time', 'timepoint'])
    print(f"Wrote {len(new_stop_times)} stop_times")

    print("Done. Rebuild OTP with: docker compose up -d --build")


if __name__ == '__main__':
    main()
