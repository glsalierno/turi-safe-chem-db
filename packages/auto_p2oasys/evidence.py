"""
Evidence record for P2OASys data sources.

Each Evidence instance represents one measured or predicted value from a single
source, with full provenance for audit trails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Evidence:
    """
    Single evidence record for P2OASys scoring.

    Attributes:
        cas: CAS registry number (normalized, e.g., "67-64-1")
        endpoint: Hazard endpoint name (e.g., "oral_ld50", "flash_point", "gwp100")
        value: Numeric or string value
        unit: Unit of measurement (e.g., "mg/kg", "°C", "mmHg")
        qualifier: Value qualifier ("<", ">", "≈", "ca.", None for exact)
        source: Data source name (e.g., "PubChem", "ToxValDB", "OPERA")
        predicted: True if value is predicted/modeled, False if measured
        reliability: Reliability score or category (source-specific)
        reference: Citation, study ID, or source document
        retrieved_at: Timestamp when data was retrieved
        section: SDS section reference (e.g., "Section 9.1") when from SDS
        raw_text: Original text before parsing (for audit)
    """

    cas: str
    endpoint: str
    value: float | str | None
    unit: str | None = None
    qualifier: str | None = None
    source: str = "unknown"
    predicted: bool = False
    reliability: str | None = None
    reference: str | None = None
    retrieved_at: datetime | None = field(default=None)
    section: str | None = None
    raw_text: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cas": self.cas,
            "endpoint": self.endpoint,
            "value": self.value,
            "unit": self.unit,
            "qualifier": self.qualifier,
            "source": self.source,
            "predicted": self.predicted,
            "reliability": self.reliability,
            "reference": self.reference,
            "retrieved_at": (
                self.retrieved_at.isoformat() if self.retrieved_at else None
            ),
            "section": self.section,
            "raw_text": self.raw_text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        """Create from dictionary."""
        retrieved_at = d.get("retrieved_at")
        if isinstance(retrieved_at, str):
            retrieved_at = datetime.fromisoformat(retrieved_at)
        return cls(
            cas=d["cas"],
            endpoint=d["endpoint"],
            value=d.get("value"),
            unit=d.get("unit"),
            qualifier=d.get("qualifier"),
            source=d.get("source", "unknown"),
            predicted=d.get("predicted", False),
            reliability=d.get("reliability"),
            reference=d.get("reference"),
            retrieved_at=retrieved_at,
            section=d.get("section"),
            raw_text=d.get("raw_text"),
        )

    def __str__(self) -> str:
        parts = [f"{self.endpoint}={self.value}"]
        if self.unit:
            parts.append(self.unit)
        if self.qualifier:
            parts.insert(0, self.qualifier)
        if self.predicted:
            parts.append("(predicted)")
        parts.append(f"[{self.source}]")
        return " ".join(parts)
