# SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
# SPDX-License-Identifier: AGPL-3.0-or-later
from citizens.security.recorder_tokens import generate_token, hash_token


def test_tokens_are_long_and_unique():
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 40 for t in tokens)  # 32 bytes urlsafe-encoded


def test_hash_is_stable_sha256_hex():
    token = "some-token"
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert hash_token(token) != hash_token(token + "x")
    assert token not in hash_token(token)
