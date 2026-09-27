"""
IUCLID phrase code decoder.

Decodes IUCLID picklist codes (e.g., "2081" → "mg/kg bw") using either:
1. A bundled minimal phrase map (covers common units, endpoints, species)
2. The full IUCLID format pack if IUCLID_FORMAT_DIR is configured

The bundled map is derived from IUCLID 6.9.0 format pack for offline use.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.iuclid_core.config import IUCLIDConfig

logger = logging.getLogger(__name__)

BUNDLED_PHRASES: dict[str, str] = {
    "4": "#2",
    "5": "#3",
    "8": "#6",
    "14": "(Q)SAR",
    "16": "1 (reliable without restriction)",
    "18": "2 (reliable with restrictions)",
    "22": "3 (not reliable)",
    "24": "4 (not assignable)",
    "30": "<=",
    "103": "Artemia salina",
    "128": "BOD5",
    "252": "Chlorella pyrenoidosa",
    "300": "Cyprinus auratus",
    "326": "Daphnia magna",
    "360": "EC0",
    "361": "EC10",
    "362": "EC100",
    "365": "EC50",
    "857": "IC50",
    "921": "key study",
    "931": "LD50",
    "932": "LC50",
    "1129": "NOEC",
    "1130": "NOAEL",
    "1131": "LOAEL",
    "1132": "LOEC",
    "1133": "NOAEC",
    "1134": "LOAEC",
    "1187": "OECD Guideline 105 (Water Solubility)",
    "1209": "OECD Guideline 211 (Daphnia magna Reproduction Test)",
    "1224": "OECD Guideline 301 B (Ready Biodegradability: CO2 Evolution Test)",
    "1225": "OECD Guideline 301 C (Ready Biodegradability: Modified MITI Test (I))",
    "1249": "OECD Guideline 401 (Acute Oral Toxicity)",
    "1578": "standard acute method",
    "1590": "supporting study",
    "1680": "according to guideline",
    "1708": "aerobic",
    "1740": "atm",
    "1758": "test mat.",
    "1769": "biomass",
    "1802": "closed cup",
    "1839": "d",
    "1841": "density",
    "1880": "equivalent or similar to guideline",
    "1895": "experimental study",
    "1904": "female",
    "1920": "freshwater",
    "1929": "g/cm³",
    "1935": "g/L",
    "1951": "growth rate",
    "1976": "h",
    "1997": "inherently biodegradable",
    "2019": "kPa",
    "2020": "Pa",
    "2043": "log Pow",
    "2052": "male/female",
    "2053": "male",
    "2074": "mg O2/g test mat.",
    "2081": "mg/kg bw",
    "2082": "mg/kg bw/day",
    "2083": "mg/kg bw/week",
    "2098": "mg/L",
    "2100": "mg/L air",
    "2103": "mg/m³",
    "2104": "mg/m³ air",
    "2119": "mL/kg bw",
    "2121": "mm Hg",
    "2148": "negative",
    "2158": "no",
    "2178": "nominal",
    "2195": "not classified",
    "2197": "not examined",
    "2207": "not specified",
    "2214": "octanol-water",
    "2231": "oral: gavage",
    "2232": "oral: feed",
    "2233": "oral: drinking water",
    "2234": "oral: capsule",
    "2235": "oral: unspecified",
    "2301": "rabbit",
    "2305": "readily biodegradable",
    "2326": "saltwater",
    "2339": "semi-static",
    "2392": "static",
    "2474": "with",
    "2475": "with and without",
    "2480": "yes",
    "2490": "mean",
    "2493": "°C",
    "2500": "µg/L",
    "2678": "acute toxicity: oral",
    "2679": "acute toxicity: dermal",
    "2680": "acute toxicity: inhalation",
    "2719": "boiling point",
    "2893": "long-term toxicity to aquatic invertebrates",
    "2915": "mono-constituent substance",
    "3334": "short-term toxicity to aquatic invertebrates",
    "3335": "short-term toxicity to fish",
    "3336": "long-term toxicity to fish",
    "3384": "toxicity to aquatic algae and cyanobacteria",
    "3415": "vapour pressure",
    "3427": "water solubility",
    "3456": "activated sludge, domestic (adaptation not specified)",
    "3484": "rabbit",
    "3485": "rat",
    "3494": "Chinese hamster Ovary (CHO)",
    "3547": "rabbit",
    "3561": "New Zealand White",
    "3574": "Wistar",
    "3887": "K",
    "3895": "Desmodesmus subspicatus (previous name: Scenedesmus subspicatus)",
    "4038": "meas. (not specified)",
    "4790": "flask method",
    "5666": "partition coefficient",
    "59": "inhalation: aerosol",
    "60": "inhalation: dust",
    "61": "inhalation: gas",
    "62": "inhalation: vapour",
    "63": "inhalation: vapour (nose only)",
    "64": "inhalation: vapour (whole body)",
    "65": "dermal",
    "2279": "ppm",
    "2280": "ppb",
    "60752": "biodegradation in water: ready biodegradability",
    "61929": "biodegradation in water: screening tests",
    "61933": "flash point",
}


def _java_unescape(s: str) -> str:
    """Unescape Java properties unicode escapes like \\u00B0."""
    def repl(m: re.Match) -> str:
        return chr(int(m.group(1), 16))
    return re.sub(r"\\u([0-9A-Fa-f]{4})", repl, s)


def _load_format_pack_phrases(format_dir: Path) -> dict[str, str]:
    """
    Load phrase codes from IUCLID format pack .properties files.
    
    Expects structure: <format_dir>/configuration/provider-*/phrases/*.properties
    """
    phrases: dict[str, str] = {}
    config_dir = format_dir / "configuration"
    if not config_dir.is_dir():
        return phrases
    
    for provider_dir in config_dir.glob("provider-*"):
        phrases_dir = provider_dir / "phrases"
        if not phrases_dir.is_dir():
            continue
        for prop_file in phrases_dir.glob("*.properties"):
            try:
                text = prop_file.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        code, label = line.split("=", 1)
                        code = code.strip()
                        label = _java_unescape(label.strip())
                        if code and label:
                            phrases[code] = label
            except Exception as e:
                logger.debug("Failed to load %s: %s", prop_file, e)
    
    return phrases


class PhraseMapper:
    """
    IUCLID phrase code decoder.
    
    Decodes numeric phrase codes to human-readable labels.
    Falls back to bundled map if format pack not available.
    """
    
    def __init__(self, phrases: dict[str, str] | None = None):
        """
        Initialize with optional phrase map.
        
        If phrases is None, uses bundled minimal map.
        """
        self._phrases = phrases if phrases is not None else dict(BUNDLED_PHRASES)
    
    @classmethod
    def from_format_pack(cls, format_dir: Path) -> "PhraseMapper":
        """Load phrases from IUCLID format pack directory."""
        phrases = _load_format_pack_phrases(format_dir)
        phrases.update(BUNDLED_PHRASES)
        return cls(phrases)
    
    @classmethod
    def from_json(cls, json_path: Path) -> "PhraseMapper":
        """Load phrases from a JSON file."""
        with open(json_path, encoding="utf-8") as f:
            phrases = json.load(f)
        return cls(phrases)
    
    def decode(self, code: str | None) -> str:
        """
        Decode a phrase code to its label.
        
        Returns the original code if not found in map.
        """
        if code is None:
            return ""
        code = str(code).strip()
        if not code:
            return ""
        label = self._phrases.get(code, code)
        return _java_unescape(label)
    
    def get(self, code: str, default: str = "") -> str:
        """Get phrase label with default."""
        result = self.decode(code)
        return result if result != code else default
    
    def __contains__(self, code: str) -> bool:
        return str(code).strip() in self._phrases
    
    def __len__(self) -> int:
        return len(self._phrases)


_cached_mapper: PhraseMapper | None = None


def get_phrase_mapper(config: "IUCLIDConfig | None" = None) -> PhraseMapper:
    """
    Get the configured phrase mapper (cached).
    
    Uses format pack if IUCLID_FORMAT_DIR is set, otherwise bundled map.
    """
    global _cached_mapper
    
    if _cached_mapper is not None:
        return _cached_mapper
    
    if config is None:
        from packages.iuclid_core.config import get_config
        config = get_config()
    
    if config.format_dir and config.format_dir.is_dir():
        logger.debug("Loading phrases from format pack: %s", config.format_dir)
        _cached_mapper = PhraseMapper.from_format_pack(config.format_dir)
    else:
        logger.debug("Using bundled phrase map (%d codes)", len(BUNDLED_PHRASES))
        _cached_mapper = PhraseMapper()
    
    return _cached_mapper


def reset_phrase_mapper() -> None:
    """Reset cached phrase mapper (for testing)."""
    global _cached_mapper
    _cached_mapper = None
