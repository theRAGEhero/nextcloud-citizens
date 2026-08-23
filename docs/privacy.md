# Privacy & data handling

Audio recordings and transcripts of assembly discussions are sensitive data.
This document grows with the implementation; the rules below are binding from
Milestone 0 on.

## Data locations

- **Everything** Citizens stores lives under the ExApp's persistent storage
  (`APP_PERSISTENT_STORAGE`, the `citizens_data` docker volume in dev).
- Citizens never reads or writes Nextcloud user files (no Files integration in
  V1 by design).

## Standing rules (from the brief, §28, §43, §52)

- API keys are stored server-side only (sensitive Nextcloud AppConfig from
  Milestone 4); they never reach a browser, a QR code, a REST response, or a
  log line. UIs only ever see `configured: true` plus a short key hint.
- Recorder QR tokens are long random secrets; only their SHA-256 hash is
  stored server-side. Tokens are revocable and regenerable.
- Logs never contain audio, transcript content, API keys, or bearer/QR
  secrets. A redaction processor (`citizens/logging_setup.py`) scrubs
  sensitive keys from every event as defense in depth.
- Raw-audio retention is admin-configurable (delete after transcription /
  7 days / 30 days / indefinite); deletion runs as a durable job and is
  audit-logged (what, when, which assembly/recording, which policy) without
  logging content.
- Participants can be fully pseudonymous (`P001`…): names and emails are
  optional everywhere. Diarization produces `SPEAKER_NN` labels only — no
  voice biometrics, no automatic real-name attribution.
- Before recording starts, the recorder shows a consent/information screen
  naming the STT provider and the configured retention period.
- AI findings are drafts until a human approves them; the original AI text is
  preserved for audit alongside any human edit.

## Threat notes

- Public recorder endpoints (Milestone 2) are token-scoped (assembly + table +
  rounds), rate-limited, and never grant organizer/admin capability.
- Path traversal: all storage paths are built from server-generated UUIDs,
  never from client-supplied names.
- Upload integrity: every chunk is SHA-256-verified before acknowledgment.
