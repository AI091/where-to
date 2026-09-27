# Project Vision

> Agreed in a grill session on 2026-09-27.

## Goal

A public trip-planning app for Alexandria's buses, minibuses and microbuses, all of which are hail-and-ride.

## Target user

The public in Alexandria, commuter-first. Arabic route and stop names are required before launch.

## App flow (draft)

1. User picks origin (current location / tap on map / search)
2. User picks destination
3. App shows trip options with estimates ("about 35 min", "every ~3 min"), not clock times

## Hail-and-ride

Main line: synthetic stops every 250 m (at most ~125 m extra walk). In parallel, a local OTP fork explores boarding, alighting and changing buses anywhere.

## Backend services

| Service | Tech | Status |
|---------|------|--------|
| API | TypeScript + Hono on Bun | Next: port Go `/getPath` |
| OTP (routing) | Pinned version | Speed work first: 95% of searches < 1 s |
| Photon (address search) | — | Part of the backend milestone |
| Map tiles | External OSM tiles | Deferred |

## Order

1. OTP speed and spacing
2. Port Go to TypeScript
3. Estimates in responses
4. Photon

Later: hosting, mobile app (React Native).

## Offline

Currently an online-only app. OTP is server-side, so routing requires a connection regardless of tile source. Full offline would require embedding OTP on-device — a distant future consideration.
