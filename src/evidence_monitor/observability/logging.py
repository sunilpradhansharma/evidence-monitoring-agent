"""Structured JSON logging with secret redaction (FR-031; secrets are never logged).

Every application event is emitted as a single-line JSON object with a timestamp, severity, and
arbitrary context fields. Before anything is written, the message and its context pass through
:func:`redact`, which masks secret-shaped strings (API keys, bearer tokens, ``key=value`` pairs
whose key looks sensitive) so a credential can never reach a log sink — even if it is accidentally
interpolated into a message.

Redaction is deliberately conservative-by-shape rather than relying on a registry: it catches
provider key formats and generic high-entropy tokens. Callers may additionally register exact
secret values (e.g. the loaded API keys) via :func:`register_secret`.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_REDACTED = "***REDACTED***"

# Secret-shaped token patterns. Ordered from most specific to most general.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),  # OpenAI / Anthropic style
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),  # Google API keys
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"),  # bearer tokens
    # key=value or key: value where the key name looks sensitive.
    re.compile(
        r"(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|credential)[A-Za-z0-9_]*)"
        r"\s*[=:]\s*\"?([^\s\"',]+)\"?"
    ),
]

# Exact secret values registered at runtime (e.g. resolved env credentials).
_REGISTERED_SECRETS: set[str] = set()

# Exact-secret registration ignores trivially short values: real API keys are long, and masking a
# 1–2 char string would scrub unrelated text everywhere it appears. Their *shapes* are still caught
# by the pattern rules above, so nothing key-shaped slips through.
_MIN_REGISTERED_SECRET_LEN = 8


def register_secret(value: str | None) -> None:
    """Register an exact secret string to be masked wherever it appears in a log.

    Values shorter than :data:`_MIN_REGISTERED_SECRET_LEN` are ignored to avoid over-redaction
    (real credentials are far longer; placeholder/test stubs are not worth masking by value).
    """
    if value and len(value) >= _MIN_REGISTERED_SECRET_LEN:
        _REGISTERED_SECRETS.add(value)


def redact(value: Any) -> Any:
    """Return ``value`` with secret-shaped substrings masked.

    Strings are scrubbed; dicts/lists/tuples are scrubbed recursively; other types are
    returned unchanged. Registered exact secrets are masked first.
    """
    if isinstance(value, str):
        out = value
        for secret in _REGISTERED_SECRETS:
            if secret:
                out = out.replace(secret, _REDACTED)
        for pattern in _PATTERNS:
            if pattern.groups >= 2:
                out = pattern.sub(lambda m: f"{m.group(1)}={_REDACTED}", out)
            else:
                out = pattern.sub(_REDACTED, out)
        return out
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    return value


class JsonFormatter(logging.Formatter):
    """Format a log record as a single line of redacted JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = redact(context)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class _RedactingFilter(logging.Filter):
    """Last line of defence: scrub the rendered message and args on every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(redact(a) for a in record.args)
        return True


def get_logger(name: str = "evidence_monitor", level: str = "INFO") -> logging.Logger:
    """Return a logger that emits redacted JSON to stderr (idempotent per name)."""
    logger = logging.getLogger(name)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(_RedactingFilter())
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: str, message: str, **context: Any) -> None:
    """Emit a structured event with arbitrary (redacted) context fields."""
    logger.log(logging.getLevelName(level.upper()), message, extra={"context": context})


__all__ = ["JsonFormatter", "get_logger", "log_event", "redact", "register_secret"]
