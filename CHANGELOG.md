# Changelog

All notable changes to Nextcloud Citizens.

## [Unreleased]

### Milestone 3 — 2026-08-23

- Offline resilience: exponential-backoff upload retry with online-event
  wake and manual retry; reload/crash recovery (IndexedDB scan → "Recovered
  recording" → resume synchronization); storage monitoring with low-space and
  write-failure alerts; explicit local cleanup of synchronized recordings.
- Device heartbeats (20 s) + client log shipping to the server (offline-
  tolerant, per-session JSONL); facilitator "Live" dashboard tab with round
  start/end controls, per-table device/upload/local-safe status and device
  log viewer.
- Round lifecycle (start/end, single-active enforcement); recorder prompts
  to finish when the facilitator ends the round.
- SQLite `BEGIN IMMEDIATE` transactions — fixes "database is locked" under
  concurrent device uploads.
- Release-blocker tests all passing: §56 Test A (network loss) and Test C
  (reload recovery) as Playwright browser tests with a fake microphone
  (Firefox), Test D/E in pytest, Test F (10 concurrent devices) as a load
  script. 31 backend tests total.

### Milestone 2 — 2026-08-23

- Public recorder API: invite-token join → short-lived scoped recorder session
  (hash-only bearer), start recording, chunked upload (raw octet-stream,
  SHA-256 verified, idempotent on recording+sequence+hash), complete with
  server-side missing-chunk detection and resend, status polling. Join
  endpoint rate-limited.
- Recording state machine (§24) with explicit resumable transitions; durable
  SQLite job runner (claim/retry/backoff, stale-RUNNING recovery on restart);
  ASSEMBLE_AUDIO job: concat → ffprobe validate → ffmpeg remux → canonical
  file + checksum + manifest.json.
- Recorder phone SPA (separate PUBLIC bundle, no Nextcloud chrome): QR join
  (secret stripped from URL), pre-flight checks (mic, formats, IndexedDB,
  persistence, connectivity, level meter, 5-s test), recording screen with
  IndexedDB-first chunk pipeline, upload/pending status, offline banner,
  wake lock, finish → synchronize → server-validated done state.
- 28 tests total; recorder integration suite uses real opus audio through the
  real assembly pipeline and covers duplicate upload (Test D) and missing
  chunk (Test E). Live HTTPS end-to-end verified on the dev server
  (join → upload → AUDIO_READY, duration validated).

### Milestone 1 — 2026-08-23

- Assembly core backend: assemblies, rounds (add/edit/reorder/delete), tables,
  participants (manual + CSV import, anonymous labels), random table
  assignment, copy-from-previous-round, manual moves. Ownership authorization
  (creator-scoped; missing and not-owned both answer 404).
- Recorder invites: 256-bit tokens (SHA-256 hash stored only), QR SVGs
  (segno) returned exactly once at generation, revoke/regenerate, audit
  events. Invite URLs carry the token in the URL fragment.
- Organizer SPA: Vue 3 + TypeScript + Vite (single IIFE bundle into `js/` +
  `css/`) — assembly list, creation wizard, rounds/participants/tables/QR
  tabs, printable QR sheet. Nextcloud theming via CSS variables.
- 17 tests incl. an integration suite covering the 50-participant/10-table/
  2-round acceptance flow; fixed a SQLite self-deadlock (audit writes now use
  the request session).

### Milestone 0 — 2026-08-23

- ExApp skeleton: FastAPI + nc_py_api (heartbeat/init/enabled), SQLite with
  WAL + foreign keys, first Alembic migration (audit_events), structured
  logging (structlog: dev console + rotating JSONL, secret redaction,
  request-ID correlation), `/api/v1/health`.
- Registered on the live Nextcloud via an AppAPI manual-install daemon;
  "Citizens" top-menu entry renders the M0 shell with live health data for
  `citizens-test`.
- Dev workflow: `make up` (auto-reload container, 512 MB cap), `make register`,
  `make test`/`make lint` (run inside the container image — the host is too
  memory-constrained for a native venv), `make dev-reset` (Citizens data only).
- Verified AppAPI route access control end-to-end; documented non-obvious
  AppAPI behaviours (numeric access levels in `--json-info`, no-leading-slash
  route regexes, session-only proxy auth, `/apps/app_api/proxy/` URL form) in
  `docs/architecture.md`.

### Phase 0 — 2026-08-23

- Inventoried the development server (Nextcloud 32.0.0.13, AppAPI 32, clean
  ExApp slate); documented in `docs/development-environment.md`.
- Created and restore-tested a pre-Citizens Nextcloud backup (DB + config +
  custom_apps + compose): `/root/backups/nextcloud-pre-citizens-20260823/`.
- Repository baseline: README, docs, changelog, gitignore.
