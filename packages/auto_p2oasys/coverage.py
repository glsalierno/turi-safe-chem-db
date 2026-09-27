"""
Batch coverage cross-check for auto_p2oasys.

Usage:
    python -m packages.auto_p2oasys.coverage --expert-set <csv|sqlite> --out <dir>

Compares fast P2OASys coverage (auto) against expert P2OASys chemicals.
Throttle-safe, resumable, disk-cached; honors pubchem_batch.lock.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DATA_DIR = REPO_ROOT / "data"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.p2oasys_core.lookup import (
    AUTO6_MAX_COLS,
    SQLITE_AUTO_AUTO6,
    SQLITE_EXPERT_AUTO6,
    default_lookup_db_path,
    format_cas_display,
    load_expert_csv,
    max_of_values,
    normalize_cas,
)

LOCK_FILE = "pubchem_batch.lock"
PROGRESS_FILE = "coverage_progress.json"
MIN_INTERVAL_MS = 350

AUTO6_CATEGORIES = (
    "Acute Human Effects",
    "Chronic Human Effects",
    "Ecological Hazards",
    "Environmental Fate & Transport",
    "Atmospheric Hazard",
    "Physical Properties",
)

AUTO6_SQLITE_EXPERT_MAP = dict(zip(AUTO6_CATEGORIES, SQLITE_EXPERT_AUTO6))
AUTO6_SQLITE_AUTO_MAP = dict(zip(AUTO6_CATEGORIES, SQLITE_AUTO_AUTO6))


@dataclass
class CASResult:
    """Coverage result for a single CAS."""

    cas: str
    name: str = ""
    has_expert: bool = False
    has_auto: bool = False
    expert_overall: Optional[float] = None
    auto_overall: Optional[float] = None
    expert_categories: dict[str, Optional[float]] = field(default_factory=dict)
    auto_categories: dict[str, Optional[float]] = field(default_factory=dict)
    expert_subcats: dict[str, dict[str, float]] = field(default_factory=dict)
    auto_subcats: dict[str, dict[str, float]] = field(default_factory=dict)
    score_agreement: Optional[bool] = None
    overall_delta: Optional[float] = None
    source_type: str = "sqlite"


@dataclass
class CoverageStats:
    """Aggregate coverage statistics."""

    total_expert_cas: int = 0
    expert_with_auto: int = 0
    expert_only: int = 0
    category_fill: dict[str, dict[str, int]] = field(default_factory=dict)
    subcat_fill: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    score_agreements: int = 0
    score_disagreements: int = 0
    mean_overall_delta: float = 0.0
    measured_vs_predicted: dict[str, dict[str, int]] = field(default_factory=dict)


def acquire_lock(lock_path: Path, timeout_s: float = 300) -> bool:
    """Acquire pubchem_batch.lock with timeout. Returns True if acquired."""
    start = time.monotonic()
    while True:
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.close(fd)
            return True
        except FileExistsError:
            if time.monotonic() - start > timeout_s:
                return False
            time.sleep(1.0)


def release_lock(lock_path: Path) -> None:
    """Release pubchem_batch.lock."""
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def load_progress(progress_path: Path) -> dict[str, Any]:
    """Load progress from disk for resumability."""
    if progress_path.is_file():
        try:
            return json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed": [], "results": {}}


def save_progress(progress_path: Path, data: dict[str, Any]) -> None:
    """Save progress to disk for resumability."""
    try:
        progress_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _to_float(v: Any) -> Optional[float]:
    """Convert value to float, returning None on failure."""
    if v is None:
        return None
    try:
        return float(v) if not (isinstance(v, float) and v != v) else None
    except (TypeError, ValueError):
        return None


def load_expert_cas_from_sqlite(
    db_path: Path,
) -> list[dict[str, Any]]:
    """Load all CAS with has_expert=1 from SQLite."""
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM by_cas WHERE has_expert = 1 ORDER BY cas"""
        ).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]
    finally:
        conn.close()


def load_expert_cas_from_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Load expert CAS list from CSV."""
    if not csv_path.is_file():
        return []
    df = load_expert_csv(csv_path)
    if df is None or df.empty:
        return []
    results = []
    for _, row in df.iterrows():
        results.append(row.to_dict())
    return results


def load_subcat_scores(
    db_path: Path, cas: str, source: str
) -> dict[str, dict[str, float]]:
    """Load subcategory scores for a CAS from SQLite."""
    if not db_path.is_file():
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT category, subcategory, score
               FROM subcat_scores WHERE cas = ? AND source = ?""",
            (format_cas_display(normalize_cas(cas)), source),
        ).fetchall()
        result: dict[str, dict[str, float]] = {}
        for row in rows:
            cat = row["category"]
            subcat = row["subcategory"]
            score = _to_float(row["score"])
            if score is not None:
                result.setdefault(cat, {})[subcat] = score
        return result
    finally:
        conn.close()


def analyze_cas(
    cas_row: dict[str, Any],
    db_path: Path,
    source_type: str,
) -> CASResult:
    """Analyze coverage for a single CAS."""
    cas = str(cas_row.get("cas") or cas_row.get("CAS") or "").strip()
    cas_disp = format_cas_display(normalize_cas(cas))

    result = CASResult(
        cas=cas_disp,
        name=str(cas_row.get("name") or cas_row.get("name_expert") or ""),
        source_type=source_type,
    )

    if source_type == "sqlite":
        result.has_expert = bool(cas_row.get("has_expert"))
        result.has_auto = bool(cas_row.get("has_auto"))

        for cat, col in AUTO6_SQLITE_EXPERT_MAP.items():
            result.expert_categories[cat] = _to_float(cas_row.get(col))

        for cat, col in AUTO6_SQLITE_AUTO_MAP.items():
            result.auto_categories[cat] = _to_float(cas_row.get(col))

        expert_vals = [v for v in result.expert_categories.values() if v is not None]
        auto_vals = [v for v in result.auto_categories.values() if v is not None]

        result.expert_overall = max_of_values(expert_vals)
        result.auto_overall = max_of_values(auto_vals)

        result.expert_subcats = load_subcat_scores(db_path, cas, "expert")
        result.auto_subcats = load_subcat_scores(db_path, cas, "auto")

    else:
        result.has_expert = True
        result.has_auto = False

        for col in AUTO6_MAX_COLS:
            cat = col.replace("_max", "").replace("_", " ").title()
            result.expert_categories[cat] = _to_float(cas_row.get(col))

        expert_vals = [v for v in result.expert_categories.values() if v is not None]
        result.expert_overall = max_of_values(expert_vals)

    if result.expert_overall is not None and result.auto_overall is not None:
        result.overall_delta = abs(result.expert_overall - result.auto_overall)
        result.score_agreement = result.overall_delta <= 1.0

    return result


def compute_stats(results: list[CASResult]) -> CoverageStats:
    """Compute aggregate statistics from CAS results."""
    stats = CoverageStats()
    stats.total_expert_cas = len(results)

    deltas = []

    for r in results:
        if r.has_auto:
            stats.expert_with_auto += 1
        else:
            stats.expert_only += 1

        if r.score_agreement is True:
            stats.score_agreements += 1
        elif r.score_agreement is False:
            stats.score_disagreements += 1

        if r.overall_delta is not None:
            deltas.append(r.overall_delta)

        for cat in AUTO6_CATEGORIES:
            stats.category_fill.setdefault(cat, {"expert": 0, "auto": 0, "both": 0})

            expert_filled = r.expert_categories.get(cat) is not None
            auto_filled = r.auto_categories.get(cat) is not None

            if expert_filled:
                stats.category_fill[cat]["expert"] += 1
            if auto_filled:
                stats.category_fill[cat]["auto"] += 1
            if expert_filled and auto_filled:
                stats.category_fill[cat]["both"] += 1

        for cat, subcats in r.expert_subcats.items():
            stats.subcat_fill.setdefault(cat, {})
            for subcat in subcats:
                stats.subcat_fill[cat].setdefault(
                    subcat, {"expert": 0, "auto": 0, "both": 0}
                )
                stats.subcat_fill[cat][subcat]["expert"] += 1

        for cat, subcats in r.auto_subcats.items():
            stats.subcat_fill.setdefault(cat, {})
            for subcat in subcats:
                stats.subcat_fill[cat].setdefault(
                    subcat, {"expert": 0, "auto": 0, "both": 0}
                )
                stats.subcat_fill[cat][subcat]["auto"] += 1
                if (
                    cat in r.expert_subcats
                    and subcat in r.expert_subcats.get(cat, {})
                ):
                    stats.subcat_fill[cat][subcat]["both"] += 1

    if deltas:
        stats.mean_overall_delta = sum(deltas) / len(deltas)

    return stats


def write_per_cas_csv(results: list[CASResult], out_path: Path) -> None:
    """Write per-CAS coverage CSV."""
    fieldnames = [
        "cas",
        "name",
        "has_expert",
        "has_auto",
        "expert_overall",
        "auto_overall",
        "overall_delta",
        "score_agreement",
        "source_type",
    ]
    for cat in AUTO6_CATEGORIES:
        fieldnames.append(f"expert_{cat.replace(' ', '_')}")
        fieldnames.append(f"auto_{cat.replace(' ', '_')}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            row = {
                "cas": r.cas,
                "name": r.name,
                "has_expert": int(r.has_expert),
                "has_auto": int(r.has_auto),
                "expert_overall": r.expert_overall if r.expert_overall else "",
                "auto_overall": r.auto_overall if r.auto_overall else "",
                "overall_delta": (
                    round(r.overall_delta, 2) if r.overall_delta is not None else ""
                ),
                "score_agreement": (
                    int(r.score_agreement) if r.score_agreement is not None else ""
                ),
                "source_type": r.source_type,
            }
            for cat in AUTO6_CATEGORIES:
                col = cat.replace(" ", "_")
                row[f"expert_{col}"] = (
                    r.expert_categories.get(cat) if r.expert_categories.get(cat) else ""
                )
                row[f"auto_{col}"] = (
                    r.auto_categories.get(cat) if r.auto_categories.get(cat) else ""
                )
            writer.writerow(row)


def write_category_summary_csv(stats: CoverageStats, out_path: Path) -> None:
    """Write per-category summary CSV."""
    total = stats.total_expert_cas

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "category",
                "expert_n",
                "expert_pct",
                "auto_n",
                "auto_pct",
                "both_n",
                "both_pct",
            ]
        )

        for cat in AUTO6_CATEGORIES:
            fill = stats.category_fill.get(cat, {"expert": 0, "auto": 0, "both": 0})
            writer.writerow(
                [
                    cat,
                    fill["expert"],
                    round(100 * fill["expert"] / total, 1) if total else 0,
                    fill["auto"],
                    round(100 * fill["auto"] / total, 1) if total else 0,
                    fill["both"],
                    round(100 * fill["both"] / total, 1) if total else 0,
                ]
            )


def write_subcategory_summary_csv(stats: CoverageStats, out_path: Path) -> None:
    """Write per-subcategory summary CSV."""
    total = stats.total_expert_cas

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "category",
                "subcategory",
                "expert_n",
                "expert_pct",
                "auto_n",
                "auto_pct",
                "both_n",
                "both_pct",
            ]
        )

        for cat in sorted(stats.subcat_fill.keys()):
            subcats = stats.subcat_fill[cat]
            for subcat in sorted(subcats.keys()):
                fill = subcats[subcat]
                writer.writerow(
                    [
                        cat,
                        subcat,
                        fill["expert"],
                        round(100 * fill["expert"] / total, 1) if total else 0,
                        fill["auto"],
                        round(100 * fill["auto"] / total, 1) if total else 0,
                        fill["both"],
                        round(100 * fill["both"] / total, 1) if total else 0,
                    ]
                )


def write_summary_json(
    stats: CoverageStats, results: list[CASResult], out_path: Path
) -> None:
    """Write overall summary JSON."""
    total = stats.total_expert_cas
    summary = {
        "total_expert_cas": total,
        "expert_with_auto_coverage": stats.expert_with_auto,
        "expert_with_auto_pct": (
            round(100 * stats.expert_with_auto / total, 1) if total else 0
        ),
        "expert_only": stats.expert_only,
        "score_agreements": stats.score_agreements,
        "score_disagreements": stats.score_disagreements,
        "agreement_rate_pct": (
            round(
                100
                * stats.score_agreements
                / (stats.score_agreements + stats.score_disagreements),
                1,
            )
            if (stats.score_agreements + stats.score_disagreements) > 0
            else None
        ),
        "mean_overall_delta": round(stats.mean_overall_delta, 2),
        "category_summary": {},
        "note": (
            "Score agreement compares max-of-Auto6 overall between expert and auto. "
            "Subcategory comparison available when expert subcategory scores exist in "
            "p2oasys_score_lookup.sqlite; otherwise overall-only comparison."
        ),
    }

    for cat in AUTO6_CATEGORIES:
        fill = stats.category_fill.get(cat, {"expert": 0, "auto": 0, "both": 0})
        summary["category_summary"][cat] = {
            "expert_n": fill["expert"],
            "expert_pct": round(100 * fill["expert"] / total, 1) if total else 0,
            "auto_n": fill["auto"],
            "auto_pct": round(100 * fill["auto"] / total, 1) if total else 0,
            "both_n": fill["both"],
            "both_pct": round(100 * fill["both"] / total, 1) if total else 0,
        }

    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_coverage(
    expert_set: str,
    out_dir: Path,
    force_fast: bool = True,
    db_path: Path | None = None,
    csv_path: Path | None = None,
    resume: bool = True,
) -> int:
    """
    Run coverage cross-check.

    Args:
        expert_set: "sqlite" or "csv" to select expert data source
        out_dir: Output directory for reports
        force_fast: If True, use only cached/local data (no PubChem calls)
        db_path: Override SQLite path
        csv_path: Override CSV path
        resume: Resume from progress file if available

    Returns:
        Exit code (0 = success)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / LOCK_FILE
    progress_path = out_dir / PROGRESS_FILE

    if not acquire_lock(lock_path, timeout_s=60):
        print(
            f"ERROR: Could not acquire lock {lock_path}. Another process may be running.",
            file=sys.stderr,
        )
        return 1

    try:
        if db_path is None:
            db_path = default_lookup_db_path()

        progress = load_progress(progress_path) if resume else {"processed": [], "results": {}}
        processed_set = set(progress.get("processed", []))

        if expert_set == "sqlite":
            if not db_path.is_file():
                print(f"ERROR: SQLite not found: {db_path}", file=sys.stderr)
                return 1
            expert_rows = load_expert_cas_from_sqlite(db_path)
            source_type = "sqlite"
        elif expert_set == "csv":
            if csv_path is None:
                csv_path = DATA_DIR / "priority_expert_p2oasys_scores.csv"
            if not csv_path.is_file():
                print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
                return 1
            expert_rows = load_expert_cas_from_csv(csv_path)
            source_type = "csv"
        else:
            print(f"ERROR: Invalid expert-set: {expert_set}", file=sys.stderr)
            return 1

        print(f"Expert set: {expert_set}")
        print(f"Expert CAS count: {len(expert_rows)}")
        print(f"Output directory: {out_dir}")
        print(f"Force fast mode: {force_fast}")
        print(f"Already processed: {len(processed_set)}")
        print()

        results: list[CASResult] = []
        cached_results = progress.get("results", {})

        for i, row in enumerate(expert_rows):
            cas = str(row.get("cas") or row.get("CAS") or "").strip()
            cas_key = normalize_cas(cas)

            if cas_key in cached_results:
                r = CASResult(**cached_results[cas_key])
                results.append(r)
                continue

            if cas_key in processed_set:
                continue

            if (i + 1) % 100 == 0:
                print(f"Processing {i + 1}/{len(expert_rows)}...", flush=True)

            r = analyze_cas(row, db_path, source_type)
            results.append(r)

            processed_set.add(cas_key)
            cached_results[cas_key] = {
                "cas": r.cas,
                "name": r.name,
                "has_expert": r.has_expert,
                "has_auto": r.has_auto,
                "expert_overall": r.expert_overall,
                "auto_overall": r.auto_overall,
                "expert_categories": r.expert_categories,
                "auto_categories": r.auto_categories,
                "expert_subcats": r.expert_subcats,
                "auto_subcats": r.auto_subcats,
                "score_agreement": r.score_agreement,
                "overall_delta": r.overall_delta,
                "source_type": r.source_type,
            }

            if (i + 1) % 50 == 0:
                save_progress(
                    progress_path,
                    {"processed": list(processed_set), "results": cached_results},
                )

        save_progress(
            progress_path,
            {"processed": list(processed_set), "results": cached_results},
        )

        print(f"\nAnalyzed {len(results)} CAS entries")

        stats = compute_stats(results)

        per_cas_path = out_dir / "coverage_per_cas.csv"
        category_path = out_dir / "coverage_by_category.csv"
        subcat_path = out_dir / "coverage_by_subcategory.csv"
        summary_path = out_dir / "coverage_summary.json"

        write_per_cas_csv(results, per_cas_path)
        write_category_summary_csv(stats, category_path)
        write_subcategory_summary_csv(stats, subcat_path)
        write_summary_json(stats, results, summary_path)

        print(f"\nWritten:")
        print(f"  {per_cas_path}")
        print(f"  {category_path}")
        print(f"  {subcat_path}")
        print(f"  {summary_path}")

        print(f"\nSummary:")
        print(f"  Total expert CAS: {stats.total_expert_cas}")
        print(f"  With auto coverage: {stats.expert_with_auto} ({100*stats.expert_with_auto/stats.total_expert_cas:.1f}%)")
        print(f"  Score agreements: {stats.score_agreements}")
        print(f"  Score disagreements: {stats.score_disagreements}")
        print(f"  Mean overall delta: {stats.mean_overall_delta:.2f}")

        return 0

    finally:
        release_lock(lock_path)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare fast P2OASys coverage against expert P2OASys chemicals"
    )
    parser.add_argument(
        "--expert-set",
        choices=["csv", "sqlite"],
        required=True,
        help="Expert data source: 'csv' or 'sqlite'",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for coverage reports",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Override SQLite database path",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help="Override expert CSV path (for --expert-set csv)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume from progress file",
    )
    parser.add_argument(
        "--no-force-fast",
        action="store_true",
        help="Allow live PubChem calls (default: fast mode, local data only)",
    )

    args = parser.parse_args()

    return run_coverage(
        expert_set=args.expert_set,
        out_dir=args.out,
        force_fast=not args.no_force_fast,
        db_path=args.db,
        csv_path=args.csv_path,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    raise SystemExit(main())
