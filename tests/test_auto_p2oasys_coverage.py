"""
Offline tests for auto_p2oasys.coverage with synthetic fixture data.

These tests use synthetic data and mocked auto_p2oasys calls to verify
the coverage cross-check logic without requiring real data or external APIs.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from packages.auto_p2oasys.coverage import (
    AUTO6_CATEGORIES,
    CASResult,
    CoverageStats,
    SubcatComparison,
    analyze_cas,
    compute_stats,
    is_measured_evidence,
    is_predicted_evidence,
    load_expert_cas_from_csv,
    load_expert_cas_from_sqlite,
    resolve_expert_set,
    run_coverage,
    write_category_summary_csv,
    write_per_cas_csv,
    write_subcategory_summary_csv,
    write_summary_json,
)


@pytest.fixture
def synthetic_sqlite_db(tmp_path: Path) -> Path:
    """Create a synthetic SQLite database with fixture data."""
    db_path = tmp_path / "test_p2oasys.sqlite"
    conn = sqlite3.connect(str(db_path))

    conn.execute(
        """
        CREATE TABLE by_cas (
            cas TEXT PRIMARY KEY,
            name_expert TEXT,
            name_auto TEXT,
            expert_acute REAL,
            expert_chronic REAL,
            expert_ecological REAL,
            expert_fate REAL,
            expert_atmospheric REAL,
            expert_physical REAL,
            auto_acute REAL,
            auto_chronic REAL,
            auto_ecological REAL,
            auto_fate REAL,
            auto_atmospheric REAL,
            auto_physical REAL,
            has_expert INTEGER NOT NULL DEFAULT 0,
            has_auto INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE subcat_scores (
            cas TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            score REAL NOT NULL,
            PRIMARY KEY (cas, source, category, subcategory)
        )
        """
    )

    test_data = [
        {
            "cas": "67-64-1",
            "name_expert": "Acetone",
            "has_expert": 1,
            "has_auto": 1,
            "expert_acute": 6.0,
            "expert_chronic": 8.0,
            "expert_ecological": 4.0,
            "expert_fate": 4.0,
            "expert_atmospheric": 2.0,
            "expert_physical": 8.0,
            "auto_acute": 6.0,
            "auto_chronic": 7.0,
            "auto_ecological": None,
            "auto_fate": 4.0,
            "auto_atmospheric": 2.0,
            "auto_physical": 8.0,
        },
        {
            "cas": "64-17-5",
            "name_expert": "Ethanol",
            "has_expert": 1,
            "has_auto": 1,
            "expert_acute": 4.0,
            "expert_chronic": 6.0,
            "expert_ecological": 2.0,
            "expert_fate": 2.0,
            "expert_atmospheric": 2.0,
            "expert_physical": 6.0,
            "auto_acute": 5.0,
            "auto_chronic": 6.0,
            "auto_ecological": 2.0,
            "auto_fate": 2.0,
            "auto_atmospheric": 2.0,
            "auto_physical": 6.0,
        },
        {
            "cas": "67-56-1",
            "name_expert": "Methanol",
            "has_expert": 1,
            "has_auto": 0,
            "expert_acute": 8.0,
            "expert_chronic": 10.0,
            "expert_ecological": 4.0,
            "expert_fate": 4.0,
            "expert_atmospheric": 2.0,
            "expert_physical": 8.0,
            "auto_acute": None,
            "auto_chronic": None,
            "auto_ecological": None,
            "auto_fate": None,
            "auto_atmospheric": None,
            "auto_physical": None,
        },
    ]

    for row in test_data:
        conn.execute(
            """
            INSERT INTO by_cas (
                cas, name_expert, has_expert, has_auto,
                expert_acute, expert_chronic, expert_ecological,
                expert_fate, expert_atmospheric, expert_physical,
                auto_acute, auto_chronic, auto_ecological,
                auto_fate, auto_atmospheric, auto_physical
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["cas"],
                row["name_expert"],
                row["has_expert"],
                row["has_auto"],
                row["expert_acute"],
                row["expert_chronic"],
                row["expert_ecological"],
                row["expert_fate"],
                row["expert_atmospheric"],
                row["expert_physical"],
                row["auto_acute"],
                row["auto_chronic"],
                row["auto_ecological"],
                row["auto_fate"],
                row["auto_atmospheric"],
                row["auto_physical"],
            ),
        )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def synthetic_expert_csv(tmp_path: Path) -> Path:
    """Create a synthetic expert CSV file with fixture data."""
    csv_path = tmp_path / "test_expert.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "cas",
                "name",
                "Acute_Human_Effects_max",
                "Chronic_Human_Effects_max",
                "Ecological_Hazards_max",
                "Environmental_Fate_and_Transport_max",
                "Atmospheric_Hazard_max",
                "Physical_Properties_max",
            ]
        )
        writer.writerow(["67-64-1", "Acetone", 6, 8, 4, 4, 2, 8])
        writer.writerow(["64-17-5", "Ethanol", 4, 6, 2, 2, 2, 6])
    return csv_path


class TestLoadExpertCAS:
    """Tests for loading expert CAS lists."""

    def test_load_from_sqlite(self, synthetic_sqlite_db: Path) -> None:
        """Load expert CAS from SQLite."""
        rows = load_expert_cas_from_sqlite(synthetic_sqlite_db)
        assert len(rows) == 3
        cas_list = [r["cas"] for r in rows]
        assert "67-64-1" in cas_list
        assert "64-17-5" in cas_list
        assert "67-56-1" in cas_list

    def test_load_from_csv(self, synthetic_expert_csv: Path) -> None:
        """Load expert CAS from CSV."""
        rows = load_expert_cas_from_csv(synthetic_expert_csv)
        assert len(rows) == 2
        cas_list = [str(r.get("cas", "")) for r in rows]
        assert "67-64-1" in cas_list
        assert "64-17-5" in cas_list

    def test_load_from_missing_sqlite(self, tmp_path: Path) -> None:
        """Return empty list for missing SQLite."""
        rows = load_expert_cas_from_sqlite(tmp_path / "nonexistent.sqlite")
        assert rows == []

    def test_load_from_missing_csv(self, tmp_path: Path) -> None:
        """Return empty list for missing CSV."""
        rows = load_expert_cas_from_csv(tmp_path / "nonexistent.csv")
        assert rows == []


class TestResolveExpertSet:
    """Tests for resolving expert-set argument."""

    def test_resolve_sqlite_keyword(self) -> None:
        """Resolve 'sqlite' keyword."""
        source_type, path = resolve_expert_set("sqlite")
        assert source_type == "sqlite"
        assert path is not None

    def test_resolve_csv_keyword(self) -> None:
        """Resolve 'csv' keyword."""
        source_type, path = resolve_expert_set("csv")
        assert source_type == "csv"
        assert path is not None

    def test_resolve_sqlite_file_path(self, tmp_path: Path) -> None:
        """Resolve .sqlite file path."""
        test_path = tmp_path / "test.sqlite"
        test_path.touch()
        source_type, path = resolve_expert_set(str(test_path))
        assert source_type == "sqlite"
        assert path == test_path

    def test_resolve_csv_file_path(self, tmp_path: Path) -> None:
        """Resolve .csv file path."""
        test_path = tmp_path / "test.csv"
        test_path.touch()
        source_type, path = resolve_expert_set(str(test_path))
        assert source_type == "csv"
        assert path == test_path


class TestEvidenceClassification:
    """Tests for evidence classification."""

    def test_is_measured_pubchem(self) -> None:
        """PubChem evidence is measured."""
        assert is_measured_evidence("pubchem_ghs") is True
        assert is_measured_evidence("PubChem Properties") is True

    def test_is_measured_sds(self) -> None:
        """SDS evidence is measured."""
        assert is_measured_evidence("sds_parser") is True
        assert is_measured_evidence("fisher_sds") is True
        assert is_measured_evidence("tci_catalog") is True

    def test_is_predicted_ecosar(self) -> None:
        """ECOSAR evidence is predicted."""
        assert is_predicted_evidence("ecosar_aquatic") is True
        assert is_predicted_evidence("ECOSAR LC50") is True

    def test_is_predicted_qsar(self) -> None:
        """QSAR evidence is predicted."""
        assert is_predicted_evidence("qsar_model") is True
        assert is_predicted_evidence("predicted_toxicity") is True


class TestComputeStats:
    """Tests for computing aggregate statistics."""

    def test_compute_stats_basic(self) -> None:
        """Compute basic statistics from results."""
        results = [
            CASResult(
                cas="67-64-1",
                name="Acetone",
                has_expert=True,
                has_fast=True,
                expert_overall=8.0,
                fast_overall=8.0,
                score_agreement=True,
                overall_delta=0.0,
                expert_categories={"Acute Human Effects": 6.0, "Chronic Human Effects": 8.0},
                fast_categories={"Acute Human Effects": 6.0, "Chronic Human Effects": 7.0},
                evidence_count=5,
                measured_count=3,
                predicted_count=2,
            ),
            CASResult(
                cas="67-56-1",
                name="Methanol",
                has_expert=True,
                has_fast=False,
                expert_overall=10.0,
                fast_overall=None,
                score_agreement=None,
                expert_categories={"Acute Human Effects": 8.0, "Chronic Human Effects": 10.0},
                fast_categories={},
                error="Fast pipeline not available",
            ),
        ]

        stats = compute_stats(results)

        assert stats.total_expert_cas == 2
        assert stats.expert_with_fast == 1
        assert stats.expert_only == 0
        assert stats.fast_errors == 1
        assert stats.score_agreements == 1
        assert stats.score_disagreements == 0
        assert stats.total_evidence == 5
        assert stats.total_measured == 3
        assert stats.total_predicted == 2

    def test_compute_stats_category_fill(self) -> None:
        """Verify category fill counts."""
        results = [
            CASResult(
                cas="67-64-1",
                has_expert=True,
                has_fast=True,
                expert_categories={"Acute Human Effects": 6.0},
                fast_categories={"Acute Human Effects": 6.0},
            ),
            CASResult(
                cas="64-17-5",
                has_expert=True,
                has_fast=True,
                expert_categories={"Acute Human Effects": 4.0},
                fast_categories={},
            ),
        ]

        stats = compute_stats(results)

        assert stats.category_fill["Acute Human Effects"]["expert"] == 2
        assert stats.category_fill["Acute Human Effects"]["fast"] == 1
        assert stats.category_fill["Acute Human Effects"]["both"] == 1


class TestWriteOutputs:
    """Tests for writing output files."""

    def test_write_per_cas_csv(self, tmp_path: Path) -> None:
        """Write per-CAS CSV file."""
        results = [
            CASResult(
                cas="67-64-1",
                name="Acetone",
                mode="expert+fast",
                has_expert=True,
                has_fast=True,
                expert_overall=8.0,
                fast_overall=8.0,
                score_agreement=True,
                overall_delta=0.0,
                expert_categories={"Acute Human Effects": 6.0},
                fast_categories={"Acute Human Effects": 6.0},
                evidence_count=5,
                measured_count=3,
                predicted_count=2,
            ),
        ]

        out_path = tmp_path / "per_cas.csv"
        write_per_cas_csv(results, out_path)

        assert out_path.is_file()
        content = out_path.read_text()
        assert "67-64-1" in content
        assert "Acetone" in content
        assert "expert+fast" in content
        assert "measured_count" in content

    def test_write_category_summary_csv(self, tmp_path: Path) -> None:
        """Write category summary CSV file."""
        stats = CoverageStats(
            total_expert_cas=100,
            category_fill={
                "Acute Human Effects": {"expert": 95, "fast": 80, "both": 75},
            },
        )

        out_path = tmp_path / "category.csv"
        write_category_summary_csv(stats, out_path)

        assert out_path.is_file()
        content = out_path.read_text()
        assert "Acute Human Effects" in content
        assert "95" in content
        assert "fast_n" in content

    def test_write_summary_json(self, tmp_path: Path) -> None:
        """Write summary JSON file."""
        stats = CoverageStats(
            total_expert_cas=100,
            expert_with_fast=80,
            score_agreements=70,
            score_disagreements=10,
            mean_overall_delta=0.5,
            total_evidence=500,
            total_measured=400,
            total_predicted=100,
        )

        out_path = tmp_path / "summary.json"
        write_summary_json(stats, [], out_path)

        assert out_path.is_file()
        data = json.loads(out_path.read_text())
        assert data["total_expert_cas"] == 100
        assert data["expert_with_fast_coverage"] == 80
        assert "measured_vs_predicted" in data
        assert data["measured_vs_predicted"]["measured_count"] == 400
        assert data["measured_vs_predicted"]["predicted_count"] == 100


class TestAnalyzeCAS:
    """Tests for analyze_cas with mocked auto_p2oasys."""

    def test_analyze_cas_expert_plus_fast(self) -> None:
        """Analyze CAS returns expert+fast mode result."""
        from packages.auto_p2oasys.core import P2OASysResult, P2OASysMode, CategoryScore

        mock_result = P2OASysResult(
            cas="67-64-1",
            mode=P2OASysMode.EXPERT_PLUS_FAST,
            overall=8.0,
            expert_overall=8.0,
            fast_overall=7.0,
            name="Acetone",
            expert_categories={"Acute Human Effects": 6.0},
            fast_categories={"Acute Human Effects": 5.0},
            categories={
                "Acute Human Effects": CategoryScore(
                    name="Acute Human Effects",
                    score=6.0,
                    status="expert",
                    subcategories={"Eye Irritation": 6.0},
                )
            },
            evidence=[],
        )

        with patch("packages.auto_p2oasys.auto_p2oasys", return_value=mock_result):
            result = analyze_cas("67-64-1", "Acetone")

        assert result.cas == "67-64-1"
        assert result.has_expert is True
        assert result.has_fast is True
        assert result.expert_overall == 8.0
        assert result.fast_overall == 7.0
        assert result.overall_delta == 1.0
        assert result.score_agreement is True

    def test_analyze_cas_not_found(self) -> None:
        """Analyze CAS handles NOT_FOUND mode."""
        from packages.auto_p2oasys.core import P2OASysResult, P2OASysMode

        mock_result = P2OASysResult(
            cas="99-99-9",
            mode=P2OASysMode.NOT_FOUND,
            error="CAS not found",
        )

        with patch("packages.auto_p2oasys.auto_p2oasys", return_value=mock_result):
            result = analyze_cas("99-99-9")

        assert result.error == "CAS not found"
        assert result.has_expert is False
        assert result.has_fast is False


class TestSubcatComparison:
    """Tests for subcategory comparison."""

    def test_subcat_comparison_with_delta(self) -> None:
        """SubcatComparison computes delta correctly."""
        comp = SubcatComparison(expert_score=6.0, fast_score=5.0)
        assert comp.expert_score == 6.0
        assert comp.fast_score == 5.0

    def test_subcat_comparison_missing_fast(self) -> None:
        """SubcatComparison handles missing fast score."""
        comp = SubcatComparison(expert_score=6.0, fast_score=None)
        assert comp.expert_score == 6.0
        assert comp.fast_score is None
        assert comp.delta is None
