"""
Source report for auto_p2oasys runs.

Tracks which adapters ran, which were skipped/disabled, and why.
Printed at the top of every result for transparency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AdapterStatus(Enum):
    """Status of an adapter in the pipeline."""

    RAN = "ran"
    SKIPPED = "skipped"
    DISABLED = "disabled"
    ERROR = "error"
    NOT_AVAILABLE = "not_available"
    NO_DATA = "no_data"


@dataclass
class AdapterResult:
    """Result from a single adapter."""

    name: str
    status: AdapterStatus
    reason: str | None = None
    evidence_count: int = 0
    duration_ms: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "evidence_count": self.evidence_count,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SourceReport:
    """
    Report of all adapters used in an auto_p2oasys run.

    Tracks which adapters were tried, succeeded, failed, or skipped,
    along with reasons for each status.
    """

    adapters: list[AdapterResult] = field(default_factory=list)
    mode: str = "unknown"
    cas: str | None = None
    total_evidence: int = 0
    pipeline_duration_ms: float | None = None

    def add(
        self,
        name: str,
        status: AdapterStatus,
        reason: str | None = None,
        evidence_count: int = 0,
        duration_ms: float | None = None,
    ) -> None:
        """Add an adapter result to the report."""
        self.adapters.append(
            AdapterResult(
                name=name,
                status=status,
                reason=reason,
                evidence_count=evidence_count,
                duration_ms=duration_ms,
            )
        )
        if status == AdapterStatus.RAN:
            self.total_evidence += evidence_count

    @property
    def ran(self) -> list[AdapterResult]:
        """Adapters that ran successfully."""
        return [a for a in self.adapters if a.status == AdapterStatus.RAN]

    @property
    def skipped(self) -> list[AdapterResult]:
        """Adapters that were skipped."""
        return [a for a in self.adapters if a.status == AdapterStatus.SKIPPED]

    @property
    def disabled(self) -> list[AdapterResult]:
        """Adapters that are disabled."""
        return [a for a in self.adapters if a.status == AdapterStatus.DISABLED]

    @property
    def errors(self) -> list[AdapterResult]:
        """Adapters that had errors."""
        return [a for a in self.adapters if a.status == AdapterStatus.ERROR]

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "cas": self.cas,
            "total_evidence": self.total_evidence,
            "pipeline_duration_ms": self.pipeline_duration_ms,
            "adapters": [a.to_dict() for a in self.adapters],
        }

    def print_summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"=== Source Report for {self.cas or 'unknown'} (mode: {self.mode}) ===",
        ]

        if self.ran:
            lines.append(f"  Ran ({len(self.ran)}):")
            for a in self.ran:
                lines.append(f"    - {a.name}: {a.evidence_count} evidence items")

        if self.skipped:
            lines.append(f"  Skipped ({len(self.skipped)}):")
            for a in self.skipped:
                reason = f" ({a.reason})" if a.reason else ""
                lines.append(f"    - {a.name}{reason}")

        if self.disabled:
            lines.append(f"  Disabled ({len(self.disabled)}):")
            for a in self.disabled:
                reason = f" ({a.reason})" if a.reason else ""
                lines.append(f"    - {a.name}{reason}")

        if self.errors:
            lines.append(f"  Errors ({len(self.errors)}):")
            for a in self.errors:
                reason = f": {a.reason}" if a.reason else ""
                lines.append(f"    - {a.name}{reason}")

        lines.append(f"  Total evidence: {self.total_evidence}")

        if self.pipeline_duration_ms is not None:
            lines.append(f"  Pipeline duration: {self.pipeline_duration_ms:.1f}ms")

        return "\n".join(lines)
