"""
Offline tests for auto_p2oasys.coverage with synthetic fixture data.

These tests use synthetic data to verify the coverage cross-check logic
without requiring the real expert database or any external API calls.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from packages.auto_p2oasys.coverage import (
    AUTO6_CATEGORIES,
    CASResult,
    CoverageStats,
    analyze_cas,
    compute_stats,
    load_expert_cas_from_csv,
    load_expert_cas_from_sqlite,
    load_subcat_scores,
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

    subcat_data = [
        ("67-64-1", "expert", "Acute Human Effects", "Dermal Irritation", 4.0),
        ("67-64-1", "expert", "Acute Human Effects", "Eye Irritation", 6.0),
        ("67-64-1", "expert", "Chronic Human Effects", "Neurotoxicity", 8.0),
        ("67-64-1", "auto", "Acute Human Effects", "Dermal Irritation", 4.0),
        ("67-64-1", "auto", "Acute Human Effects", "Eye Irritation", 5.0),
        ("64-17-5", "expert", "Acute Human Effects", "Dermal Toxicity", 2.0),
        ("64-17-5", "auto", "Acute Human Effects", "Dermal Toxicity", 3.0),
    ]

    for cas, source, category, subcategory, score in subcat_data:
        conn.execute(
            """
            INSERT INTO subcat_scores (cas, source, category, subcategory, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cas, source, category, subcategory, score),
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


class TestAnalyzeCAS:
    """Tests for analyzing individual CAS entries."""

    def test_analyze_cas_with_both(self, synthetic_sqlite_db: Path) -> None:
        """Analyze CAS with both expert and auto scores."""
        row = {
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
        }
        result = analyze_cas(row, synthetic_sqlite_db, "sqlite")

        assert result.cas == "67-64-1"
        assert result.name == "Acetone"
        assert result.has_expert is True
        assert result.has_auto is True
        assert result.expert_overall == 8.0
        assert result.auto_overall == 8.0
        assert result.score_agreement is True
        assert result.overall_delta == 0.0

    def test_analyze_cas_expert_only(self, synthetic_sqlite_db: Path) -> None:
        """Analyze CAS with only expert scores."""
        row = {
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
        }
        result = analyze_cas(row, synthetic_sqlite_db, "sqlite")

        assert result.cas == "67-56-1"
        assert result.has_expert is True
        assert result.has_auto is False
        assert result.expert_overall == 10.0
        assert result.auto_overall is None
        assert result.score_agreement is None

    def test_analyze_cas_with_subcats(self, synthetic_sqlite_db: Path) -> None:
        """Verify subcategory scores are loaded."""
        row = {
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
        }
        result = analyze_cas(row, synthetic_sqlite_db, "sqlite")

        assert "Acute Human Effects" in result.expert_subcats
        assert "Dermal Irritation" in result.expert_subcats["Acute Human Effects"]
        assert result.expert_subcats["Acute Human Effects"]["Dermal Irritation"] == 4.0


class TestComputeStats:
    """Tests for computing aggregate statistics."""

    def test_compute_stats_basic(self) -> None:
        """Compute basic statistics from results."""
        results = [
            CASResult(
                cas="67-64-1",
                name="Acetone",
                has_expert=True,
                has_auto=True,
                expert_overall=8.0,
                auto_overall=8.0,
                score_agreement=True,
                overall_delta=0.0,
                expert_categories={"Acute Human Effects": 6.0, "Chronic Human Effects": 8.0},
                auto_categories={"Acute Human Effects": 6.0, "Chronic Human Effects": 7.0},
            ),
            CASResult(
                cas="67-56-1",
                name="Methanol",
                has_expert=True,
                has_auto=False,
                expert_overall=10.0,
                auto_overall=None,
                score_agreement=None,
                expert_categories={"Acute Human Effects": 8.0, "Chronic Human Effects": 10.0},
                auto_categories={},
            ),
        ]

        stats = compute_stats(results)

        assert stats.total_expert_cas == 2
        assert stats.expert_with_auto == 1
        assert stats.expert_only == 1
        assert stats.score_agreements == 1
        assert stats.score_disagreements == 0

    def test_compute_stats_category_fill(self) -> None:
        """Verify category fill counts."""
        results = [
            CASResult(
                cas="67-64-1",
                has_expert=True,
                has_auto=True,
                expert_categories={"Acute Human Effects": 6.0},
                auto_categories={"Acute Human Effects": 6.0},
            ),
            CASResult(
                cas="64-17-5",
                has_expert=True,
                has_auto=True,
                expert_categories={"Acute Human Effects": 4.0},
                auto_categories={},
            ),
        ]

        stats = compute_stats(results)

        assert stats.category_fill["Acute Human Effects"]["expert"] == 2
        assert stats.category_fill["Acute Human Effects"]["auto"] == 1
        assert stats.category_fill["Acute Human Effects"]["both"] == 1


class TestWriteOutputs:
    """Tests for writing output files."""

    def test_write_per_cas_csv(self, tmp_path: Path) -> None:
        """Write per-CAS CSV file."""
        results = [
            CASResult(
                cas="67-64-1",
                name="Acetone",
                has_expert=True,
                has_auto=True,
                expert_overall=8.0,
                auto_overall=8.0,
                score_agreement=True,
                overall_delta=0.0,
                source_type="sqlite",
                expert_categories={"Acute Human Effects": 6.0},
                auto_categories={"Acute Human Effects": 6.0},
            ),
        ]

        out_path = tmp_path / "per_cas.csv"
        write_per_cas_csv(results, out_path)

        assert out_path.is_file()
        content = out_path.read_text()
        assert "67-64-1" in content
        assert "Acetone" in content
        assert "8.0" in content

    def test_write_category_summary_csv(self, tmp_path: Path) -> None:
        """Write category summary CSV file."""
        stats = CoverageStats(
            total_expert_cas=100,
            category_fill={
                "Acute Human Effects": {"expert": 95, "auto": 80, "both": 75},
            },
        )

        out_path = tmp_path / "category.csv"
        write_category_summary_csv(stats, out_path)

        assert out_path.is_file()
        content = out_path.read_text()
        assert "Acute Human Effects" in content
        assert "95" in content

    def test_write_summary_json(self, tmp_path: Path) -> None:
        """Write summary JSON file."""
        stats = CoverageStats(
            total_expert_cas=100,
            expert_with_auto=80,
            score_agreements=70,
            score_disagreements=10,
            mean_overall_delta=0.5,
        )

        out_path = tmp_path / "summary.json"
        write_summary_json(stats, [], out_path)

        assert out_path.is_file()
        data = json.loads(out_path.read_text())
        assert data["total_expert_cas"] == 100
        assert data["expert_with_auto_coverage"] == 80


class TestRunCoverage:
    """Integration tests for run_coverage."""

    def test_run_coverage_sqlite(
        self, synthetic_sqlite_db: Path, tmp_path: Path
    ) -> None:
        """Run full coverage analysis with SQLite source."""
        out_dir = tmp_path / "output"

        exit_code = run_coverage(
            expert_set="sqlite",
            out_dir=out_dir,
            force_fast=True,
            db_path=synthetic_sqlite_db,
            resume=False,
        )

        assert exit_code == 0
        assert (out_dir / "coverage_per_cas.csv").is_file()
        assert (out_dir / "coverage_by_category.csv").is_file()
        assert (out_dir / "coverage_by_subcategory.csv").is_file()
        assert (out_dir / "coverage_summary.json").is_file()

        summary = json.loads((out_dir / "coverage_summary.json").read_text())
        assert summary["total_expert_cas"] == 3
        assert summary["expert_with_auto_coverage"] == 2

    def test_run_coverage_csv(
        self, synthetic_expert_csv: Path, synthetic_sqlite_db: Path, tmp_path: Path
    ) -> None:
        """Run full coverage analysis with CSV source."""
        out_dir = tmp_path / "output"

        exit_code = run_coverage(
            expert_set="csv",
            out_dir=out_dir,
            force_fast=True,
            db_path=synthetic_sqlite_db,
            csv_path=synthetic_expert_csv,
            resume=False,
        )

        assert exit_code == 0
        summary = json.loads((out_dir / "coverage_summary.json").read_text())
        assert summary["total_expert_cas"] == 2

    def test_run_coverage_resumable(
        self, synthetic_sqlite_db: Path, tmp_path: Path
    ) -> None:
        """Verify coverage analysis is resumable."""
        out_dir = tmp_path / "output"

        exit_code = run_coverage(
            expert_set="sqlite",
            out_dir=out_dir,
            force_fast=True,
            db_path=synthetic_sqlite_db,
            resume=False,
        )
        assert exit_code == 0

        progress_path = out_dir / "coverage_progress.json"
        assert progress_path.is_file()

        exit_code = run_coverage(
            expert_set="sqlite",
            out_dir=out_dir,
            force_fast=True,
            db_path=synthetic_sqlite_db,
            resume=True,
        )
        assert exit_code == 0

    def test_run_coverage_lock_file(
        self, synthetic_sqlite_db: Path, tmp_path: Path
    ) -> None:
        """Verify lock file is created and released."""
        out_dir = tmp_path / "output"
        lock_path = out_dir / "pubchem_batch.lock"

        exit_code = run_coverage(
            expert_set="sqlite",
            out_dir=out_dir,
            force_fast=True,
            db_path=synthetic_sqlite_db,
            resume=False,
        )
        assert exit_code == 0
        assert not lock_path.is_file()


class TestLoadSubcatScores:
    """Tests for loading subcategory scores."""

    def test_load_subcat_scores_expert(self, synthetic_sqlite_db: Path) -> None:
        """Load expert subcategory scores."""
        subcats = load_subcat_scores(synthetic_sqlite_db, "67-64-1", "expert")

        assert "Acute Human Effects" in subcats
        assert "Dermal Irritation" in subcats["Acute Human Effects"]
        assert subcats["Acute Human Effects"]["Dermal Irritation"] == 4.0

    def test_load_subcat_scores_auto(self, synthetic_sqlite_db: Path) -> None:
        """Load auto subcategory scores."""
        subcats = load_subcat_scores(synthetic_sqlite_db, "67-64-1", "auto")

        assert "Acute Human Effects" in subcats
        assert "Dermal Irritation" in subcats["Acute Human Effects"]
        assert subcats["Acute Human Effects"]["Dermal Irritation"] == 4.0

    def test_load_subcat_scores_missing_cas(self, synthetic_sqlite_db: Path) -> None:
        """Return empty dict for missing CAS."""
        subcats = load_subcat_scores(synthetic_sqlite_db, "99-99-9", "expert")
        assert subcats == {}
