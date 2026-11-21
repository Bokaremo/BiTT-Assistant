"""Folder naming rules (Arabic / English)."""

from __future__ import annotations

import re

GRADES_AR = {
    1: "أول", 2: "ثاني", 3: "ثالث", 4: "رابع", 5: "خامس", 6: "سادس",
    7: "سابع", 8: "ثامن", 9: "تاسع", 10: "عاشر", 11: "حادي عشر", 12: "ثاني عشر",
}

YEAR_RE = re.compile(r"^(\d{4})-(\d{4})$")


def valid_year(value: str) -> bool:
    m = YEAR_RE.match(value or "")
    return bool(m) and int(m.group(2)) == int(m.group(1)) + 1


def term_folder(grade: int, semester: int, academic_year: str, lang: str) -> str:
    """G11_S1_2026-2027  /  حادي عشر_ف1_2026-2027"""
    if grade not in GRADES_AR:
        raise ValueError("grade must be 1-12")
    if semester not in (1, 2):
        raise ValueError("semester must be 1 or 2")
    if not valid_year(academic_year):
        raise ValueError("academic year must look like 2026-2027")
    if lang == "ar":
        return f"{GRADES_AR[grade]}_ف{semester}_{academic_year}"
    if lang == "en":
        return f"G{grade}_S{semester}_{academic_year}"
    raise ValueError("lang must be ar or en")


def section_folder(grade: int, label: str, semester: int,
                   academic_year: str, lang: str,
                   include_label: bool = True) -> str:
    """Unique term folder for one grade section in the device-first tree."""
    term_folder(grade, semester, academic_year, lang)  # validate shared fields
    if not include_label:
        return term_folder(grade, semester, academic_year, lang)
    safe_label = " ".join(str(label or "").split()).replace("/", "-").replace("\\", "-")
    if not safe_label:
        raise ValueError("section label is required")
    # Imported MOE labels commonly repeat their grade (for example 12-2).
    # Keep only the actual section token so a multi-section folder says G12-2,
    # while a one-section grade omits the token altogether.
    prefix = re.fullmatch(rf"{grade}[-_](.+)", safe_label)
    if prefix:
        safe_label = prefix.group(1)
    if lang == "ar":
        return f"{GRADES_AR[grade]}_{safe_label}_ف{semester}_{academic_year}"
    if lang == "en":
        return f"G{grade}-{safe_label}_S{semester}_{academic_year}"
    raise ValueError("lang must be ar or en")


def tree_root_folder(semester: int, academic_year: str, lang: str) -> str:
    """Dedicated parent directory for the whole device-first tree."""
    if semester not in (1, 2):
        raise ValueError("semester must be 1 or 2")
    if not valid_year(academic_year):
        raise ValueError("academic year must look like 2026-2027")
    if lang == "ar":
        return f"شجرة الطلبة_ف{semester}_{academic_year}"
    if lang == "en":
        return f"BiTT_Students_S{semester}_{academic_year}"
    raise ValueError("lang must be ar or en")
