"""
Batch coverage cross-check for auto_p2oasys.

Usage:
    python -m packages.auto_p2oasys.coverage --expert-set <csv|sqlite|path> --out <dir>

Compares fast P2OASys coverage against expert P2OASys chemicals by actually
running auto_p2oasys(cas, force_fast=True) for each CAS.

Throttle-safe, resumable, disk-cached; honors ~/.turi-safe-chem-db/precalc/pubchem_batch.lock.
"""

from __future__ import annotations

import argparse
import csv
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

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.capability_config import (
    BatchConfig,
    P2OASysConfig,
    DATA_DIR,
)
from packages.p2oasys_core.lookup import (
    format_cas_display,
    load_expert_csv,
    normalize_cas,
)

PROGRESS_FILE = "coverage_progress.json"

AUTO6_CATEGORIES = (
    "Acute Human Effects",
    "Chronic Human Effects",
    "Ecological Hazards",
    "Environmental Fate & Transport",
    "Atmospheric Hazard",
    "Physical Properties",
)


@dataclass
class SubcatComparison:
    """Comparison result for a single subcategory."""

    expert_score: float | None = None
    fast_score: float | None = None
    delta: float | None = None
    is_measured: bool = False
    is_predicted: bool = False


@dataclass
class CASResult:
    """Coverage result for a single CAS."""

    cas: str
    name: str = ""
    has_expert: bool = False
    has_fast: bool = False
    expert_overall: Optional[float] = None
    fast_overall: Optional[float] = None
    expert_categories: dict[str, Optional[float]] = field(default_factory=dict)
    fast_categories: dict[str, Optional[float]] = field(default_factory=dict)
    expert_subcats: dict[str, dict[str, float]] = field(default_factory=dict)
    fast_subcats: dict[str, dict[str, float]] = field(default_factory=dict)
    subcat_comparisons: dict[str, dict[str, SubcatComparison]] = field(
        default_factory=dict
    )
    score_agreement: Optional[bool] = None
    overall_delta: Optional[float] = None
    mode: str = ""
    error: str | None = None
    evidence_count: int = 0
    measured_count: int = 0
    predicted_count: int = 0


@dataclass
class CoverageStats:
    """Aggregate coverage statistics."""

    total_expert_cas: int = 0
    expert_with_fast: int = 0
    expert_only: int = 0
    fast_errors: int = 0
    category_fill: dict[str, dict[str, int]] = field(default_factory=dict)
    subcat_fill: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    score_agreements: int = 0
    score_disagreements: int = 0
    mean_overall_delta: float = 0.0
    total_measured: int = 0
    total_predicted: int = 0
    total_evidence: int = 0


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


def load_expert_cas_from_sqlite(db_path: Path) -> list[dict[str, Any]]:
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


def is_measured_evidence(evidence_type: str) -> bool:
    """Check if evidence type is measured (vs predicted)."""
    measured_sources = {
        "pubchem",
        "sds",
        "tci",
        "fisher",
        "cameo",
        "iuclid",
        "comptox",
        "cpdb",
        "iarc",
    }
    return any(src in evidence_type.lower() for src in measured_sources)


def is_predicted_evidence(evidence_type: str) -> bool:
    """Check if evidence type is predicted (vs measured)."""
    predicted_sources = {"ecosar", "qsar", "model", "predict", "estimate"}
    return any(src in evidence_type.lower() for src in predicted_sources)


def analyze_cas(cas: str, name: str = "") -> CASResult:
    """Analyze coverage for a single CAS by running auto_p2oasys(force_fast=True)."""
    from packages.auto_p2oasys import auto_p2oasys, P2OASysMode

    result = CASResult(cas=format_cas_display(normalize_cas(cas)), name=name)

    try:
        p2_result = auto_p2oasys(cas, force_fast=True)

        result.mode = p2_result.mode.value
        result.name = p2_result.name or name
        result.evidence_count = len(p2_result.evidence)

        for ev in p2_result.evidence:
            ev_type = getattr(ev, "source", "") or getattr(ev, "adapter", "") or ""
            if is_measured_evidence(ev_type):
                result.measured_count += 1
            elif is_predicted_evidence(ev_type):
                result.predicted_count += 1

        if p2_result.mode in (P2OASysMode.EXPERT, P2OASysMode.EXPERT_PLUS_FAST):
            result.has_expert = True
            result.expert_overall = p2_result.expert_overall
            result.expert_categories = dict(p2_result.expert_categories)

            for cat_name, cat_score in p2_result.categories.items():
                if cat_score.status == "expert" and cat_score.subcategories:
                    result.expert_subcats[cat_name] = dict(cat_score.subcategories)

        if p2_result.mode in (P2OASysMode.FAST, P2OASysMode.EXPERT_PLUS_FAST):
            result.has_fast = True
            result.fast_overall = p2_result.fast_overall
            result.fast_categories = dict(p2_result.fast_categories)

            for cat_name, cat_score in p2_result.categories.items():
                if cat_score.status != "expert" and cat_score.subcategories:
                    result.fast_subcats[cat_name] = dict(cat_score.subcategories)

        if p2_result.mode == P2OASysMode.NOT_FOUND:
            result.error = p2_result.error

        if result.expert_overall is not None and result.fast_overall is not None:
            result.overall_delta = abs(result.expert_overall - result.fast_overall)
            result.score_agreement = result.overall_delta <= 1.0

        for cat in AUTO6_CATEGORIES:
            result.subcat_comparisons[cat] = {}

            expert_subcats = result.expert_subcats.get(cat, {})
            fast_subcats = result.fast_subcats.get(cat, {})
            all_subcats = set(expert_subcats.keys()) | set(fast_subcats.keys())

            for subcat in all_subcats:
                comp = SubcatComparison(
                    expert_score=expert_subcats.get(subcat),
                    fast_score=fast_subcats.get(subcat),
                )
                if comp.expert_score is not None and comp.fast_score is not None:
                    comp.delta = abs(comp.expert_score - comp.fast_score)
                result.subcat_comparisons[cat][subcat] = comp

    except Exception as e:
        result.error = str(e)

    return result


def compute_stats(results: list[CASResult]) -> CoverageStats:
    """Compute aggregate statistics from CAS results."""
    stats = CoverageStats()
    stats.total_expert_cas = len(results)

    deltas = []

    for r in results:
        if r.error:
            stats.fast_errors += 1
        elif r.has_fast:
            stats.expert_with_fast += 1
        else:
            stats.expert_only += 1

        if r.score_agreement is True:
            stats.score_agreements += 1
        elif r.score_agreement is False:
            stats.score_disagreements += 1

        if r.overall_delta is not None:
            deltas.append(r.overall_delta)

        stats.total_measured += r.measured_count
        stats.total_predicted += r.predicted_count
        stats.total_evidence += r.evidence_count

        for cat in AUTO6_CATEGORIES:
            stats.category_fill.setdefault(cat, {"expert": 0, "fast": 0, "both": 0})

            expert_filled = r.expert_categories.get(cat) is not None
            fast_filled = r.fast_categories.get(cat) is not None

            if expert_filled:
                stats.category_fill[cat]["expert"] += 1
            if fast_filled:
                stats.category_fill[cat]["fast"] += 1
            if expert_filled and fast_filled:
                stats.category_fill[cat]["both"] += 1

        for cat, subcats in r.expert_subcats.items():
            stats.subcat_fill.setdefault(cat, {})
            for subcat in subcats:
                stats.subcat_fill[cat].setdefault(
                    subcat, {"expert": 0, "fast": 0, "both": 0}
                )
                stats.subcat_fill[cat][subcat]["expert"] += 1

        for cat, subcats in r.fast_subcats.items():
            stats.subcat_fill.setdefault(cat, {})
            for subcat in subcats:
                stats.subcat_fill[cat].setdefault(
                    subcat, {"expert": 0, "fast": 0, "both": 0}
                )
                stats.subcat_fill[cat][subcat]["fast"] += 1
                if cat in r.expert_subcats and subcat in r.expert_subcats.get(cat, {}):
                    stats.subcat_fill[cat][subcat]["both"] += 1

    if deltas:
        stats.mean_overall_delta = sum(deltas) / len(deltas)

    return stats


def write_per_cas_csv(results: list[CASResult], out_path: Path) -> None:
    """Write per-CAS coverage CSV."""
    fieldnames = [
        "cas",
        "name",
        "mode",
        "has_expert",
        "has_fast",
        "expert_overall",
        "fast_overall",
        "overall_delta",
        "score_agreement",
        "evidence_count",
        "measured_count",
        "predicted_count",
        "error",
    ]
    for cat in AUTO6_CATEGORIES:
        fieldnames.append(f"expert_{cat.replace(' ', '_').replace('&', 'and')}")
        fieldnames.append(f"fast_{cat.replace(' ', '_').replace('&', 'and')}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            row = {
                "cas": r.cas,
                "name": r.name,
                "mode": r.mode,
                "has_expert": int(r.has_expert),
                "has_fast": int(r.has_fast),
                "expert_overall": r.expert_overall if r.expert_overall else "",
                "fast_overall": r.fast_overall if r.fast_overall else "",
                "overall_delta": (
                    round(r.overall_delta, 2) if r.overall_delta is not None else ""
                ),
                "score_agreement": (
                    int(r.score_agreement) if r.score_agreement is not None else ""
                ),
                "evidence_count": r.evidence_count,
                "measured_count": r.measured_count,
                "predicted_count": r.predicted_count,
                "error": r.error or "",
            }
            for cat in AUTO6_CATEGORIES:
                col = cat.replace(" ", "_").replace("&", "and")
                row[f"expert_{col}"] = (
                    r.expert_categories.get(cat)
                    if r.expert_categories.get(cat)
                    else ""
                )
                row[f"fast_{col}"] = (
                    r.fast_categories.get(cat) if r.fast_categories.get(cat) else ""
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
                "fast_n",
                "fast_pct",
                "both_n",
                "both_pct",
            ]
        )

        for cat in AUTO6_CATEGORIES:
            fill = stats.category_fill.get(cat, {"expert": 0, "fast": 0, "both": 0})
            writer.writerow(
                [
                    cat,
                    fill["expert"],
                    round(100 * fill["expert"] / total, 1) if total else 0,
                    fill["fast"],
                    round(100 * fill["fast"] / total, 1) if total else 0,
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
                "fast_n",
                "fast_pct",
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
                        fill["fast"],
                        round(100 * fill["fast"] / total, 1) if total else 0,
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
        "expert_with_fast_coverage": stats.expert_with_fast,
        "expert_with_fast_pct": (
            round(100 * stats.expert_with_fast / total, 1) if total else 0
        ),
        "expert_only": stats.expert_only,
        "fast_errors": stats.fast_errors,
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
        "measured_vs_predicted": {
            "total_evidence": stats.total_evidence,
            "measured_count": stats.total_measured,
            "predicted_count": stats.total_predicted,
            "measured_pct": (
                round(100 * stats.total_measured / stats.total_evidence, 1)
                if stats.total_evidence
                else 0
            ),
            "predicted_pct": (
                round(100 * stats.total_predicted / stats.total_evidence, 1)
                if stats.total_evidence
                else 0
            ),
        },
        "category_summary": {},
        "note": (
            "This tool runs auto_p2oasys(cas, force_fast=True) for each expert CAS "
            "and compares fast pipeline scores against expert scores at both "
            "category and subcategory levels. "
            "Score agreement: overall delta <= 1.0. "
            "Measured = PubChem/SDS/IUCLID/etc; Predicted = ECOSAR/QSAR."
        ),
    }

    for cat in AUTO6_CATEGORIES:
        fill = stats.category_fill.get(cat, {"expert": 0, "fast": 0, "both": 0})
        summary["category_summary"][cat] = {
            "expert_n": fill["expert"],
            "expert_pct": round(100 * fill["expert"] / total, 1) if total else 0,
            "fast_n": fill["fast"],
            "fast_pct": round(100 * fill["fast"] / total, 1) if total else 0,
            "both_n": fill["both"],
            "both_pct": round(100 * fill["both"] / total, 1) if total else 0,
        }

    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def resolve_expert_set(expert_set: str) -> tuple[str, Path | None]:
    """
    Resolve --expert-set argument to (source_type, path).

    Accepts:
    - "sqlite" -> use default P2OASysConfig.score_lookup_db()
    - "csv" -> use default P2OASysConfig.expert_csv() or DATA_DIR/priority_expert_p2oasys_scores.csv
    - file path -> auto-detect type from extension
    """
    if expert_set == "sqlite":
        return "sqlite", P2OASysConfig.score_lookup_db()
    elif expert_set == "csv":
        csv_path = P2OASysConfig.expert_csv()
        if csv_path is None:
            csv_path = DATA_DIR / "priority_expert_p2oasys_scores.csv"
        return "csv", csv_path
    else:
        path = Path(expert_set)
        if path.suffix.lower() in (".sqlite", ".db", ".sqlite3"):
            return "sqlite", path
        elif path.suffix.lower() in (".csv", ".tsv"):
            return "csv", path
        else:
            return "sqlite", path


def run_coverage(
    expert_set: str,
    out_dir: Path,
    resume: bool = True,
) -> int:
    """
    Run coverage cross-check.

    Args:
        expert_set: "sqlite", "csv", or file path to expert data source
        out_dir: Output directory for reports
        resume: Resume from progress file if available

    Returns:
        Exit code (0 = success)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = BatchConfig.pubchem_batch_lock()
    progress_path = out_dir / PROGRESS_FILE

    if not acquire_lock(lock_path, timeout_s=60):
        print(
            f"ERROR: Could not acquire lock {lock_path}. Another process may be running.",
            file=sys.stderr,
        )
        return 1

    try:
        source_type, data_path = resolve_expert_set(expert_set)

        if data_path is None or not data_path.is_file():
            print(f"ERROR: Data source not found: {data_path}", file=sys.stderr)
            return 1

        progress = (
            load_progress(progress_path) if resume else {"processed": [], "results": {}}
        )
        processed_set = set(progress.get("processed", []))

        if source_type == "sqlite":
            expert_rows = load_expert_cas_from_sqlite(data_path)
        else:
            expert_rows = load_expert_cas_from_csv(data_path)

        print(f"Expert set: {expert_set} ({source_type})")
        print(f"Data path: {data_path}")
        print(f"Expert CAS count: {len(expert_rows)}")
        print(f"Output directory: {out_dir}")
        print(f"Lock file: {lock_path}")
        print(f"Already processed: {len(processed_set)}")
        print()

        results: list[CASResult] = []
        cached_results = progress.get("results", {})

        for i, row in enumerate(expert_rows):
            cas = str(row.get("cas") or row.get("CAS") or "").strip()
            name = str(row.get("name") or row.get("name_expert") or "").strip()
            cas_key = normalize_cas(cas)

            if cas_key in cached_results:
                cached = cached_results[cas_key]
                r = CASResult(
                    cas=cached.get("cas", ""),
                    name=cached.get("name", ""),
                    has_expert=cached.get("has_expert", False),
                    has_fast=cached.get("has_fast", False),
                    expert_overall=cached.get("expert_overall"),
                    fast_overall=cached.get("fast_overall"),
                    expert_categories=cached.get("expert_categories", {}),
                    fast_categories=cached.get("fast_categories", {}),
                    expert_subcats=cached.get("expert_subcats", {}),
                    fast_subcats=cached.get("fast_subcats", {}),
                    score_agreement=cached.get("score_agreement"),
                    overall_delta=cached.get("overall_delta"),
                    mode=cached.get("mode", ""),
                    error=cached.get("error"),
                    evidence_count=cached.get("evidence_count", 0),
                    measured_count=cached.get("measured_count", 0),
                    predicted_count=cached.get("predicted_count", 0),
                )
                results.append(r)
                continue

            if (i + 1) % 10 == 0 or i == 0:
                print(
                    f"[{i + 1}/{len(expert_rows)}] Processing {cas} {name[:30]}...",
                    flush=True,
                )

            r = analyze_cas(cas, name)
            results.append(r)

            processed_set.add(cas_key)
            cached_results[cas_key] = {
                "cas": r.cas,
                "name": r.name,
                "has_expert": r.has_expert,
                "has_fast": r.has_fast,
                "expert_overall": r.expert_overall,
                "fast_overall": r.fast_overall,
                "expert_categories": r.expert_categories,
                "fast_categories": r.fast_categories,
                "expert_subcats": r.expert_subcats,
                "fast_subcats": r.fast_subcats,
                "score_agreement": r.score_agreement,
                "overall_delta": r.overall_delta,
                "mode": r.mode,
                "error": r.error,
                "evidence_count": r.evidence_count,
                "measured_count": r.measured_count,
                "predicted_count": r.predicted_count,
            }

            if (i + 1) % 25 == 0:
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
        print(
            f"  With fast coverage: {stats.expert_with_fast} "
            f"({100*stats.expert_with_fast/stats.total_expert_cas:.1f}%)"
        )
        print(f"  Fast errors: {stats.fast_errors}")
        print(f"  Score agreements: {stats.score_agreements}")
        print(f"  Score disagreements: {stats.score_disagreements}")
        print(f"  Mean overall delta: {stats.mean_overall_delta:.2f}")
        print(f"\nMeasured vs Predicted:")
        print(f"  Total evidence: {stats.total_evidence}")
        print(f"  Measured: {stats.total_measured}")
        print(f"  Predicted: {stats.total_predicted}")

        return 0

    finally:
        release_lock(lock_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m packages.auto_p2oasys.coverage",
        description="Compare fast P2OASys coverage against expert P2OASys chemicals",
    )
    parser.add_argument(
        "--expert-set",
        required=True,
        help="Expert data source: 'csv', 'sqlite', or path to file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for coverage reports",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume from progress file",
    )

    args = parser.parse_args(argv)

    return run_coverage(
        expert_set=args.expert_set,
        out_dir=args.out,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    raise SystemExit(main())
