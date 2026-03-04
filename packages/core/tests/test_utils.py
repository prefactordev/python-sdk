"""Tests for prefactor_core utility functions."""

from __future__ import annotations

import uuid

import pytest
from prefactor_core.utils import generate_idempotency_key, validate_idempotency_key


class TestGenerateIdempotencyKey:
    def test_returns_valid_uuid(self):
        key = generate_idempotency_key()
        parsed = uuid.UUID(key)
        assert parsed.version == 4

    def test_max_length(self):
        key = generate_idempotency_key()
        assert len(key) <= 64

    def test_unique_per_call(self):
        keys = {generate_idempotency_key() for _ in range(10)}
        assert len(keys) == 10


class TestValidateIdempotencyKey:
    def test_accepts_valid_key(self):
        key = "a" * 64
        assert validate_idempotency_key(key) == key

    def test_accepts_short_key(self):
        key = "abc"
        assert validate_idempotency_key(key) == key

    def test_rejects_oversized_key(self):
        key = "a" * 65
        with pytest.raises(ValueError, match="64 characters"):
            validate_idempotency_key(key)

    def test_accepts_uuid_key(self):
        key = str(uuid.uuid4())
        assert validate_idempotency_key(key) == key
