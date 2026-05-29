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
| Tileserver (map) | Next |

## Tech stack

- Backend: Docker Compose (OTP + Photon + Tileserver)
- Mobile: React Native
