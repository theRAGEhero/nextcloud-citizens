# Changelog

All notable changes to Nextcloud Citizens.

## [Unreleased]

### Recorder app-shell — 2026-08-24

- The phone recorder now behaves like a native app: page scrolling and
  overscroll-bounce are fully locked (fixed 100dvh shell, no pinch-zoom or
  double-tap zoom), each screen is header + internally-scrollable middle +
  pinned action bar with safe-area padding — READY / Start / Finish are
  always on screen, even with the live transcript panel open.


### Milestones 6 + 7-lite — 2026-08-24 (AI analysis, reports, recorder lock, GitHub)

- **AI analysis pipeline**: after transcription, each table is analyzed by the
  configured OpenAI-compatible endpoint (verified live against Ollama Cloud /
  deepseek-v4-flash): strict-JSON extraction validated by Pydantic with
  correction retries; findings without real transcript evidence are dropped;
  once every table of a round is analyzed, cross-table clustering runs
  automatically ("Mentioned at N tables" — never support percentages).
  Findings are DRAFTs with mandatory human review (approve / reject / edit →
  EDITED_AND_APPROVED; original AI output preserved for audit).
- **Analysis tab** (review UI with evidence expanders, re-run, guided empty
  states) and **Report tab**: assembly report from approved findings
  (optional clearly-marked drafts), evidence quotes with timestamps, fixed
  AI-assistance methodology note, Markdown + JSON downloads.
- **Recorder lock**: after a table's recording is synchronized the device is
  locked on a completion screen — no way back to start a stray recording; the
  server refuses a second healthy recording per table+round (409); the next
  round appears automatically when the facilitator starts it; failed attempts
  (invalid/incomplete audio) still allow re-recording.
- Published to GitHub: https://github.com/theRAGEhero/nextcloud-citizens
  (public; tracked files and full history verified clean of secrets).
- 54 backend tests; Playwright offline tests green; full chain verified live
  end-to-end including a real cross-table finding.

### UI/UX design round — 2026-08-23

- Organizer rebuilt around Nextcloud's native app-shell: sidebar navigation
  (assembly list with status dots, admin Settings), content pane with
  assembly header, icon tabs and a new Overview tab (stat cards + state-aware
  "next step" guidance). Design system in `frontend/src/components/ui/`:
  MDI icons, buttons, status pills, empty states, skeleton loaders,
  confirmation modals for destructive actions, toasts. Full dark-theme and
  mobile support; conversation-style transcript view; countdown bar with
  progress in the Live tab; refined printable QR sheet.
- Recorder redesigned: hero table number, pulsing record ring around the
  timer, iconized pre-flight checklist and status rows, caption bubbles,
  animated success state.
- Fixed a real M4 regression the screenshot audit caught: the phone's
  completion poll only accepted AUDIO_READY and hung when auto-transcription
  advanced the state within seconds — it now accepts every post-validation
  state.
- Verified: screenshot audit (light/dark, desktop/mobile, all screens),
  Playwright offline tests A & C, 47 backend tests, typecheck clean.
  Organizer bundle +13 KB gzip, recorder +3 KB.

### Milestone 4 — 2026-08-23 (STT: batch + live)

- Batch transcription pipeline: after audio validation, recordings are
  automatically transcribed by the configured provider (Deepgram `nova-3`
  with `diarize_model=latest` + utterances; Mistral Voxtral
  `voxtral-mini-latest` with `diarize` — model IDs verified against provider
  docs 2026-08-23 and admin-configurable). Normalized transcript schema
  (SPEAKER_NN by first appearance, segments + word timestamps), raw provider
  JSON retained on disk, durable TRANSCRIBE_FINAL job with temporary-error
  retry and permanent-error surfacing, organizer transcript API + manual
  (re)transcribe, transcript panel in the Live tab.
- Provisional live captions: the phone's safety chunks are forwarded into a
  server-side Deepgram streaming session (zero extra phone bandwidth);
  recorder "Show live transcript" panel, clearly labeled PROVISIONAL;
  failures cool down instead of reconnect-looping and never affect
  recording. Mistral Voxtral Realtime not yet wired (captions report
  unavailable with Mistral).
- Settings: STT model fields per provider; "Test connection" now tests the
  key typed in the form before saving (the reported "No API key configured"
  confusion). Deepgram key stored (encrypted) and verified live; full
  speech → chunked upload → assembly → automatic Deepgram transcription with
  diarization verified end-to-end on the production server, live captions
  included. 52 tests.

### Fix round + platform upgrade — 2026-08-23

- **Recorder CSP fix**: the page moved to `/recorder.html` and ships its own
  Content-Security-Policy — Nextcloud's proxy applies `default-src 'none'`
  (no script allowance) to proxied ExApp pages and only an ExApp-provided CSP
  header survives. Mic-test playback via WebAudio (blob: media is blocked).
  Old `/recorder/` QR links require regeneration (proxy follows redirects
  internally). Live join → record → synchronize verified in a headless
  browser against the production URL.
- **QR codes** render with a viewBox (no more clipping); printable sheet kept.
- **Organizer layout**: opaque Nextcloud-style app surface, ID-scoped styles
  (NC core `button:not()` chains override plain classes), underline tabs,
  fixed accessible danger red, full-width surface, recorder asset cache
  busting via app version.
- **Admin Speech & AI settings**: sensitive AppConfig key storage (hint-only
  responses), STT provider choice, live/final toggles, OpenAI-compatible
  analysis endpoint (Ollama-ready), connection tests, audit trail. 37 tests.
- **Nextcloud upgraded 32.0.0 → 33.0.8 → 34.0.3** (user-approved): per-hop
  DB dumps + code-volume backup + rollback doc in
  `/root/backups/nextcloud-upgrade-20260823/`; app_api auto-updated to 34.0.0;
  Citizens ExApp registration survived both hops; full live recording
  round-trip re-verified on 34.

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
