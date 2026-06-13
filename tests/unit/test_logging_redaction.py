"""Secret-redaction tests for the structured logger (FR-031; secrets never logged)."""

from __future__ import annotations

import json
import logging

from evidence_monitor.observability.logging import (
    JsonFormatter,
    redact,
    register_secret,
)


def test_redacts_provider_key_shapes():
    assert "sk-" not in redact("token sk-abcDEF0123456789ghijkl")
    assert "AIza" not in redact("key AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    assert "REDACTED" in redact("Authorization: Bearer abcdef0123456789ABCDEF")


def test_redacts_sensitive_key_value_pairs():
    out = redact("ANTHROPIC_API_KEY=super-secret-value-123")
    assert "super-secret-value-123" not in out
    assert "REDACTED" in out


def test_redacts_registered_exact_secret():
    register_secret("my-exact-credential")
    assert "my-exact-credential" not in redact("leaked my-exact-credential here")


def test_redacts_nested_context_structures():
    payload = {"api_key": "sk-abcDEF0123456789ghijkl", "nested": ["Bearer abcdef0123456789xyz"]}
    scrubbed = redact(payload)
    assert "sk-abcDEF0123456789ghijkl" not in json.dumps(scrubbed)
    assert "abcdef0123456789xyz" not in json.dumps(scrubbed)


def test_json_formatter_emits_redacted_single_line_json():
    record = logging.LogRecord(
        name="evidence_monitor",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connecting with sk-abcDEF0123456789ghijkl",
        args=(),
        exc_info=None,
    )
    rendered = JsonFormatter().format(record)
    parsed = json.loads(rendered)  # valid JSON
    assert "sk-abcDEF0123456789ghijkl" not in rendered
    assert parsed["level"] == "INFO"
    assert "REDACTED" in parsed["message"]
