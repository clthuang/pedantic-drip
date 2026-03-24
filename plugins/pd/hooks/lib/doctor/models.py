"""Data models for pd:doctor diagnostic reports."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Issue:
    """A single diagnostic issue found by a check."""

    check: str
    severity: str  # "error" | "warning" | "info"
    entity: str | None
    message: str
    fix_hint: str | None

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""

    name: str
    passed: bool
    issues: list[Issue]
    elapsed_ms: int
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)


@dataclass
class DiagnosticReport:
    """Aggregate report from all diagnostic checks."""

    healthy: bool
    checks: list[CheckResult]
    total_issues: int
    error_count: int
    warning_count: int
    elapsed_ms: int

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)
