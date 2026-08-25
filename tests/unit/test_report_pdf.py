# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""PDF rendering: full report with findings and evidence (regression for the
fpdf2 multi_cell cursor bug that only bit consecutive text blocks)."""

from citizens.services.report_pdf import render_pdf

REPORT = {
    "assembly": {
        "name": "Bologna Mobility Assembly",
        "description": "Citywide conversation on how people move.",
        "language": "en",
        "participants": 48,
        "expected_participants": 50,
        "tables": 10,
    },
    "method": "In-person citizens' assembly with one recording phone per table.",
    "methodology_note": "AI was used to assist transcription and analysis.",
    "rounds": [
        {
            "position": 1,
            "title": "R1",
            "question": "What mobility problems do people experience?",
            "summary": "Tables focused on bus frequency and bike safety.",
            "cross_table": [
                {
                    "type": "proposal",
                    "title": "Extend evening bus service",
                    "summary": "Multiple tables proposed later buses on weekends.",
                    "is_draft": False,
                    "mentioned_table_count": 4,
                    "evidence": [
                        {"speaker": "SPEAKER_01", "timestamp": "02:14",
                         "text": "The last bus leaves too early."},
                    ],
                },
                {
                    "type": "concern",
                    "title": "Unsafe bike lanes",
                    "summary": "Draft concern awaiting review.",
                    "is_draft": True,
                    "mentioned_table_count": None,
                    "evidence": [],
                },
            ],
            "tables": [
                {
                    "table_number": 1,
                    "summary": "The table discussed commuting pain points.",
                    "findings": [
                        {
                            "type": "new_idea",
                            "title": "Cargo-bike sharing",
                            "summary": "A shared cargo-bike fleet for families.",
                            "is_draft": False,
                            "mentioned_table_count": None,
                            "evidence": [
                                {"speaker": "SPEAKER_02", "timestamp": "11:02",
                                 "text": "Perché non biciclette da carico — “cargo bike”?"},
                            ],
                        }
                    ],
                },
            ],
        },
        {
            "position": 2,
            "title": "R2",
            "question": "",
            "summary": "",
            "cross_table": [],
            "tables": [],
        },
    ],
}


def test_render_pdf_with_findings_and_unicode():
    pdf = render_pdf(REPORT)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


def test_render_pdf_without_logo_matches_magic(tmp_path):
    missing_logo = tmp_path / "nope.png"
    assert render_pdf(REPORT, missing_logo).startswith(b"%PDF")
