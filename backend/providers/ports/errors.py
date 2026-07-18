"""The common provider error taxonomy (doc 06).

Adapters map every vendor-specific failure onto exactly one of these, so callers
handle the taxonomy and never a vendor's own error types. This keeps vendor
knowledge quarantined at L1 (ADR-0005).
"""
from __future__ import annotations


class ProviderError(Exception):
    """Base class for every error a provider adapter may raise."""


class NotAvailable(ProviderError):
    """The requested instrument or data is not available from this provider."""


class MalformedPayload(ProviderError):
    """The vendor payload did not satisfy the adapter's declared raw contract."""


class RateLimited(ProviderError):
    """The provider rejected the request due to rate/quota limits."""


class AuthFailed(ProviderError):
    """Authentication/authorization with the provider failed."""


class TransientError(ProviderError):
    """A transient failure (network/5xx); the request may succeed on retry."""
