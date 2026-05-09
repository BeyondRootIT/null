"""Typed exceptions distinguishing transient (retry-eligible) from permanent failures."""

from __future__ import annotations


class CTIError(Exception):
    """Root of all framework errors."""


class TransientError(CTIError):
    """Network blip, 5xx, timeout — retry with backoff."""


class RateLimited(TransientError):
    """Upstream told us to slow down; honour `retry_after` if set."""

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentError(CTIError):
    """4xx (auth, not-found, bad-request), parse error, contract violation — DLQ."""


class CircuitOpen(TransientError):
    """Per-source circuit breaker is open; skip this attempt."""


class PluginError(CTIError):
    """Generic plugin failure; subclasses below for specifics."""


class PluginConfigError(PluginError, PermanentError):
    """Plugin received invalid config — does not retry."""


class PluginLoadError(PluginError):
    """Failure during entry-point discovery or instantiation."""


class EgressBlocked(PermanentError):
    """SSRF guard rejected the URL."""


class TLPViolation(PermanentError):
    """Publisher received an indicator with TLP it cannot handle."""


class WatermarkConflict(CTIError):
    """Two workers tried to advance the same source's watermark concurrently."""
