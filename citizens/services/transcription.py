"""Final (batch) transcription: dispatch to the configured provider and store
the normalized transcript (brief §30–§33)."""

import json

from sqlalchemy.orm import Session

from citizens.config import get_settings
from citizens.db.models import Assembly, Recording, Transcript, TranscriptSegment, TranscriptWord
from citizens.logging_setup import get_logger
from citizens.providers.transcription import deepgram as deepgram_provider
from citizens.providers.transcription import mistral as mistral_provider
from citizens.providers.transcription.base import NormalizedTranscript, TranscriptionError
from citizens.services import provider_config

log = get_logger(__name__)


def batch_transcription_ready(store: provider_config.ConfigStore) -> bool:
    if provider_config.get_setting(store, "stt_batch_enabled") != "1":
        return False
    provider = provider_config.get_setting(store, "stt_provider")
    key_name = "deepgram_api_key" if provider == "deepgram" else "mistral_api_key"
    return bool(store.get_value(key_name))


def transcribe_recording(
    session: Session, store: provider_config.ConfigStore, recording: Recording
) -> Transcript:
    settings = get_settings()
    audio_path = settings.app_persistent_storage / recording.canonical_audio_path
    if not recording.canonical_audio_path or not audio_path.exists():
        raise TranscriptionError("Canonical audio file is missing", permanent=True)

    assembly = session.get(Assembly, recording.assembly_id)
    language = assembly.language if assembly else ""
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
