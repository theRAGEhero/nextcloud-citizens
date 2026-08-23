# Architecture

Grows alongside the code; currently covers Milestone 0.

## Overall shape

```text
                      NEXTCLOUD (32)
                           │  AppAPI (manual-install daemon, dev)
                           │  proxies /apps/app_api/proxy/citizens/* → http://nc_app_citizens:23000
                           ▼
             ┌───────────────────────────────┐
             │       NEXTCLOUD CITIZENS      │
             │  FastAPI (citizens/main.py)   │
             │  SQLite in /data (WAL, FK)    │
             │  structlog → console + jsonl  │
             └───────────────────────────────┘
```

- The ExApp is a single FastAPI process. Nextcloud authenticates every proxied
  request with the shared `APP_SECRET`; `AppAPIAuthMiddleware` (nc_py_api)
  validates it globally.
- Route access control lives in the AppAPI registration (`scripts/register.sh`
  for dev, `appinfo/info.xml` for packaged installs): `js/css/img` + `/api/v1/*`
  are USER-level, `/api/v1/admin/*` is ADMIN. Public recorder routes arrive in
  Milestone 2 with `access_level` PUBLIC. Hard-won AppAPI facts (verified
  against AppAPI 32 source and live behaviour):
  - `--json-info` registration takes **numeric** access levels (PUBLIC=0,
    USER=1, ADMIN=2); info.xml takes the string names.
  - Route URL regexes are matched against the path **without** a leading slash
    and are wrapped in `/.../i` delimiters server-side — patterns must look
    like `^js\/.*`, never `^/js/.*` (a leading `/` breaks the pattern).
  - The proxy checks `$userId` from the **Nextcloud session** — basic auth is
    not processed on the proxy controller; browsers work, bare curl does not.
  - The browser-facing proxy URL on this server is
    `/index.php/apps/app_api/proxy/citizens/<route>` — there is no `/exapps/`
    web-server rewrite here, so client code derives its base URL from its own
    `<script src>` (see `js/citizens-main.js`).
- WebSockets do not traverse this server's nginx vhost, so all live features
  use HTTP polling / short posts by design (see
  `development-environment.md`).

## Modules (Milestone 0)

| Module | Responsibility |
|---|---|
| `citizens/main.py` | app factory, lifespan (storage → logging → DB → migrations → AppAPI handlers), request-log middleware, `enabled_handler` registering the top-menu entry + SPA script |
| `citizens/config.py` | pydantic-settings over the AppAPI environment variables |
| `citizens/logging_setup.py` | structlog: contextvar correlation IDs, secret redaction, pretty dev console + rotating `logs/citizens.jsonl` |
| `citizens/storage/paths.py` | persistent-storage layout (`recordings/`, `assembled/`, `transcripts/`, `exports/`, `temp/`, `logs/`, `citizens.db`) |
| `citizens/db/` | SQLAlchemy 2 (sync engine — endpoints doing DB work are `def`, FastAPI runs them in its threadpool), SQLite pragmas, Alembic migrations run at startup |
| `citizens/services/audit.py` | audit-event writing |
| `citizens/api/system.py` | `/api/v1/health` |
| `js/citizens-main.js` | Milestone 0 shell injected into AppAPI's embedded top-menu page (`<div id="content">`); replaced by the Vue organizer SPA in Milestone 1 |

## UI design system

The organizer SPA follows Nextcloud's native app-shell pattern: a 300 px
app-navigation sidebar (assembly list with status dots, "+ New assembly",
admin-only Settings pinned at the bottom) beside a scrollable content pane
(assembly header + icon tabs: Overview, Rounds, Participants, Tables, QR
codes, Live). On ≤768 px the sidebar becomes an overlay drawer. Shared atoms
live in `frontend/src/components/ui/` (SvgIcon via `@mdi/js`, CzButton,
CzStatusPill, CzEmptyState, CzSkeleton, CzConfirm for destructive actions,
CzToast). All styles are ID-scoped tokens over NC CSS variables (see the
"hard-won facts" above for why), adapting automatically to NC's dark theme.
The recorder keeps its own dark glanceable design (hero table number, pulsing
record ring, iconized checklist, caption bubbles).

## UI delivery model

The organizer UI is not an iframe: `enabled_handler` registers a top-menu
entry plus a script (`nc.ui.resources.set_script("top_menu", "citizens",
"js/citizens-main")`). Nextcloud's embedded template
(`/apps/app_api/embedded/citizens/citizens`) loads that script from
`/index.php/apps/app_api/proxy/citizens/js/citizens-main.js` and the script
renders into `#content`. nc_py_api auto-mounts the `js/`, `css/`, `img/`,
`l10n/` folders from the process working directory.

The recorder UI (Milestone 2) will be a separate, dependency-light bundle
served on PUBLIC routes — phones load it straight from
`/exapps/citizens/recorder/...` with no Nextcloud chrome.

## Recording pipeline (Milestones 2–3)

```text
PHONE (recorder SPA, PUBLIC routes)          SERVER
MediaRecorder (~10 s timeslices)
  └► IndexedDB FIRST (chunk + sha256)  ──►  POST chunks/{seq} (octet-stream,
       └► uploader: sequential, exp.         X-Chunk-SHA256 verified,
          backoff, online-event kick,        idempotent on rec+seq+hash)
          manual retry                          └► AudioChunk row + file
finish → complete(total)              ──►  gap check → resend missing → job
                                            ASSEMBLE_AUDIO: concat → ffprobe
                                            → ffmpeg remux → sha256 →
                                            AUDIO_READY (state machine §24)
heartbeat every 20 s                  ──►  recorder_sessions.last_status_*
client log ring (IndexedDB)           ──►  logs/devices/<session>.jsonl
```

- Reload/crash recovery: on launch the recorder scans IndexedDB for
  unfinished recordings and resumes synchronization (mic session itself
  cannot survive a reload; every persisted chunk does).
- SQLite concurrency: transactions run `BEGIN IMMEDIATE` (writers queue on
  `busy_timeout` instead of failing on read→write lock upgrades) — required
  for ~10 devices uploading simultaneously (§56 Test F).
- Facilitator "Live" tab polls `/rounds/{id}/monitor`: device connectivity
  (heartbeat age), chunk upload progress, and "local recording safe" only
  when a recent heartbeat reports healthy storage.
- Round start/end is organizer-controlled; recorders only ever poll — the
  server never reaches into a phone. In orchestrated mode the phone *arms*
  itself on an explicit READY tap (that tap is the user gesture + consent and
  opens the mic), then polling turns facilitator start/end into auto
  start/finish. In independent mode the tap starts recording directly.

## Recording modes (per assembly)

- **Orchestrated** (live event, the default): tables tap READY once and sit
  on an Armed screen sending `armed` heartbeats. The Live tab shows
  "N/M tables ready" and warns (never blocks) when starting incomplete.
  Facilitator Start → armed phones begin recording together; the server
  rejects `recorder/start` for rounds that are not ACTIVE (409). Facilitator
  End → phones show a 15 s cancellable "finishing" countdown ("Keep talking"
  aborts), then finish and synchronize; the done screen re-arms for the next
  round automatically.
- **Independent** (async): rounds act as shared questions, not timed windows.
  Each table records any un-recorded round on its own schedule (days apart if
  needed); Start/End round controls are hidden on the Live tab. Cross-table
  clustering re-runs incrementally as each table's analysis lands (draft
  round findings are replaced, reviewed ones kept).
- Both modes: one healthy recording per table+round; the recorder locks after
  finish so no stray recordings appear.

## Analysis output

- Every analyzed table stores a mandatory neutral AI `analysis_summary`
  (2–4 sentences, assembly language) alongside findings; rounds store a
  cross-table summary. Summaries always render in the Analysis tab and
  reports labeled as AI-generated, so a session with no substantive findings
  (small talk) still reads as "analyzed", not as an empty failure state.
  Findings remain evidence-linked drafts until human review.
- STT models are configured separately for live captions and final
  transcription per provider (Deepgram live/batch, Mistral batch; Mistral
  live reserved for Voxtral Realtime).

## Dev workflow

```text
edit code → uvicorn auto-reloads (source bind-mounted) → refresh browser
```

- `make up` — build image, start `nc_app_citizens` (512 MB memory cap) on the
  Nextcloud docker network.
- `make register` — register manual-install daemon + ExApp (idempotent).
- `make logs`, `make test`, `make lint`, `make dev-reset` (Citizens data only).
- The AppAPI shared secret is generated once into `.app_secret` (gitignored).
