# Project Vision

> To be filled in during the next session with the grill-me skill.

## Goal

Build a mobile app for public transit in Alexandria.

## Target user

Commuter-first (expand later).

## App flow (draft)

1. User picks origin (current location / tap on map / search)
2. User picks destination
3. App shows trip options using OTP

## Backend services

| Service | Status |
|---------|--------|
| OTP (routing) | Running |
| Photon (geocoding) | Next |
| Tileserver (map tiles) | Deferred — using external OSM tiles |

## Tech stack

- Backend: Docker Compose (OTP + Photon)
- Mobile: React Native

## Offline

Currently an online-only app. OTP is server-side, so routing requires a connection regardless of tile source. Full offline would require embedding OTP on-device — a distant future consideration.
