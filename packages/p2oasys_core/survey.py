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
# Source: "Hazard Matrix Group Review 9-19-23.xlsx" from TURI P2OASys
# Users can assign whatever score they think appropriate; indicators are a guide.
# ─────────────────────────────────────────────────────────────────────────────

PROCESS_FACTORS_MATRIX: Dict[str, Dict[int, str]] = {
    "Heat": {
        2: "No symptoms (WBGT <25°C)",
        4: "Heat rash - sweating, red clusters of pimples/blisters (WBGT 27°C, sun stress after 45 min)",
        6: "Heat cramps - muscle pain, water loss and salts (WBGT 30°C, sun stress after 30 min)",
        8: "Heat exhaustion - headache, nausea, dizziness, weakness, irritability, thirst, heavy sweating, elevated body temperature, decreased urine output (WBGT 32°C, sun stress after 20 min)",
        10: "Heat stroke - confusion, loss of consciousness, seizures, very high body temperature, hot dry skin or profuse sweating (WBGT >32°C, sun stress after 15 min)",
    },
    "Cold": {
        2: "No symptoms",
        4: "Hypothermia (prolonged cold exposure) - shivering, fatigue, loss of coordination, confusion, disorientation; late symptoms - no shivering, blue skin, dilated pupils, slowed pulse and breathing, loss of consciousness",
        6: "Frostbite (freezing, often affects nose, ears, cheeks, chin, fingers, toes) - reduced blood flow to hands and feet, numbness, aching, tingling or stinging, bluish or pale waxy skin",
        8: "Trench foot (prolonged wet/cold exposure, can occur at temps up to 60°F) - reddening of skin, numbness, leg cramps, tingling pain, blisters or ulcers, bleeding under the skin, gangrene",
        10: "Chilblains (just above freezing to 60°F) - ulcers formed by damaged blood vessels, redness, itching, blistering, inflammation, possible ulcerations",
    },
    "Noise": {
        2: "80 dBA/no time limit - no symptoms",
        4: "85 dBA/8 hr limit - no symptoms",
        6: "88 dBA/4 hr limit - Hearing impairment; hear ringing or humming in ears when leaving work",
        8: "90 dBA/2 hr limit - Tinnitus; have to shout to be heard by coworker at arm's length; temporary hearing loss when leaving work",
        10: ">90 dBA/1.5 hr limit - Noise-induced hearing loss; permanent hearing loss",
    },
    "Vibration": {
        2: "Class 1 Small Machine: 0.71 mm/s; Class 2 Medium: 1.12 mm/s; Class 3 Large Rigid: 1.8 mm/s; Class 4 Large Soft: 1.8 mm/s",
        4: "Class 1: 1.8 mm/s; Class 2: 2.8 mm/s; Class 3: 4.5 mm/s; Class 4: 4.5 mm/s",
        6: "Class 1: 4.5 mm/s; Class 2: 7.1 mm/s; Class 3: 7.1 mm/s; Class 4: 11.2 mm/s",
        8: "Elevated vibration levels across machine classes",
        10: "Class 1: 7.1 mm/s; Class 2: 11.2 mm/s; Class 3: 18 mm/s; Class 4: 28 mm/s",
    },
    "Ergonomic Hazard": {
        2: "Rare, unlikely, improbable occurrence; insignificant hazard, no injury, no impact on time",
        4: "Unlikely/remote occurrence; minor injury/illness, minor impact on time lost",
        6: "Possible occurrence; moderate injury, lost time",
        8: "Likely and probable occurrence; major long-term injury or health effect or permanent disability",
        10: "Constant/almost certain occurrence; catastrophic - kill or cause permanent disability or ill health",
    },
    "Psychosocial Hazard": {
        2: "Process improves workload; adequate machine pacing; improves time constraints; normalizes shift work; eliminates isolation; includes worker input; improved equipment quality; improves workspace conditions",
        4: "Process allows for minor changes in real-time by worker",
        6: "Process provides worker with access to supervisor about needed changes; requires restricted access",
        8: "Process contributes to underload or work overload; high/low machine pacing; creates time pressure/deadlines; creates irregular shift work; creates isolation; does not allow workers in decision process; inadequate equipment; poor environmental conditions",
        10: "Process creates excessive shift work; changes in process lead to excessive production failures",
    },
    "High/Low Pressure System": {
        2: "0% delta change from ambient pressure",
        4: "20% delta change from ambient pressure",
        6: "50% delta change from ambient - Gases under pressure (H280, H284); chemical under pressure may explode if heated",
        8: "100% delta change from ambient - Flammable chemical under pressure may explode if heated (H283)",
        10: ">100% delta change from ambient - Extremely flammable chemical under pressure may explode if heated (H282)",
    },
    "High/Low Temperature System": {
        2: "0% delta change from ambient temperature",
        4: "20% delta change from ambient temperature",
        6: "50% delta change from ambient - Contains refrigerated gas; may cause cryogenic burns or injury (H281)",
        8: "100% delta change from ambient temperature",
        10: ">100% delta change from ambient temperature",
    },
    "Water Use": {
        2: ">75% water reduction; >75% reuse",
        4: "50% water reduction; 50% reuse",
        6: "<0-25% water reduction; <25% reuse",
        8: "25% water increase; 25% discharge",
        10: ">50% water increase; >50% discharge",
    },
    "Energy Use": {
        2: ">50% energy reduction; 30% renewable energy",
        4: "25% energy reduction; 25% renewable energy",
        6: "<0-10% energy reduction; 15% renewable energy",
        8: "25% energy increase; 5% renewable energy",
        10: ">50% energy increase; 0% renewable energy",
    },
}

LIFE_CYCLE_FACTORS_MATRIX: Dict[str, Dict[int, str]] = {
    "Upstream Effects": {
        2: "Eliminates suppliers' use of hazardous materials AND reduces use of energy, water, and resources",
        4: "Eliminates suppliers' use of hazardous materials OR reduces use of energy, water, and resources",
        6: "Process reduces suppliers' use of hazardous materials, energy, water and other resources",
        8: "Process requires suppliers to use hazardous materials OR excess energy, water, and other resources",
        10: "Process requires suppliers to use hazardous materials AND excess energy, water, and other resources",
    },
    "Consumer Hazard": {
        2: "Product contains no hazardous components",
        4: "Product contains hazardous components with no consumer/user exposure potential",
        6: "Product contains hazardous components with low consumer/user exposure potential",
        8: "Product contains hazardous components with moderate consumer/user exposure potential",
        10: "Product contains hazardous components with consumer/user exposure potential",
    },
    "Disposal Hazard": {
        2: "Prevents/reduces amount of waste material being created",
        4: "Creates some concern for air, water or land",
        6: "Creates concern for air, water or land and disposed of as hazardous waste",
        8: "Causes contamination of air, water OR land",
        10: "Causes contamination of air, water AND land",
    },
    "Recycling": {
        2: "100% recyclable at end of life; uses products with 90% recycled material",
        4: "75% recyclable at end of life; uses products with 75% recycled material",
        6: "50% recyclable at end of life; uses products with 25% recycled material",
        8: "25% recyclable at end of life; uses products with <25% recycled material",
        10: "<25% recyclable at end of life; uses products with 0% recycled material",
    },
    "Renewable to Nonrenewable Resource": {
        2: "75% renewable materials - renewable",
        4: "50% renewable materials - contains 50% renewable materials",
        6: "25% renewable materials - contains 25% renewable materials",
        8: "5% renewable materials - contains 10% renewable materials",
        10: "0% renewable materials - nonrenewable materials",
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
