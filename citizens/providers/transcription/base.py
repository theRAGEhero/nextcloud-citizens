# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transcription provider abstraction (brief §29, §32).

Provider adapters convert provider-specific responses into ONE normalized
structure; nothing outside this package sees provider JSON. Speaker labels
are canonical SPEAKER_01… in order of first appearance (§33).
"""

from dataclasses import dataclass, field


@dataclass
class NormalizedWord:
    text: str
    start: float
    end: float


@dataclass
class NormalizedSegment:
    speaker: str  # SPEAKER_01… or "" when the provider gave no diarization
    start: float
    end: float
    text: str
    words: list[NormalizedWord] = field(default_factory=list)


@dataclass
class NormalizedTranscript:
    provider: str
    model: str
    language: str
    segments: list[NormalizedSegment]
    raw: dict


class TranscriptionError(Exception):
    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class SpeakerLabeler:
    """Maps arbitrary provider speaker ids to SPEAKER_01… by first appearance."""

    def __init__(self):
        self._labels: dict[str, str] = {}

    def label(self, provider_speaker) -> str:
        if provider_speaker is None:
            return ""
        key = str(provider_speaker)
        if key not in self._labels:
            self._labels[key] = f"SPEAKER_{len(self._labels) + 1:02d}"
        return self._labels[key]
