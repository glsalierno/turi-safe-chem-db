"""
IUCLID 6 dossier endpoint extractor.

Parses .i6z dossiers and extracts typed toxicological and physicochemical
endpoints for use with the P2OASys scorer.

Endpoints extracted:
- Acute toxicity: oral LD50, dermal LD50, inhalation LC50
- Aquatic toxicity: fish/daphnia/algae LC50/EC50
- Repeated-dose toxicity: NOAEL/LOAEL
- Physicochemical: flash point, vapour pressure, log Kow, BCF
- Biodegradability

Based on IUCLID 6.9 / definition 7.x XML structure.
"""

from __future__ import annotations

import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterator

from packages.iuclid_core.phrase_mapper import PhraseMapper, get_phrase_mapper

logger = logging.getLogger(__name__)


RESULT_BLOCKS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "AcuteToxicityOral": ("EffectLevels", "EffectLevel", ("Endpoint", "Sex")),
    "AcuteToxicityDermal": ("EffectLevels", "EffectLevel", ("Endpoint", "Sex")),
    "AcuteToxicityInhalation": (
        "EffectLevels",
        "EffectLevel",
        ("Endpoint", "Sex", "ExpDuration"),
    ),
    "RepeatedDoseToxicityOral": (
        "EffectLevels/Efflevel",
        "EffectLevel",
        ("Endpoint", "Sex"),
    ),
    "RepeatedDoseToxicityInhalation": (
        "EffectLevels/Efflevel",
        "EffectLevel",
        ("Endpoint", "Sex"),
    ),
    "RepeatedDoseToxicityDermal": (
        "EffectLevels/Efflevel",
        "EffectLevel",
        ("Endpoint", "Sex"),
    ),
    "ShortTermToxicityToFish": (
        "EffectConcentrations",
        "EffectConc",
        ("Endpoint", "Duration"),
    ),
    "LongTermToxToFish": (
        "EffectConcentrations",
        "EffectConc",
        ("Endpoint", "Duration"),
    ),
    "ShortTermToxicityToAquaInv": (
        "EffectConcentrations",
        "EffectConc",
        ("Endpoint", "Duration"),
    ),
    "LongTermToxicityToAquaInv": (
        "EffectConcentrations",
        "EffectConc",
        ("Endpoint", "Duration"),
    ),
    "ToxicityToAquaticAlgae": (
        "EffectConcentrations",
        "EffectConc",
        ("Endpoint", "Duration"),
    ),
    "FlashPoint": ("FlashPoint", "FPoint", ("AtmPressure",)),
    "Vapour": ("Vapourpr", "Pressure", ("TempQualifier",)),
    "Partition": ("Partcoeff", "Partition", ("Type", "Temp")),
    "BioaccumulationAquaticSediment": (
        "Results",
        "BcfAquaticOrganisms",
        ("TimeOfPlateau", "Basis"),
    ),
    "BiodegradationInWaterScreeningTests": (
        "Biodegradation",
        "Degr",
        ("Degrad", "SamplingTime"),
    ),
    "BoilingPoint": ("Boilingpt", "Boilingpt", ("AtmPressure",)),
    "WaterSolubility": ("WaterSolubility", "Solubility", ("Temp",)),
    "Density": ("Density", "Density", ("Temp",)),
}


@dataclass
class RangeValue:
    """IUCLID range/quantity value."""

    lower_qualifier: str = ""
    lower: float | None = None
    upper_qualifier: str = ""
    upper: float | None = None
    unit_code: str = ""
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    
    @property
    def numeric_value(self) -> float | None:
        """Get the primary numeric value (lower, or upper if lower is None)."""
        return self.lower if self.lower is not None else self.upper
    
    def __str__(self) -> str:
        parts = []
        if self.lower_qualifier:
            parts.append(self.lower_qualifier)
        if self.lower is not None:
            parts.append(str(self.lower))
        if self.upper is not None:
            if parts:
                parts.append("-")
            if self.upper_qualifier:
                parts.append(self.upper_qualifier)
            parts.append(str(self.upper))
        if self.unit:
            parts.append(self.unit)
        return " ".join(parts)


@dataclass
class EndpointRecord:
    """Extracted endpoint record from IUCLID dossier."""

    dossier_uuid: str
    document: str
    subtype: str
    study_result_type: str = ""
    purpose_flag: str = ""
    reliability: str = ""
    species: str = ""
    route: str = ""
    key_result: bool = False
    value: RangeValue | None = None
    endpoint: str = ""
    duration: RangeValue | None = None
    sex: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "dossier_uuid": self.dossier_uuid,
            "document": self.document,
            "subtype": self.subtype,
            "study_result_type": self.study_result_type,
            "purpose_flag": self.purpose_flag,
            "reliability": self.reliability,
            "species": self.species,
            "route": self.route,
            "key_result": self.key_result,
            "value": self.value.to_dict() if self.value else None,
            "endpoint": self.endpoint,
            "sex": self.sex,
        }
        if self.duration:
            d["duration"] = self.duration.to_dict()
        d.update(self.extras)
        return d
    
    @property
    def reliability_score(self) -> int | None:
        """Extract Klimisch score (1-4) from reliability string."""
        if not self.reliability:
            return None
        for i in range(1, 5):
            if self.reliability.startswith(str(i)):
                return i
        return None
    
    @property
    def is_reliable(self) -> bool:
        """Check if reliability is Klimisch 1 or 2."""
        score = self.reliability_score
        return score is not None and score <= 2


def _loc(tag: str) -> str:
    """Get local name from namespaced tag."""
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element | None, name: str) -> ET.Element | None:
    """Get child element by local name."""
    if el is None:
        return None
    for c in el:
        if _loc(c.tag) == name:
            return c
    return None


def _path(el: ET.Element | None, path: str) -> ET.Element | None:
    """Navigate path of local names."""
    for part in path.split("/"):
        el = _child(el, part)
        if el is None:
            return None
    return el


def _txt(el: ET.Element | None, name: str) -> str:
    """Get text content of child element."""
    c = _child(el, name)
    return (c.text or "").strip() if c is not None and c.text else ""


def _is_range_element(el: ET.Element | None) -> bool:
    """Check if element is a range/quantity (not just a phrase code)."""
    if el is None:
        return False
    has_lower = _txt(el, "lowerValue") != ""
    has_upper = _txt(el, "upperValue") != ""
    has_unit = _txt(el, "unitCode") != ""
    has_qualifiers = (
        _txt(el, "lowerQualifier") != "" or _txt(el, "upperQualifier") != ""
    )
    return has_lower or has_upper or has_unit or has_qualifiers


def _parse_range(
    el: ET.Element | None, phrases: PhraseMapper
) -> RangeValue | None:
    """Parse IUCLID range/quantity element."""
    if el is None:
        return None
    
    if not _is_range_element(el):
        return None
    
    lo = _txt(el, "lowerValue") or _txt(el, "value")
    hi = _txt(el, "upperValue")
    if not lo and not hi:
        return None
    
    unit_code = _txt(el, "unitCode")
    
    def parse_float(s: str) -> float | None:
        if not s:
            return None
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None
    
    return RangeValue(
        lower_qualifier=_txt(el, "lowerQualifier"),
        lower=parse_float(lo),
        upper_qualifier=_txt(el, "upperQualifier"),
        upper=parse_float(hi),
        unit_code=unit_code,
        unit=phrases.decode(unit_code) if unit_code else "",
    )


def _phrase(el: ET.Element | None, phrases: PhraseMapper) -> str:
    """Decode phrase code from element."""
    code = _txt(el, "value") if el is not None else ""
    return phrases.decode(code) if code else ""


def iter_esr_documents(
    i6z_path: Path | io.BytesIO,
) -> Iterator[tuple[str, str, ET.Element]]:
    """
    Iterate over ENDPOINT_STUDY_RECORD documents in an .i6z dossier.
    
    Yields: (document_name, subtype, content_element)
    """
    with zipfile.ZipFile(i6z_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".i6d"):
                continue
            try:
                root = ET.fromstring(zf.read(name))
                content = next(
                    (
                        e
                        for e in root.iter()
                        if _loc(e.tag).startswith("ENDPOINT_STUDY_RECORD.")
                    ),
                    None,
                )
                if content is not None:
                    yield name, _loc(content.tag).split(".", 1)[1], content
            except ET.ParseError as e:
                logger.debug("Failed to parse %s: %s", name, e)


def extract_dossier(
    i6z_path: Path | io.BytesIO,
    dossier_uuid: str | None = None,
    phrases: PhraseMapper | None = None,
) -> list[EndpointRecord]:
    """
    Extract all endpoints from an .i6z dossier.
    
    Args:
        i6z_path: Path to .i6z file or BytesIO containing it
        dossier_uuid: Override UUID (defaults to filename stem)
        phrases: PhraseMapper instance (defaults to global)
    
    Returns:
        List of EndpointRecord objects
    """
    if phrases is None:
        phrases = get_phrase_mapper()
    
    if dossier_uuid is None:
        if isinstance(i6z_path, Path):
            dossier_uuid = i6z_path.stem
        else:
            dossier_uuid = "unknown"
    
    records: list[EndpointRecord] = []
    
    for doc_name, subtype, content in iter_esr_documents(i6z_path):
        admin = _child(content, "AdministrativeData")
        mm = _child(content, "MaterialsAndMethods")
        
        base_study_type = _phrase(_child(admin, "StudyResultType"), phrases)
        base_purpose = _phrase(_child(admin, "PurposeFlag"), phrases)
        base_reliability = _phrase(_child(admin, "Reliability"), phrases)
        
        base_species = (
            _phrase(_path(mm, "TestAnimals/Species"), phrases)
            or _phrase(_path(mm, "TestOrganisms/TestOrganismsSpecies"), phrases)
        )
        base_route = _phrase(
            _path(mm, "AdministrationExposure/RouteOfAdministration"), phrases
        )
        
        spec = RESULT_BLOCKS.get(subtype)
        res = _child(content, "ResultsAndDiscussion")
        if spec is None or res is None:
            continue
        
        container_path, value_el_name, extras = spec
        cont = _path(res, container_path)
        if cont is None:
            continue
        
        for entry in cont:
            if _loc(entry.tag) != "entry":
                continue
            
            val = _parse_range(_child(entry, value_el_name), phrases)
            if val is None:
                continue
            
            record = EndpointRecord(
                dossier_uuid=dossier_uuid,
                document=doc_name,
                subtype=subtype,
                study_result_type=base_study_type,
                purpose_flag=base_purpose,
                reliability=base_reliability,
                species=base_species,
                route=base_route,
                key_result=_txt(entry, "KeyResult").lower() == "true",
                value=val,
            )
            
            for extra_name in extras:
                xe = _child(entry, extra_name)
                if xe is None:
                    continue
                
                if extra_name == "Endpoint":
                    record.endpoint = _phrase(xe, phrases)
                elif extra_name == "Sex":
                    record.sex = _phrase(xe, phrases)
                elif extra_name == "Duration" or extra_name == "ExpDuration":
                    record.duration = _parse_range(xe, phrases)
                else:
                    rng = _parse_range(xe, phrases)
                    if rng is not None:
                        record.extras[extra_name.lower()] = rng.to_dict()
                    else:
                        decoded = _phrase(xe, phrases)
                        if decoded:
                            record.extras[extra_name.lower()] = decoded
            
            records.append(record)
    
    return records


def extract_endpoints_for_cas(
    cas: str,
    dossier_source: Path | None = None,
    dossier_index: Path | None = None,
) -> list[dict]:
    """
    Extract all endpoints for a CAS number from configured dossier source.
    
    Args:
        cas: CAS number to look up
        dossier_source: Override dossier source path
        dossier_index: Override dossier index path
    
    Returns:
        List of endpoint dicts
    """
    from packages.iuclid_core.config import get_config
    from packages.iuclid_core.index import get_dossier_uuids_for_cas, get_dossier_path
    
    config = get_config()
    if dossier_source is None:
        dossier_source = config.dossier_source
    if dossier_index is None:
        dossier_index = config.dossier_index
    
    if dossier_source is None:
        logger.debug("No dossier source configured for CAS lookup: %s", cas)
        return []
    
    uuids = get_dossier_uuids_for_cas(cas, dossier_index)
    if not uuids:
        logger.debug("No dossiers found for CAS: %s", cas)
        return []
    
    all_records: list[dict] = []
    phrases = get_phrase_mapper()
    
    for uuid in uuids:
        dossier_path = get_dossier_path(uuid, dossier_source)
        if dossier_path is None:
            logger.debug("Dossier not found: %s", uuid)
            continue
        
        try:
            if isinstance(dossier_path, io.BytesIO):
                records = extract_dossier(dossier_path, uuid, phrases)
            else:
                records = extract_dossier(dossier_path, uuid, phrases)
            all_records.extend(r.to_dict() for r in records)
        except Exception as e:
            logger.warning("Failed to extract dossier %s: %s", uuid, e)
    
    return all_records
