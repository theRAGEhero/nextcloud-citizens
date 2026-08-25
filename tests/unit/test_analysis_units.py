# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from pydantic import ValidationError

from citizens.domain.analysis_schemas import TableAnalysis
from citizens.providers.analysis.openai_compat import _extract_json
from citizens.services.analysis import TABLE_SYSTEM, build_system_prompt, coalesce_segments


class Seg:
    def __init__(self, id, speaker, start, end, text):
        self.id = id
        self.speaker_label = speaker
        self.start_seconds = start
        self.end_seconds = end
        self.text = text


def test_coalesce_merges_same_speaker_fragments():
    segments = [
        Seg("a", "SPEAKER_01", 0.0, 1.0, "So"),
        Seg("b", "SPEAKER_01", 1.2, 2.0, "my name is"),
        Seg("c", "SPEAKER_01", 2.3, 3.0, "Giancarlo,"),
        Seg("d", "SPEAKER_02", 3.4, 4.0, "Nice to meet you."),
        Seg("e", "SPEAKER_01", 10.0, 11.0, "Later remark."),  # big gap → new block
    ]
    blocks = coalesce_segments(segments)
    assert len(blocks) == 3
    assert blocks[0]["ids"] == ["a", "b", "c"]
    assert blocks[0]["text"] == "So my name is Giancarlo,"
    assert blocks[1]["speaker"] == "SPEAKER_02"
    assert blocks[2]["ids"] == ["e"]


def test_extract_json_handles_fences_and_prose():
    assert _extract_json('```json\n{"findings": []}\n```') == {"findings": []}
    assert _extract_json('Here you go: {"findings": []} hope that helps') == {"findings": []}
    with pytest.raises(ValueError):
        _extract_json("no json here")


def test_table_schema_requires_evidence():
    with pytest.raises(ValidationError):
        TableAnalysis.model_validate(
            {"summary": "A table discussion about buses.",
             "findings": [{"type": "proposal", "title": "Better buses", "summary": "x" * 5,
                           "evidence_segment_ids": []}]}
        )
    valid = TableAnalysis.model_validate(
        {"summary": "A table discussion about buses.",
         "findings": [{"type": "proposal", "title": "Better buses", "summary": "Extend service.",
                       "evidence_segment_ids": ["seg-1"]}]}
    )
    assert valid.findings[0].type == "proposal"


def test_table_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        TableAnalysis.model_validate(
            {"summary": "A table discussion about something.",
             "findings": [{"type": "vibe", "title": "ttt", "summary": "sss",
                           "evidence_segment_ids": ["seg-1"]}]}
        )


def test_table_schema_requires_summary():
    with pytest.raises(ValidationError):
        TableAnalysis.model_validate({"findings": []})


class _Store:
    def __init__(self, extra):
        self._extra = extra

    def get_value(self, key):
        return {"analysis_extra_instructions": self._extra}.get(key)


def test_extra_instructions_appended_not_substituted():
    prompt = build_system_prompt(TABLE_SYSTEM, "it", _Store("Focus on housing."))
    assert "Write everything in it." in prompt  # built-in rules intact
    assert prompt.rstrip().endswith("Focus on housing.")
    assert "must never override" in prompt


def test_no_extra_instructions_keeps_prompt_unchanged():
    assert build_system_prompt(TABLE_SYSTEM, "en", _Store("")) == TABLE_SYSTEM.format(language="en")


def test_assembly_instructions_appended_after_global():
    prompt = build_system_prompt(
        TABLE_SYSTEM, "en", _Store("Global tone."), assembly_instructions="PUMS = mobility plan."
    )
    assert "Write everything in en." in prompt
    assert prompt.index("Global tone.") < prompt.index("PUMS = mobility plan.")
    assert "specific to THIS assembly" in prompt
