"""
Core auto_p2oasys function and result types.

Implements expert-first routing with fast pipeline fallback:
1. Check for expert score in p2oasys_score_lookup.sqlite
2. If expert exists and force_fast=False: return expert result
3. Otherwise: run fast pipeline, possibly returning expert+fast mode
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .evidence import Evidence
from .source_report import SourceReport, AdapterStatus
from .cas_utils import normalize_cas, validate_cas_checksum, format_cas_display


class P2OASysMode(Enum):
    """Mode of P2OASys result."""

    EXPERT = "expert"
    FAST = "fast"
    EXPERT_PLUS_FAST = "expert+fast"
    NOT_FOUND = "not_found"


@dataclass
class CategoryScore:
    """Score for a single P2OASys category."""

    name: str
    score: float | None
    status: str = "scored"
    subcategories: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "status": self.status,
            "subcategories": self.subcategories,
        }


@dataclass
class P2OASysResult:
    """
    Complete result from auto_p2oasys.

    Contains expert scores (if available), fast pipeline scores (if run),
    evidence records, and the source report showing adapter status.
    """

    cas: str
    mode: P2OASysMode
    overall: float | None = None
    expert_overall: float | None = None
    fast_overall: float | None = None
    categories: dict[str, CategoryScore] = field(default_factory=dict)
    expert_categories: dict[str, float | None] = field(default_factory=dict)
    fast_categories: dict[str, float | None] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
    source_report: SourceReport = field(default_factory=SourceReport)
    name: str | None = None
    provenance: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cas": self.cas,
            "mode": self.mode.value,
            "overall": self.overall,
            "expert_overall": self.expert_overall,
            "fast_overall": self.fast_overall,
            "categories": {k: v.to_dict() for k, v in self.categories.items()},
            "expert_categories": self.expert_categories,
            "fast_categories": self.fast_categories,
            "evidence": [e.to_dict() for e in self.evidence],
            "trace": self.trace,
            "source_report": self.source_report.to_dict(),
            "name": self.name,
            "provenance": self.provenance,
            "error": self.error,
        }

    def print_summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"=== P2OASys Result: {self.cas} ===",
            f"Mode: {self.mode.value}",
            f"Overall: {self._format_score(self.overall)}",
        ]

        if self.mode == P2OASysMode.EXPERT_PLUS_FAST:
            lines.append(f"  Expert: {self._format_score(self.expert_overall)}")
            lines.append(f"  Fast:   {self._format_score(self.fast_overall)}")

        if self.name:
            lines.append(f"Name: {self.name}")

        lines.append("")
        lines.append("Categories:")
        for name, cat in self.categories.items():
            lines.append(f"  {name}: {self._format_score(cat.score)} ({cat.status})")

        lines.append("")
        lines.append(f"Evidence count: {len(self.evidence)}")

        return "\n".join(lines)

    @staticmethod
    def _format_score(score: float | None) -> str:
        if score is None:
            return "-"
        if abs(score - round(score)) < 1e-9:
            return str(int(round(score)))
        return f"{score:.1f}"


def _lookup_expert(cas: str) -> dict | None:
    """Look up expert score from p2oasys_score_lookup.sqlite."""
    from packages.p2oasys_core.lookup import (
        lookup_sqlite_expert,
        format_cas_display as fmt_cas,
    )

    try:
        result = lookup_sqlite_expert(cas)
        if result and result.get("overall") is not None:
            return result
    except Exception:
        pass

    return None


def _lookup_expert_subcategories(cas: str) -> dict | None:
    """Look up expert subcategory scores from sqlite."""
    from packages.p2oasys_core.lookup import _sqlite_row, SQLITE_EXPERT_AUTO6

    try:
        row = _sqlite_row(cas)
        if row and row.get("has_expert"):
            cats = {}
            cat_names = [
                "Acute Human Effects",
                "Chronic Human Effects",
                "Ecological Hazards",
                "Environmental Fate & Transport",
                "Atmospheric Hazard",
                "Physical Properties",
            ]
            for col, cat_name in zip(SQLITE_EXPERT_AUTO6, cat_names):
                val = row.get(col)
                if val is not None:
                    try:
                        cats[cat_name] = float(val)
                    except (TypeError, ValueError):
                        pass
            return {
                "categories": cats,
                "name": row.get("name_expert"),
            }
    except Exception:
        pass

    return None


def _run_fast_pipeline(
    cas: str,
    sds_pdf: Path | None = None,
    report: SourceReport | None = None,
) -> tuple[dict | None, list[Evidence], dict]:
    """
    Run the fast P2OASys pipeline.

    Gathers evidence from available adapters, builds hazard_data,
    and runs the P2OASys scorer.

    Returns:
        (scores_dict, evidence_list, trace_dict) or (None, [], {}) on failure
    """
    if report is None:
        report = SourceReport()

    evidence: list[Evidence] = []
    start_time = time.monotonic()

    from .pipeline import gather_evidence, build_hazard_data, run_scorer

    evidence = gather_evidence(cas, sds_pdf=sds_pdf, report=report)
    hazard_data = build_hazard_data(cas, evidence)
    scores, trace = run_scorer(hazard_data)

    report.pipeline_duration_ms = (time.monotonic() - start_time) * 1000
    return scores, evidence, trace


def auto_p2oasys(
    cas: str | None = None,
    sds_pdf: Path | None = None,
    *,
    force_fast: bool = False,
) -> P2OASysResult:
    """
    Compute P2OASys scores with expert-first routing.

    Routing rule:
    1. Normalize CAS (validate check digit). If SDS given, parse for CAS first.
    2. If CAS has expert row in database AND force_fast=False:
       - Return expert result (mode=expert) with provenance
    3. If CAS not in database OR force_fast=True:
       - Run fast P2OASys (mode=fast)
       - If expert exists and fast was forced: return both (mode=expert+fast)

    Args:
        cas: CAS registry number (optional if sds_pdf provided)
        sds_pdf: Path to SDS PDF file for CAS extraction and data
        force_fast: Force fast pipeline even if expert exists

    Returns:
        P2OASysResult with scores, evidence, and source report
    """
    report = SourceReport()
    start_time = time.monotonic()

    if sds_pdf is not None:
        from .adapters.sds import extract_cas_from_sds

        sds_cas_list = extract_cas_from_sds(sds_pdf, report=report)
        if sds_cas_list and not cas:
            cas = sds_cas_list[0]
            if len(sds_cas_list) > 1:
                report.add(
                    "sds_multicomponent",
                    AdapterStatus.RAN,
                    f"Mixture with {len(sds_cas_list)} CAS numbers",
                )

    if not cas:
        return P2OASysResult(
            cas="",
            mode=P2OASysMode.NOT_FOUND,
            error="No CAS number provided or found in SDS",
            source_report=report,
        )

    norm_cas = normalize_cas(cas)
    display_cas = format_cas_display(norm_cas)
    report.cas = display_cas
    report.mode = "checking"

    if not validate_cas_checksum(norm_cas):
        report.add("cas_validation", AdapterStatus.ERROR, "Invalid CAS check digit")

    expert_result = _lookup_expert(display_cas)
    expert_subcats = _lookup_expert_subcategories(display_cas)

    if expert_result and not force_fast:
        report.mode = "expert"
        report.add(
            "expert_lookup",
            AdapterStatus.RAN,
            evidence_count=1,
        )

        cats = {}
        if expert_subcats:
            for cat_name, score in expert_subcats.get("categories", {}).items():
                cats[cat_name] = CategoryScore(
                    name=cat_name,
                    score=score,
                    status="expert",
                )

        report.pipeline_duration_ms = (time.monotonic() - start_time) * 1000

        return P2OASysResult(
            cas=display_cas,
            mode=P2OASysMode.EXPERT,
            overall=expert_result["overall"],
            expert_overall=expert_result["overall"],
            categories=cats,
            expert_categories={k: v.score for k, v in cats.items()},
            name=expert_result.get("name") or (
                expert_subcats.get("name") if expert_subcats else None
            ),
            provenance=expert_result.get("detail", "expert"),
            source_report=report,
        )

    fast_scores, evidence, trace = _run_fast_pipeline(
        display_cas, sds_pdf=sds_pdf, report=report
    )

    if expert_result and force_fast:
        report.mode = "expert+fast"

        cats = {}
        if expert_subcats:
            for cat_name, score in expert_subcats.get("categories", {}).items():
                cats[cat_name] = CategoryScore(
                    name=cat_name,
                    score=score,
                    status="expert",
                )

        fast_cats = {}
        fast_overall = None
        if fast_scores:
            auto6_scores = []
            for cat_name, cat_data in fast_scores.items():
                if cat_name in ("Process Factors", "Life Cycle Factors"):
                    continue
                if isinstance(cat_data, dict) and "_category_max" in cat_data:
                    score = cat_data["_category_max"]
                    fast_cats[cat_name] = score
                    if score is not None:
                        auto6_scores.append(score)
            if auto6_scores:
                fast_overall = max(auto6_scores)

        return P2OASysResult(
            cas=display_cas,
            mode=P2OASysMode.EXPERT_PLUS_FAST,
            overall=expert_result["overall"],
            expert_overall=expert_result["overall"],
            fast_overall=fast_overall,
            categories=cats,
            expert_categories={k: v.score for k, v in cats.items()},
            fast_categories=fast_cats,
            evidence=evidence,
            trace=trace,
            name=expert_result.get("name") or (
                expert_subcats.get("name") if expert_subcats else None
            ),
            provenance="expert+fast",
            source_report=report,
        )

    report.mode = "fast"

    if fast_scores is None:
        return P2OASysResult(
            cas=display_cas,
            mode=P2OASysMode.NOT_FOUND,
            error="Fast pipeline failed to produce scores",
            evidence=evidence,
            trace=trace,
            source_report=report,
        )

    cats = {}
    auto6_scores = []
    for cat_name, cat_data in fast_scores.items():
        if cat_name in ("Process Factors", "Life Cycle Factors"):
            continue
        if isinstance(cat_data, dict) and "_category_max" in cat_data:
            score = cat_data["_category_max"]
            cats[cat_name] = CategoryScore(
                name=cat_name,
                score=score,
                status=trace.get("category_status", {}).get(cat_name, "scored"),
                subcategories={
                    k: v for k, v in cat_data.items() if not k.startswith("_")
                },
            )
            if score is not None:
                auto6_scores.append(score)

    overall = max(auto6_scores) if auto6_scores else None

    return P2OASysResult(
        cas=display_cas,
        mode=P2OASysMode.FAST,
        overall=overall,
        fast_overall=overall,
        categories=cats,
        fast_categories={k: v.score for k, v in cats.items()},
        evidence=evidence,
        trace=trace,
        source_report=report,
    )
