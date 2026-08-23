# Changelog

All notable changes to Nextcloud Citizens.

## [Unreleased]

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
