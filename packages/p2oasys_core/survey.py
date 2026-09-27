"""
User survey for Process Factors and Life Cycle Factors.

These TURI P2OASys categories cannot be auto-scored from chemical data sources
and require human expert assessment. This module provides:
  - Matrix band definitions (score 2/4/6/8/10 criteria per subcategory)
  - Data model for survey answers (JSON-serializable)
  - Save/load per CAS
  - CLI interface

CRITICAL: Blank stays blank — never default to 2, never auto-fill.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# Band score values in the TURI P2OASys matrix
BAND_SCORES = (2, 4, 6, 8, 10)

# Default data directory for survey answers
DEFAULT_SURVEY_DIR = Path(__file__).resolve().parents[2] / "data" / "survey_answers"


class Category(str, Enum):
    """Non-auto-scored P2OASys categories requiring human assessment."""
    PROCESS_FACTORS = "Process Factors"
    LIFE_CYCLE_FACTORS = "Life Cycle Factors"


# ─────────────────────────────────────────────────────────────────────────────
# TURI Matrix Band Definitions
# Process Factors and Life Cycle Factors subcategories with score criteria.
# Source: TURI P2OASys methodology (scores: 2=low concern → 10=high concern)
# ─────────────────────────────────────────────────────────────────────────────

PROCESS_FACTORS_MATRIX: Dict[str, Dict[int, str]] = {
    "Exposure Potential": {
        2: "Low exposure potential: closed system, minimal handling, no vapor release",
        4: "Moderate-low exposure: occasional open handling, low volatility, good ventilation",
        6: "Moderate exposure: regular handling, moderate volatility, standard controls",
        8: "High exposure potential: frequent open handling, volatile, limited controls",
        10: "Very high exposure: continuous open use, highly volatile, inadequate controls",
    },
    "Ergonomic Hazard": {
        2: "Minimal ergonomic concern: light weight, easy handling, no repetitive motions",
        4: "Low ergonomic concern: modest weight, occasional handling requirements",
        6: "Moderate ergonomic concern: regular lifting/handling, some repetitive tasks",
        8: "High ergonomic concern: heavy containers, frequent handling, awkward positions",
        10: "Severe ergonomic hazard: very heavy loads, continuous handling, injury risk",
    },
    "Psychosocial Hazard": {
        2: "Minimal psychosocial concern: routine chemical, well-understood, workers comfortable",
        4: "Low concern: familiar chemical class, adequate training provided",
        6: "Moderate concern: requires attention to handling, some worker uncertainty",
        8: "High concern: known hazardous reputation, worker anxiety, complex procedures",
        10: "Severe psychosocial hazard: feared chemical, significant worker stress, stigma",
    },
    "High/Low Pressure System": {
        2: "Ambient pressure operation, no pressurized systems involved",
        4: "Low pressure systems (<50 psig), standard equipment, minimal concern",
        6: "Moderate pressure operations (50-150 psig), requires trained operators",
        8: "High pressure systems (150-500 psig), specialized equipment, safety protocols",
        10: "Very high pressure (>500 psig) or vacuum systems, extreme caution required",
    },
    "Water Use": {
        2: "No water use in process, dry application or closed loop",
        4: "Minimal water use: occasional rinsing, small volumes recycled",
        6: "Moderate water use: regular cleaning, treatment available",
        8: "High water consumption: continuous flow, significant wastewater generated",
        10: "Very high water intensity: large volumes, complex treatment required",
    },
}

LIFE_CYCLE_FACTORS_MATRIX: Dict[str, Dict[int, str]] = {
    "Upstream Processing and Manufacturing": {
        2: "Green manufacturing: renewable feedstocks, low energy, minimal waste",
        4: "Relatively clean production: some fossil inputs, efficient process",
        6: "Standard chemical manufacturing: typical energy/waste profile",
        8: "Energy-intensive production: significant fossil inputs, notable waste streams",
        10: "Very high impact manufacturing: hazardous synthesis, major pollution concerns",
    },
    "Renewable to Nonrenewable Resource": {
        2: "Fully renewable: bio-based, sustainably sourced feedstock",
        4: "Mostly renewable: >75% bio-based or recycled content",
        6: "Mixed sourcing: partial bio-based, partial petrochemical",
        8: "Mostly non-renewable: >75% petrochemical or mined feedstock",
        10: "Fully non-renewable: 100% fossil-derived, finite resource base",
    },
    "Usage and Retail": {
        2: "Minimal end-use concern: contained use, no consumer exposure, recyclable packaging",
        4: "Low concern: limited consumer exposure, returnable/recyclable systems",
        6: "Moderate concern: some consumer exposure, standard disposal expected",
        8: "High concern: direct consumer contact, difficult-to-recycle packaging",
        10: "Very high concern: extensive consumer exposure, single-use, disposal issues",
    },
    "End of life": {
        2: "Readily biodegradable, non-toxic breakdown products, no accumulation",
        4: "Biodegradable with low-concern intermediates, standard waste treatment",
        6: "Moderate persistence, requires treatment, manageable disposal",
        8: "Persistent or requires specialized disposal, limited treatment options",
        10: "Highly persistent, hazardous waste designation, major disposal challenge",
    },
}

MATRIX_BY_CATEGORY: Dict[Category, Dict[str, Dict[int, str]]] = {
    Category.PROCESS_FACTORS: PROCESS_FACTORS_MATRIX,
    Category.LIFE_CYCLE_FACTORS: LIFE_CYCLE_FACTORS_MATRIX,
}


def get_subcategories(category: Category) -> List[str]:
    """Return subcategory names for a category."""
    return list(MATRIX_BY_CATEGORY[category].keys())


def get_band_description(category: Category, subcategory: str, score: int) -> Optional[str]:
    """Return the band description for a specific score, or None if invalid."""
    matrix = MATRIX_BY_CATEGORY.get(category)
    if not matrix:
        return None
    subcat_bands = matrix.get(subcategory)
    if not subcat_bands:
        return None
    return subcat_bands.get(score)


def get_all_options(category: Category, subcategory: str) -> List[Dict[str, Any]]:
    """Return all score options for a subcategory as list of {score, description}."""
    matrix = MATRIX_BY_CATEGORY.get(category)
    if not matrix:
        return []
    subcat_bands = matrix.get(subcategory)
    if not subcat_bands:
        return []
    return [
        {"score": score, "description": subcat_bands[score]}
        for score in BAND_SCORES
        if score in subcat_bands
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Survey Answer Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SubcategoryAnswer:
    """A single subcategory answer from the survey."""
    category: str
    subcategory: str
    score: Optional[int] = None  # None = blank/don't know
    source: str = "user"  # Always "user" for survey answers
    note: str = ""
    answered_at: Optional[str] = None  # ISO timestamp when answered
    
    def __post_init__(self):
        if self.score is not None and self.score not in BAND_SCORES:
            raise ValueError(f"Invalid score {self.score}; must be one of {BAND_SCORES} or None")
    
    @property
    def is_answered(self) -> bool:
        """True if user provided a score (not blank)."""
        return self.score is not None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubcategoryAnswer":
        return cls(**data)


@dataclass
class SurveyAnswers:
    """
    Complete survey answers for a single CAS number.
    
    CRITICAL: Blank stays blank. Never auto-fill scores.
    Unanswered subcategories have score=None.
    """
    cas: str
    answers: Dict[str, SubcategoryAnswer] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    chemical_name: str = ""
    
    def _key(self, category: str, subcategory: str) -> str:
        return f"{category}::{subcategory}"
    
    def set_answer(
        self,
        category: Category,
        subcategory: str,
        score: Optional[int],
        note: str = "",
    ) -> None:
        """
        Set or update an answer. Use score=None to mark as blank/don't know.
        """
        key = self._key(category.value, subcategory)
        self.answers[key] = SubcategoryAnswer(
            category=category.value,
            subcategory=subcategory,
            score=score,
            source="user",
            note=note,
            answered_at=datetime.now(timezone.utc).isoformat() if score is not None else None,
        )
        self.updated_at = datetime.now(timezone.utc).isoformat()
    
    def get_answer(self, category: Category, subcategory: str) -> Optional[SubcategoryAnswer]:
        """Get answer for a subcategory, or None if not set."""
        key = self._key(category.value, subcategory)
        return self.answers.get(key)
    
    def get_score(self, category: Category, subcategory: str) -> Optional[int]:
        """Get just the score for a subcategory, or None if blank/unanswered."""
        answer = self.get_answer(category, subcategory)
        return answer.score if answer else None
    
    def count_answered(self, category: Optional[Category] = None) -> int:
        """Count how many subcategories have been answered (not blank)."""
        count = 0
        for answer in self.answers.values():
            if category and answer.category != category.value:
                continue
            if answer.is_answered:
                count += 1
        return count
    
    def count_total(self, category: Optional[Category] = None) -> int:
        """Count total subcategories (answered + unanswered) for a category."""
        if category:
            return len(get_subcategories(category))
        return sum(len(get_subcategories(c)) for c in Category)
    
    def category_max(self, category: Category) -> Optional[int]:
        """
        Return max score for a category, or None if no answers.
        
        CRITICAL: Returns None (not 2) if all subcategories are blank.
        """
        scores = []
        for subcategory in get_subcategories(category):
            score = self.get_score(category, subcategory)
            if score is not None:
                scores.append(score)
        return max(scores) if scores else None
    
    def category_mean(self, category: Category) -> Optional[float]:
        """Return mean score for answered subcategories, or None if none answered."""
        scores = []
        for subcategory in get_subcategories(category):
            score = self.get_score(category, subcategory)
            if score is not None:
                scores.append(score)
        if not scores:
            return None
        return sum(scores) / len(scores)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cas": self.cas,
            "chemical_name": self.chemical_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "answers": {k: v.to_dict() for k, v in self.answers.items()},
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SurveyAnswers":
        answers_raw = data.get("answers", {})
        answers = {k: SubcategoryAnswer.from_dict(v) for k, v in answers_raw.items()}
        return cls(
            cas=data["cas"],
            answers=answers,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            chemical_name=data.get("chemical_name", ""),
        )
    
    def summary(self) -> Dict[str, Any]:
        """Return a summary dict suitable for display."""
        return {
            "cas": self.cas,
            "chemical_name": self.chemical_name,
            "process_factors": {
                "max": self.category_max(Category.PROCESS_FACTORS),
                "mean": self.category_mean(Category.PROCESS_FACTORS),
                "answered": self.count_answered(Category.PROCESS_FACTORS),
                "total": self.count_total(Category.PROCESS_FACTORS),
            },
            "life_cycle_factors": {
                "max": self.category_max(Category.LIFE_CYCLE_FACTORS),
                "mean": self.category_mean(Category.LIFE_CYCLE_FACTORS),
                "answered": self.count_answered(Category.LIFE_CYCLE_FACTORS),
                "total": self.count_total(Category.LIFE_CYCLE_FACTORS),
            },
            "updated_at": self.updated_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Save/Load per CAS
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_cas_for_filename(cas: str) -> str:
    """Normalize CAS for safe filename (remove dashes, lowercase)."""
    return "".join(c for c in cas if c.isdigit())


def get_survey_dir() -> Path:
    """Get survey answers directory from env or default."""
    env_path = os.environ.get("SURVEY_ANSWERS_DIR", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_SURVEY_DIR


def survey_file_path(cas: str) -> Path:
    """Return the JSON file path for a CAS survey."""
    cas_digits = _normalize_cas_for_filename(cas)
    return get_survey_dir() / f"survey_{cas_digits}.json"


def save_survey(answers: SurveyAnswers) -> Path:
    """
    Save survey answers to JSON file.
    Creates directory if needed. Returns the file path.
    """
    path = survey_file_path(answers.cas)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(answers.to_dict(), f, indent=2, ensure_ascii=False)
    return path


def load_survey(cas: str) -> Optional[SurveyAnswers]:
    """
    Load survey answers for a CAS from JSON file.
    Returns None if no saved answers exist.
    """
    path = survey_file_path(cas)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SurveyAnswers.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to load survey for %s from %s: %s", cas, path, e
        )
        return None


def list_saved_surveys() -> List[Dict[str, Any]]:
    """
    List all saved surveys with their CAS and answer counts.
    Returns list of {cas, file_path, answered, total, updated_at}.
    """
    survey_dir = get_survey_dir()
    if not survey_dir.is_dir():
        return []
    
    results = []
    for path in survey_dir.glob("survey_*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            answers = SurveyAnswers.from_dict(data)
            results.append({
                "cas": answers.cas,
                "chemical_name": answers.chemical_name,
                "file_path": str(path),
                "answered": answers.count_answered(),
                "total": answers.count_total(),
                "updated_at": answers.updated_at,
            })
        except Exception:
            continue
    
    return sorted(results, key=lambda x: x.get("updated_at", ""), reverse=True)


def delete_survey(cas: str) -> bool:
    """Delete saved survey for a CAS. Returns True if deleted."""
    path = survey_file_path(cas)
    if path.is_file():
        path.unlink()
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI Interface
# ─────────────────────────────────────────────────────────────────────────────

def cli_show_survey_form(cas: str) -> None:
    """Print survey form to stdout for CLI use."""
    print(f"\n{'='*60}")
    print(f"P2OASys Survey: Process Factors & Life Cycle Factors")
    print(f"CAS: {cas}")
    print(f"{'='*60}")
    
    existing = load_survey(cas)
    if existing:
        print(f"\n[Existing answers loaded from {survey_file_path(cas)}]")
        print(f"Last updated: {existing.updated_at}")
    
    for category in Category:
        print(f"\n--- {category.value} ---\n")
        for subcategory in get_subcategories(category):
            current = existing.get_score(category, subcategory) if existing else None
            status = f"[Current: {current}]" if current else "[Blank]"
            print(f"{subcategory} {status}")
            for opt in get_all_options(category, subcategory):
                print(f"  {opt['score']}: {opt['description']}")
            print()
    
    print("To answer via CLI, use: python -m packages.p2oasys_core.survey answer <CAS> <category> <subcategory> <score>")
    print("Score values: 2, 4, 6, 8, 10, or 'blank' to clear")


def cli_set_answer(
    cas: str,
    category_name: str,
    subcategory: str,
    score_str: str,
    note: str = "",
) -> None:
    """Set an answer via CLI."""
    # Parse category
    category_map = {c.value.lower(): c for c in Category}
    cat_key = category_name.lower().replace("_", " ")
    if cat_key not in category_map:
        print(f"Error: Unknown category '{category_name}'")
        print(f"Valid categories: {', '.join(c.value for c in Category)}")
        return
    category = category_map[cat_key]
    
    # Validate subcategory
    valid_subcats = get_subcategories(category)
    if subcategory not in valid_subcats:
        print(f"Error: Unknown subcategory '{subcategory}' in {category.value}")
        print(f"Valid subcategories: {', '.join(valid_subcats)}")
        return
    
    # Parse score
    if score_str.lower() in ("blank", "none", "null", "-"):
        score = None
    else:
        try:
            score = int(score_str)
            if score not in BAND_SCORES:
                raise ValueError()
        except ValueError:
            print(f"Error: Invalid score '{score_str}'")
            print(f"Valid scores: {', '.join(map(str, BAND_SCORES))} or 'blank'")
            return
    
    # Load or create survey
    answers = load_survey(cas) or SurveyAnswers(cas=cas)
    answers.set_answer(category, subcategory, score, note)
    
    # Save
    path = save_survey(answers)
    print(f"Answer saved: {category.value} / {subcategory} = {score or 'blank'}")
    print(f"File: {path}")


def cli_show_summary(cas: str) -> None:
    """Show summary for a CAS."""
    answers = load_survey(cas)
    if not answers:
        print(f"No survey answers found for CAS {cas}")
        return
    
    summary = answers.summary()
    print(f"\nSurvey Summary for {cas}")
    if summary["chemical_name"]:
        print(f"Chemical: {summary['chemical_name']}")
    print(f"Updated: {summary['updated_at']}")
    
    for key, label in [("process_factors", "Process Factors"), ("life_cycle_factors", "Life Cycle Factors")]:
        cat = summary[key]
        print(f"\n{label}:")
        print(f"  Answered: {cat['answered']}/{cat['total']}")
        if cat['max'] is not None:
            print(f"  Max score: {cat['max']}")
            print(f"  Mean score: {cat['mean']:.1f}")
        else:
            print("  Max score: (none answered)")


def main():
    """CLI entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m packages.p2oasys_core.survey <command> [args]")
        print("\nCommands:")
        print("  show <CAS>                        - Show survey form with current answers")
        print("  answer <CAS> <cat> <subcat> <score> [note] - Set an answer")
        print("  summary <CAS>                     - Show summary for a CAS")
        print("  list                              - List all saved surveys")
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "show" and len(sys.argv) >= 3:
        cli_show_survey_form(sys.argv[2])
    elif cmd == "answer" and len(sys.argv) >= 6:
        note = sys.argv[6] if len(sys.argv) > 6 else ""
        cli_set_answer(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], note)
    elif cmd == "summary" and len(sys.argv) >= 3:
        cli_show_summary(sys.argv[2])
    elif cmd == "list":
        surveys = list_saved_surveys()
        if not surveys:
            print("No saved surveys found.")
        else:
            print(f"Found {len(surveys)} saved survey(s):\n")
            for s in surveys:
                print(f"  CAS {s['cas']}: {s['answered']}/{s['total']} answered, updated {s['updated_at']}")
    else:
        print("Invalid command. Run without arguments for help.")


if __name__ == "__main__":
    main()
