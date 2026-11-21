"""Import assessment records directly for student work cards."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from . import config
from .roster import normalise

SCORE_FIELDS = ("activity1", "activity2", "practical_test", "short_test", "projects")
SCORE_LIMITS = {"activity1": 10, "activity2": 10, "practical_test": 10,
                "short_test": 10, "projects": 20}
CARD_STYLES = {
    "classic": "الأخضر الرسمي",
    "ocean": "الأزرق الهادئ",
    "burgundy": "العنابي",
    "olive": "الزيتوني الذهبي",
}


def _style_key(class_info: str, section_label: str) -> str:
    return f"{normalise(class_info).casefold()}::{normalise(section_label).casefold()}"


def get_card_style(class_info: str, section_label: str) -> str:
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    styles = prefs.get("student_card_styles", {}) if isinstance(prefs, dict) else {}
    style = styles.get(_style_key(class_info, section_label), "classic") if isinstance(styles, dict) else "classic"
    return style if style in CARD_STYLES else "classic"


def set_card_style(class_info: str, section_label: str, style: str) -> str:
    if style not in CARD_STYLES:
        raise ValueError("نمط البطاقة المحدد غير متاح.")
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    prefs = prefs if isinstance(prefs, dict) else {}
    styles = prefs.get("student_card_styles", {})
    styles = styles if isinstance(styles, dict) else {}
    styles[_style_key(class_info, section_label)] = style
    prefs["student_card_styles"] = styles
    config.save_json(config.user_dir() / "tools.json", prefs)
    return style


def _number(value) -> float | int | None:
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return 0
    return int(n) if n.is_integer() else n


def parse_assessment(path: str | Path, semester: int, section: dict | None = None) -> dict:
    path = Path(path)
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"تعذّر فتح سجل التقويم: {exc}") from exc
    # Assessment exports use several naming conventions. The official
    # workbook supplied by the school calls its sheets "الفصل الأول" and
    # "الفصل الثاني", and keeps the grade in the sheet cells instead of its
    # title. Ignore annual-summary sheets and use the requested semester.
    expected = f"الثاني عشر - ف{semester}"
    ws = wb[expected] if expected in wb.sheetnames else None
    if ws is None:
        semester_words = {1: ("الأول", "الاول", "1"),
                          2: ("الثاني", "2")}[int(semester)]
        for sheet in wb.worksheets:
            title = normalise(sheet.title)
            is_semester = any(word in title for word in semester_words)
            is_annual = "سنوي" in title or "سنوية" in title
            if not is_semester or is_annual:
                continue
            # When the title does not specify the grade, check the grade
            # metadata row used by the school's assessment template.
            metadata = " ".join(normalise(str(v or ""))
                                for v in next(sheet.iter_rows(min_row=2, max_row=3,
                                                              max_col=4, values_only=True), ()))
            if "12" in metadata or "الثاني عشر" in metadata or "الصف" not in metadata:
                ws = sheet
                break
    if ws is None:
        wb.close()
        raise ValueError(f"لم أجد ورقة الصف الثاني عشر للفصل {semester} في الملف.")
    metadata_rows = list(ws.iter_rows(min_row=2, max_row=3, max_col=3, values_only=True))
    class_info = " ".join(normalise(str(v or "")) for row in metadata_rows for v in row if v)
    section_label = normalise(str(metadata_rows[1][1] or "")) if len(metadata_rows) > 1 and len(metadata_rows[1]) > 1 else ""
    records = []
    for row in ws.iter_rows(min_row=6, values_only=True):
        name = normalise(str(row[1] or "")) if len(row) > 1 else ""
        if len(name.split()) < 2:
            continue
        scores = {
            "activity1": _number(row[2] if len(row) > 2 else None),
            "activity2": _number(row[3] if len(row) > 3 else None),
            "practical_test": _number(row[5] if len(row) > 5 else None),
            "short_test": _number(row[6] if len(row) > 6 else None),
            "projects": _number(row[7] if len(row) > 7 else None),
        }
        records.append({"official_name": name, "scores": scores})
    wb.close()
    if not records:
        raise ValueError("لم أجد أسماء طلبة في ورقة الصف الثاني عشر.")
    return {"sheet": ws.title, "class_info": class_info,
            "section_label": section_label, "records": records}
