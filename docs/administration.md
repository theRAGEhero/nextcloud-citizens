# Administration guide

Citizens is an **ExApp**: Nextcloud runs it as a container next to itself and
talks to it through the AppAPI proxy. This guide covers installing it, giving it
the API keys it needs, and understanding what leaves your server.

## 1. Requirements

* Nextcloud **32 or newer**
* The **AppAPI** app enabled, with a deploy daemon configured
  (Settings → Administration → External Apps → Deploy daemons)
* Docker available to that daemon, with enough disk for audio:
  roughly **10 MB per table per hour** of recording, plus the assembled copy

## 2. Install

Settings → Administration → **External Apps** → find *Citizens* → **Install**.
AppAPI pulls `ghcr.io/theragehero/citizens`, starts it, and enables it. The app
then appears in the top menu for every user.

Nothing else is required to start: without API keys the app records and stores
audio, but performs no transcription and no analysis.

## 3. Configure transcription and analysis

Open **Citizens → Settings** (visible to Nextcloud administrators only).

**Transcription.** Four engines are supported:

| Engine | Runs | Speaker labels | Live captions |
|---|---|---|---|
| Deepgram | hosted | yes | native streaming, with speakers |
| Mistral (Voxtral) | hosted | on final transcripts | Voxtral Realtime, no speakers while live |
| Whisper (OpenAI-compatible) | hosted **or your own server** | only on diarizing servers | rolling 20-second windows; a line may be revised |
| Vosk | **your own server**, offline | no | native streaming, no punctuation |

Any endpoint speaking the OpenAI audio API works for Whisper (OpenAI itself,
Speaches, whisper.cpp, LocalAI, vLLM, WhisperX). Deepgram's caption endpoint is
configurable too, so a self-hosted server speaking the same streaming protocol —
WhisperLiveKit, for example — can drive captions without leaving your network.

Paste the API key for hosted engines, or the endpoint URL for self-hosted ones,
and use the *Test* button before saving — it checks what you typed.

Choosing **Whisper against your own server** or **Vosk** means recordings are
never sent to a third party. A Whisper server that adds diarization (WhisperX-
based, or OpenAI's `gpt-4o-transcribe-diarize` model) keeps speaker labels;
plain Whisper and Vosk produce transcripts without them, and reports then omit
the "who said it" attribution while keeping every quote and finding.

### Running Vosk yourself

Vosk needs **a separate model per language**, but one server can hold several:
each recording names the model it wants, and the language you set on an assembly
chooses it.

`scripts/vosk-up.sh` starts a server with Italian and English small models and
prints the values to paste into Settings. Adding a language is one more entry in
the script's model table plus one row in Settings — no second container. Models
are downloaded once to `/srv/citizens-vosk/models`, and `scripts/vosk-down.sh`
stops the server (`--purge` also removes the models).

In Settings → Speech to text → Vosk, set the server URL and one row per
language, mapping a language code to the model path *on the server*:

```
Server URL          ws://citizens-vosk:2700
it                  /models/it
en                  /models/en
```

A language with no row uses whatever model the server started with, so it still
transcribes rather than failing.

Two things worth knowing. The server must be reachable **from the app
container**, so use the container name rather than `localhost` — `localhost`
would point the app at itself. And Vosk has no authentication, so never publish
its port beyond `127.0.0.1`; the app reaches it over the shared Docker network.

The script runs a lightly patched `asr_server.py` (in `scripts/vosk/`): upstream
switches models process-wide and reloads from disk on every connection, which
would let two assemblies in different languages take each other's model. The
patch makes the choice per-connection and caches loaded models. Both small
models together use about 340 MB.

**AI analysis.** Any OpenAI-compatible endpoint works: Mistral, OpenAI, or a
self-hosted server such as Ollama or vLLM. Set the base URL, model and key.
Choosing a self-hosted endpoint keeps transcripts on your own infrastructure.

**Organisation.** Your organisation name and logo appear on the PDF reports.

**Additional analysis instructions** apply to every assembly on the instance;
each assembly can add its own instructions on top (topic context, glossary).

API keys are stored in Nextcloud's app configuration marked *sensitive*. They
are never sent to browsers, never written to logs, and never reach the phones.

## 4. What leaves the server

| Step | What is sent | Where | When |
|---|---|---|---|
| Transcription | the assembled audio of one recording | Deepgram, Mistral, or the Whisper endpoint you configure (which can be your own server) | only after an admin configures an engine |
| Live captions | ~10-second audio chunks during recording | whichever engine is configured — none if it is self-hosted | only if live captions are enabled |
| Analysis | transcript text (never audio) | the configured endpoint — may be your own server | only after an admin configures it |

Audio, transcripts, findings and reports live in the app's own persistent
storage, never in users' Nextcloud files. See [privacy.md](privacy.md) for the
full data-handling note, and give participants a privacy notice before you
record them.

## 5. Data management

Each assembly has a **Files** tab listing every table's audio with its size and
duration. From there an organizer can download one table's audio, download all
of it, export the **whole session** as a portable archive (metadata, audio,
transcripts and report), or delete audio and transcripts — per table or for the
session — without deleting the assembly. Deleting an assembly deletes its
stored files too.

Automatic retention (scheduled deletion of audio some days after a session is
closed) is **not implemented yet** in this beta; deletion is manual for now.

## 6. Backups

The app keeps everything in the persistent volume AppAPI mounts at `/data`:
SQLite database, audio, transcripts and logs. Back that volume up together with
Nextcloud itself. The database is safe to copy while running (WAL mode), but a
snapshot taken while a recording is uploading may miss its most recent chunks.

## 7. Troubleshooting

**The app is not in the top menu.** Check External Apps shows it enabled, then
look at the container logs — the app logs `missing_environment` if AppAPI did
not pass `APP_SECRET` or `NEXTCLOUD_URL`.

**Phones show "Loading recorder…" forever.** Their QR codes were generated by an
older version of the app. Regenerate the codes from the QR tab.

**A phone cannot start recording.** In live (orchestrated) mode a round must be
started by the facilitator first; a closed session refuses new recordings.

**Transcription never happens.** Check Settings for a configured key and use
*Test*; the recording's state in the Files tab shows where it stopped.

Health endpoint: `GET /api/v1/health` through the proxy reports the database,
storage, free disk and any missing configuration.
