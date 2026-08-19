from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import pymupdf

from mining_rights_agent.common.models import (
    GradeUnit,
    MetalUnit,
    ReportingCode,
    ResourceRecord,
)

CLASS_PATTERN = re.compile(r"\b(indicated|inferred)\b", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?")


@dataclass(frozen=True)
class UnitContext:
    grade_unit: GradeUnit
    metal_unit: MetalUnit | None
    tonnage_scale: float
    metal_scale: float


def _number(value: str) -> float:
    normalized = value.replace(",", "").strip("()")
    result = float(normalized)
    return abs(result)


def _detect_units(text: str) -> UnitContext:
    lowered = text.lower()
    grade_unit: GradeUnit
    if "li2o" in lowered:
        grade_unit = "% Li2O"
    elif "g/t" in lowered and ("au" in lowered or "gold" in lowered):
        grade_unit = "g/t Au"
    elif "% cu" in lowered or "copper grade" in lowered:
        grade_unit = "% Cu"
    else:
        grade_unit = "unknown"

    metal_unit: MetalUnit | None
    if "koz" in lowered or "ounces" in lowered or " oz" in lowered:
        metal_unit = "oz"
        metal_scale = 1000.0 if "koz" in lowered else 1.0
    elif " kt" in lowered and grade_unit in {"% Cu", "% Li2O"}:
        metal_unit = "t"
        metal_scale = 1000.0
    elif "tonnes" in lowered or " t " in lowered:
        metal_unit = "t"
        metal_scale = 1.0
    else:
        metal_unit = None
        metal_scale = 1.0

    tonnage_scale = 0.001 if " kt" in lowered and " mt" not in lowered else 1.0
    return UnitContext(grade_unit, metal_unit, tonnage_scale, metal_scale)


def _reporting_code(text: str) -> ReportingCode:
    lowered = text.lower()
    if "ni 43-101" in lowered or "ni 43 101" in lowered:
        return "NI 43-101"
    if "jorc" in lowered:
        return "JORC"
    return "Unknown"


def extract_resource_records(pdf_bytes: bytes, source_url: str) -> list[ResourceRecord]:
    document: Any = pymupdf.open(  # type: ignore[no-untyped-call]
        stream=pdf_bytes, filetype="pdf"
    )
    records: list[ResourceRecord] = []
    seen: set[tuple[str, int, float, float]] = set()
    document_prefix = "\n".join(page.get_text("text") for page in document[:3])
    reporting_code = _reporting_code(document_prefix)

    for page_number, page in enumerate(document, start=1):
        page_text = page.get_text("text")
        if not CLASS_PATTERN.search(page_text):
            continue
        units = _detect_units(page_text)
        candidate_lines = page_text.splitlines()
        try:
            for table in page.find_tables().tables:
                for row in table.extract():
                    candidate_lines.append(" ".join(str(cell or "") for cell in row))
        except Exception:
            # Some scanned or malformed pages cannot be table-detected; text rows still work.
            pass
        for line in candidate_lines:
            match = CLASS_PATTERN.search(line)
            if not match:
                continue
            values = [_number(value) for value in NUMBER_PATTERN.findall(line[match.end() :])]
            if len(values) < 2:
                continue

            classification: Literal["Indicated", "Inferred"] = (
                "Indicated" if match.group(1).casefold() == "indicated" else "Inferred"
            )
            tonnage_mt = values[0] * units.tonnage_scale
            grade_value = values[1]
            contained_metal = values[2] * units.metal_scale if len(values) >= 3 else None
            key = (classification, page_number, tonnage_mt, grade_value)
            if key in seen or tonnage_mt <= 0 or grade_value <= 0:
                continue
            seen.add(key)
            confidence = 0.8 if units.grade_unit != "unknown" else 0.55
            records.append(
                ResourceRecord(
                    classification=classification,
                    tonnage_mt=tonnage_mt,
                    grade_value=grade_value,
                    grade_unit=units.grade_unit,
                    contained_metal=contained_metal,
                    metal_unit=units.metal_unit if contained_metal is not None else None,
                    reporting_code=reporting_code,
                    source_url=source_url,
                    source_page=page_number,
                    source_text=line.strip(),
                    confidence=confidence,
                )
            )
    return records
