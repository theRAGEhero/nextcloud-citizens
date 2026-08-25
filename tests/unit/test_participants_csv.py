# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from fastapi import HTTPException

from citizens.services.assemblies import parse_participants_csv


def test_minimal_csv_labels_only():
    parsed = parse_participants_csv("label,name,email\nP001,,\nP002,,\n")
    assert [p.label for p in parsed] == ["P001", "P002"]
    assert all(p.name == "" and p.email == "" for p in parsed)


def test_csv_with_names_and_whitespace():
    parsed = parse_participants_csv("label, name ,email\n P001 , Ada , ada@example.org \n")
    assert parsed[0].label == "P001"
    assert parsed[0].name == "Ada"
    assert parsed[0].email == "ada@example.org"


def test_csv_skips_blank_label_rows():
    parsed = parse_participants_csv("label,name,email\nP001,,\n,,\nP002,,\n")
    assert [p.label for p in parsed] == ["P001", "P002"]


def test_csv_without_label_header_rejected():
    with pytest.raises(HTTPException) as exc:
        parse_participants_csv("id,name\n1,Ada\n")
    assert exc.value.status_code == 422


def test_empty_csv_rejected():
    with pytest.raises(HTTPException) as exc:
        parse_participants_csv("label,name,email\n")
    assert exc.value.status_code == 422
