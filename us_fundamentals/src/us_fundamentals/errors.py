"""Typed error taxonomy shared by every pipeline component.

The split that matters operationally is retryable versus terminal: a
retryable error means the same work item may succeed later without code or
data changes; a terminal error means it cannot, and the item needs a
classified state and human-visible diagnostics. No component may collapse
the two into a bare Exception.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base for all pipeline errors. Carries a stable machine category."""

    category: str = "pipeline_error"

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.context = context


class RetryableError(PipelineError):
    """The same work item may succeed on retry without intervention."""

    category = "retryable"


class TerminalError(PipelineError):
    """Retrying cannot help; the item needs a classified terminal state."""

    category = "terminal"


# -- Retryable ---------------------------------------------------------------


class TransientNetworkError(RetryableError):
    category = "retryable.network"


class RateLimitedError(RetryableError):
    category = "retryable.rate_limited"

    def __init__(
        self, message: str, retry_after_seconds: float | None = None, **context: object
    ) -> None:
        super().__init__(message, **context)
        self.retry_after_seconds = retry_after_seconds


class UpstreamUnavailableError(RetryableError):
    category = "retryable.upstream_unavailable"


# -- Terminal ----------------------------------------------------------------


class IntegrityError(TerminalError):
    """Stored evidence conflicts with newly observed bytes or hashes."""

    category = "terminal.integrity"


class ContractViolationError(TerminalError):
    """A schema, policy, or interface contract was violated."""

    category = "terminal.contract"


class MalformedInputError(TerminalError):
    """Upstream content is syntactically unusable and will not change."""

    category = "terminal.malformed_input"


class ConfigurationError(TerminalError):
    category = "terminal.configuration"
