# Nextcloud Citizens

A Nextcloud [AppAPI ExApp](https://docs.nextcloud.com/server/latest/developer_manual/exapp_development/index.html)
for running **physical, in-person citizens' assemblies**.

An organization installs Nextcloud Citizens on its own Nextcloud, creates an
assembly, places one ordinary phone at each discussion table, safely records the
conversations even with unstable connectivity, transcribes them, and obtains
evidence-linked AI analysis — reviewed and approved by a human before anything
becomes a finding.

```text
50 citizens → 10 tables → 1 phone per table
                              │
              records locally, uploads when it can
                              │
                     Nextcloud Citizens
                              │
        batch transcription + diarization (Mistral / Deepgram)
                              │
            per-table analysis → cross-table synthesis
                              │
                        human review
                              │
                           report
```

## Principles

1. **Offline-first recording** — the network is never required to preserve a
   discussion. Audio is chunked into IndexedDB on the phone first; upload is
   asynchronous, idempotent, and checksum-verified.
2. **Final transcript beats live transcript** — live captions are provisional;
   the canonical record is batch-transcribed from the complete audio.
3. **AI must be auditable** — every finding links to transcript segments with
   speaker, timestamps, and original text. No evidence → invalid finding.
4. **AI output is a draft** — findings require explicit human approval.
5. **Small, reliable V1** — reliability over feature count.

## Status

Early development. Current phase: **Phase 0 / Milestone 0** (environment,
safety, ExApp skeleton). See `docs/` and `CHANGELOG.md`.

## Requirements

- Nextcloud ≥ 32 with AppAPI
- A valid HTTPS domain (mobile browsers require it for microphone access)
- API keys for speech-to-text (Mistral or Deepgram) and analysis
  (Mistral by default; any OpenAI-compatible endpoint such as Ollama Cloud works)

## Repository documents

- `docs/development-environment.md` — the development server inventory
- `docs/architecture.md` — application architecture (grows with the code)
- `docs/testing.md` — testing strategy and how to run tests
- `docs/privacy.md` — data handling, retention, consent

## License

AGPL-3.0-or-later (aligned with the Nextcloud ecosystem).
