# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Final (batch) transcription: dispatch to the configured provider and store
the normalized transcript (brief §30–§33)."""

import json

from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import Assembly, Recording, Transcript, TranscriptSegment, TranscriptWord
from citizens.logging_setup import get_logger
from citizens.providers.transcription import deepgram as deepgram_provider
from citizens.providers.transcription import mistral as mistral_provider
from citizens.providers.transcription import vosk as vosk_provider
from citizens.providers.transcription import whisper as whisper_provider
from citizens.providers.transcription.base import NormalizedTranscript, TranscriptionError
from citizens.services import provider_config

log = get_logger(__name__)

# hosted providers authenticate with a key; self-hostable ones are reachable
# at a URL instead (a Whisper server may or may not require a key)
KEYED_PROVIDERS = ("deepgram", "mistral")
URL_PROVIDERS = {"whisper": "whisper_base_url", "vosk": "vosk_url"}


def batch_transcription_ready(store: provider_config.ConfigStore) -> bool:
    if provider_config.get_setting(store, "stt_batch_enabled") != "1":
        return False
    provider = provider_config.get_setting(store, "stt_provider")
    if provider in URL_PROVIDERS:
        return bool(provider_config.get_setting(store, URL_PROVIDERS[provider]))
    if provider in KEYED_PROVIDERS:
        return bool(store.get_value(f"{provider}_api_key"))
    return False


def transcribe_recording(
    session: Session, store: provider_config.ConfigStore, recording: Recording
) -> Transcript:
    settings = get_settings()
    audio_path = settings.app_persistent_storage / recording.canonical_audio_path
    if not recording.canonical_audio_path or not audio_path.exists():
        raise TranscriptionError("Canonical audio file is missing", permanent=True)

    assembly = session.get(Assembly, recording.assembly_id)
    language = assembly.language if assembly else ""
    # release the DB write lock BEFORE reading provider config — those reads
    # are OCS calls to Nextcloud, and a held job transaction 500s every API
    # request after busy_timeout (expire_on_commit=False keeps `recording` and
    # `assembly` usable afterwards)
    session.commit()
    provider = provider_config.get_setting(store, "stt_provider")

    log.info(
        "stt_started",
        recording_id=recording.id,
        provider=provider,
        size_bytes=audio_path.stat().st_size,
    )
    if provider == "deepgram":
        key = store.get_value("deepgram_api_key")
        if not key:
            raise TranscriptionError("No Deepgram API key configured", permanent=True)
        normalized = deepgram_provider.transcribe_file(
            key, audio_path, recording.mime_type, language,
            model=provider_config.get_setting(store, "deepgram_batch_model"),
        )
    elif provider == "mistral":
        key = store.get_value("mistral_api_key")
        if not key:
            raise TranscriptionError("No Mistral API key configured", permanent=True)
        normalized = mistral_provider.transcribe_file(
            key, audio_path, recording.mime_type, language,
            model=provider_config.get_setting(store, "mistral_batch_model"),
        )
    elif provider == "whisper":
        base_url = provider_config.get_setting(store, "whisper_base_url")
        if not base_url:
            raise TranscriptionError("No Whisper endpoint configured", permanent=True)
        normalized = whisper_provider.transcribe_file(
            # self-hosted servers usually need no key; hosted OpenAI does
            store.get_value("whisper_api_key") or "",
            audio_path, recording.mime_type, language,
            model=provider_config.get_setting(store, "whisper_batch_model"),
            base_url=base_url,
        )
    elif provider == "vosk":
        url = provider_config.get_setting(store, "vosk_url")
        if not url:
            raise TranscriptionError("No Vosk server URL configured", permanent=True)
        # one server can hold a model per language; pick this assembly's
        model = provider_config.vosk_model_for(store, language) or provider_config.get_setting(
            store, "vosk_batch_model"
        )
        log.info("vosk_model_selected", language=language, model=model or "(server default)")
        normalized = vosk_provider.transcribe_file(
            "", audio_path, recording.mime_type, language, model=model, base_url=url,
        )
    else:
        raise TranscriptionError(f"Unknown STT provider {provider}", permanent=True)

    transcript = store_transcript(session, recording, normalized)
    log.info(
        "stt_completed",
        recording_id=recording.id,
        provider=provider,
        segments=len(normalized.segments),
    )
    return transcript


def store_transcript(
    session: Session, recording: Recording, normalized: NormalizedTranscript
) -> Transcript:
    """Replace any existing transcript for this recording (retranscription)."""
    existing = session.query(Transcript).filter_by(recording_id=recording.id).one_or_none()
    if existing is not None:
        # the old segments cascade away, taking every finding's evidence links
        # with them (the new segments have new ids) — flag those findings so
        # reports do not silently show them without quotes
        from citizens.services.files import mark_evidence_removed

        mark_evidence_removed(session, existing)
        session.delete(existing)
        session.flush()

    settings = get_settings()
    raw_dir = settings.app_persistent_storage / "transcripts" / recording.assembly_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{recording.id}.raw.json"
    raw_path.write_text(json.dumps(normalized.raw))

    transcript = Transcript(
        recording_id=recording.id,
        provider=normalized.provider,
        model=normalized.model,
        language=normalized.language,
        raw_response_path=str(raw_path.relative_to(settings.app_persistent_storage)),
    )
    for index, segment in enumerate(normalized.segments):
        row = TranscriptSegment(
            sequence=index,
            speaker_label=segment.speaker,
            start_seconds=segment.start,
            end_seconds=segment.end,
            text=segment.text,
        )
        for word_index, word in enumerate(segment.words):
            row.words.append(
                TranscriptWord(
                    sequence=word_index,
                    text=word.text[:200],
                    start_seconds=word.start,
                    end_seconds=word.end,
                )
            )
        transcript.segments.append(row)
    session.add(transcript)
    session.flush()
    return transcript


def transcript_payload(transcript: Transcript) -> dict:
    return {
        "transcript_id": transcript.id,
        "recording_id": transcript.recording_id,
        "provider": transcript.provider,
        "model": transcript.model,
        "language": transcript.language,
        "segments": [
            {
                "id": segment.id,
                "speaker": segment.speaker_label,
                "start": segment.start_seconds,
                "end": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }
