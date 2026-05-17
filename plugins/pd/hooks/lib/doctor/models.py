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
    # Feature 116 FR-1 / AC-1.x: closed-set severity rollup aggregated across
    # all CheckResult.issues. default_factory keeps existing call sites green.
    severity_summary: dict[str, int] = field(
        default_factory=lambda: {"error": 0, "warning": 0, "info": 0}
    )
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)


@dataclass
class FixResult:
    """Result of applying (or skipping) a single fix."""

    issue: Issue
    applied: bool
    action: str
    classification: str  # "safe" | "manual"

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)


@dataclass
class FixReport:
    """Aggregate report from fix application."""

    fixed_count: int
    skipped_count: int
    failed_count: int
    results: list[FixResult]
    elapsed_ms: int

    def to_dict(self) -> dict:
        """Serialize to a plain dict (None -> JSON null)."""
        return asdict(self)
