# Changelog

All notable changes to Nextcloud Citizens.

## [Unreleased]

### Closing a session, Files tab, interim vs final report — 2026-08-25 (v0.5.0)

- **A report is now interim until you close the session.** The Report tab says
  so plainly ("Interim report — 1 of 3 tables have completed all rounds") and
  the PDF/Markdown/JSON downloads stay disabled until then. Closing creates the
  **final report** (stamped FINAL with a "N of M tables contributed" coverage
  line), stops phones from recording, and runs a last analysis pass over the
  tables that did participate. Reopening is possible for a late table.
- **The published report freezes at closing**: participants keep reading the
  version from when you closed, even if you reopen the session and new content
  arrives. Closing again republishes the updated version.
- **New Files tab per assembly**: every table's audio with duration, size and
  state; download one table, download all audio as a ZIP, or **export the full
  session** (manifest with checksums, audio, transcripts, findings and the
  report — portable to another server). Audio can be deleted per table or for
  the whole session **without deleting the session**: transcripts, findings and
  the report are kept.
- **QR sheet**: a proper "Copy link" button per table replaces the tiny icon.
- Fixed: assemblies stayed "Draft" forever in independent mode — the status now
  moves to Active on the first recording and Complete when closed.

### Independent mode: auto-advancing rounds, table summaries, auto-report — 2026-08-25 (v0.4.1)

- **Rounds advance automatically per table**: when a round's planned time
  elapses the phone finishes on its own (15 s "Keep talking" grace), and
  after any finish — timed or manual — it advances to a break-friendly
  "We're ready — Start Round N" prompt showing the next question. Recording
  starts only on that tap.
- **The table sees its own results**: after the last round, the phone shows
  that table's AI summary for each round as analysis completes.
- **The report reaches phones in two cases**: automatically once EVERY table
  has completed EVERY round (independent assemblies; with analysis enabled
  the summaries must be ready so the report is never empty), or the moment
  the organizer clicks Publish. Managed assemblies stay publish-only.
  Verified live end-to-end with a 1-minute timed round.

### Round-end 500 fix + managed flow + institutional reports — 2026-08-24 (v0.4.0)

- **Fixed the round-end HTTP 500** ("database is locked"): background jobs held
  the SQLite write lock across minutes-long ffmpeg/transcription/analysis
  calls, starving the phones' finish requests. Jobs now release the lock
  before external work; verified live with zero failures across 204 status
  requests hammered through a full processing chain.
- **Phones never dead-end**: transient server errors auto-retry with backoff
  ("busy server" note), and a failure screen gains a Try again button. The
  done screen keeps the table armed for the organizer's readiness count.
- **Managed flow end-to-end**: after ending a round the Live tab shows a
  one-click "Start Round N+1" banner (and an "all rounds done" pointer);
  when the organizer publishes the report, phones auto-open it after a 3 s
  countdown.
- **Institutional PDF**: branded header with organization logo + name (new
  Settings fields), generation date, executive summary of all rounds,
  grouped findings with colored type badges, evidence quote bars, running
  footer with page numbers.
- **Consensus/divergence vocabulary** everywhere (report, analysis tab,
  phones): Proposals · Points of consensus · Points of divergence ·
  Concerns raised · Open questions · Minority positions · Emerging ideas;
  the AI prompts now actively hunt for conflicts within and between tables,
  naming both sides.
- **Per-assembly AI instructions** (wizard + Overview) appended to the global
  admin instructions.
- Settings shows only the selected transcription provider's fields.
- **Deleting an assembly now deletes its audio files** (chunks, canonical
  audio, transcripts, exports) along with the database records.

### Reports round — 2026-08-24 (v0.3.0)

- **PDF reports** with the organization logo on the header (logo uploadable in
  Settings, PNG/JPEG up to 1 MB), alongside Markdown and JSON.
- **Publish report to tables**: a new button on the Report tab makes the
  report (approved findings + AI summaries only — never drafts) visible on
  the recording phones, which get a "View assembly report" screen with a
  PDF download. Unpublish anytime.
- **QR codes re-viewable anytime**: invite links are now stored encrypted
  with the app secret, so the QR tab always shows the printable sheet again
  (join verification still runs on hashes; a database dump alone reveals
  nothing). Codes issued before this release still need one regenerate.
- **Custom AI instructions**: Settings gains an "Additional analysis
  instructions" field appended to the built-in prompts (shown read-only for
  reference); the JSON output contract and mandatory evidence links cannot
  be overridden.
- Wizard and round form fields now stretch to full width; device ages on the
  Live tab read "3m ago / 11h ago" instead of thousands of seconds.
- Settings remains admin-only (enforced at the Nextcloud proxy; the nav item
  hides for non-admins). Assemblies stay private per organizer account.

### Recorder polish round — 2026-08-24 (v0.2.0)

- **Nextcloud-style recorder**: the phone recorder now uses the same light
  Nextcloud design language as the organizer app (white cards, NC blue,
  red reserved for recording state).
- **Live transcript**: visible by default (collapsible), and consecutive
  captions from the same speaker flow together as one paragraph with a
  "Speaker N" label — a new bubble starts only when the speaker changes
  (Deepgram live diarization).
- **One-tap start for independent assemblies**: mic check, round choice and a
  single red "Start recording" button on one screen — the READY step now
  exists only in orchestrated mode (where it arms the table).
- **Recording screen**: the round question stays pinned at the top (tap to
  expand), and the technical status shrank to a discreet one-line strip
  (tap for details). Alerts (storage error / offline) remain full-size.
- **Recovery dead-end fixed**: when the server definitively no longer has a
  recovered recording (deleted/reset assembly), the phone now explains it and
  offers "Download audio file" and an explicitly confirmed "Delete local
  audio" instead of retrying forever.
- **QR sheet**: tidier copy-link row under each code (truncated URL + copy
  icon). Organizer app no longer hides its bottom edge behind mobile browser
  toolbars (dynamic viewport height).
- Round-end auto-stop on phones now reacts within ~5 s; app version 0.2.0
  busts cached recorder assets so phones pick the new UI up immediately.

### Recording modes, summaries, model split, auto-QR — 2026-08-24

- **Two recording modes per assembly** (wizard choice): *Orchestrated* — tables
  arm with one READY tap, then recording starts and stops automatically for
  everyone when the facilitator starts/ends the round (15 s cancellable
  finish countdown; Live tab shows "N/M tables ready" with a warning before
  starting incomplete); phones can no longer record outside an active round.
  *Independent* — each table records the shared questions on its own schedule
  (even days apart); cross-table clustering re-runs incrementally as tables
  complete. Verified live end-to-end (arm → auto-start → auto-finish → sync).
- **AI summaries everywhere**: every analyzed table now gets a mandatory
  neutral 2–4 sentence summary (plus findings when substantive), rounds get a
  cross-table overview; both appear in the Analysis tab and reports, clearly
  labeled AI-generated. test4's small-talk session now reads "The table
  participants introduced themselves…" instead of an empty tab.
- **Separate live/final transcription models** for both Deepgram and Mistral
  in Settings (legacy single-model settings still honored).
- **QR codes generated by default**: creating an assembly generates all table
  codes immediately and lands on the printable sheet.

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
