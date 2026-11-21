"""Create project-group assessment workbooks from the supplied official forms."""

from __future__ import annotations

from copy import copy
import re
from pathlib import Path

from openpyxl import load_workbook

from . import config
from .roster import normalise


def _template_path(semester: int) -> Path:
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    path = base / "biit" / "web" / "templates" / f"project_semester_{semester}.xlsx"
    if not path.is_file():
        raise FileNotFoundError(f"قالب استمارة الفصل {semester} غير موجود.")
    return path


def _safe_piece(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    return value.strip(" .")[:80] or "شعبة"


def output_directory() -> str:
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    return str(prefs.get("project_forms_dir", "")) if isinstance(prefs, dict) else ""


def default_customization() -> dict:
    return {
        "project_form_topic_1": "", "project_form_topic_2": "",
        "project_form_topic_3": "", "project_form_topic_4": "",
        "project_form_section_format": "{section}",
        "project_form_group_format": "{section}_G{group:02d}",
        "project_form_group_size": 5,
    }


def load_customization() -> dict:
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    stored = prefs.get("project_forms_customization", {}) if isinstance(prefs, dict) else {}
    merged = {**default_customization(), **(stored if isinstance(stored, dict) else {})}
    clean, _ = validate_customization(merged)
    return clean


def validate_customization(data: dict) -> tuple[dict, dict]:
    clean, errors = default_customization(), {}
    for key in ("project_form_topic_1", "project_form_topic_2",
                "project_form_topic_3", "project_form_topic_4"):
        value = " ".join(str(data.get(key, "")).split())
        if len(value) > 80:
            errors[key] = "اسم المشروع لا يتجاوز 80 حرفًا."
        clean[key] = value[:80]
    for key, label, default, allowed in (
        ("project_form_section_format", "الشعبة", "{section}", {"section", "grade"}),
        ("project_form_group_format", "رمز المجموعة", "{section}_G{group:02d}", {"section", "grade", "group"}),
    ):
        value = str(data.get(key, default)).strip() or default
        fields = set(re.findall(r"\{(section|grade|group)(?::[^{}]+)?\}", value))
        remainder = re.sub(r"\{(?:section|grade|group)(?::[^{}]+)?\}", "", value)
        if len(value) > 80 or not fields or not fields <= allowed or "{" in remainder or "}" in remainder:
            errors[key] = f"تنسيق {label} غير صالح. استخدم الحقول المتاحة مثل {{section}} و{{group}}."
            value = default
        clean[key] = value
    try:
        group_size = int(data.get("project_form_group_size", 5))
        if group_size not in range(1, 6):
            raise ValueError
        clean["project_form_group_size"] = group_size
    except (TypeError, ValueError):
        errors["project_form_group_size"] = "عدد أعضاء المجموعة من 1 إلى 5."
    return clean, errors


def save_customization(data: dict) -> dict:
    clean, errors = validate_customization(data)
    if errors:
        raise ValueError("راجع إعدادات الاستمارة.")
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    prefs = prefs if isinstance(prefs, dict) else {}
    prefs["project_forms_customization"] = clean
    config.save_json(config.user_dir() / "tools.json", prefs)
    return clean


def set_output_directory(path: str) -> str:
    target = Path(path).expanduser().resolve(strict=True)
    if not target.is_dir():
        raise ValueError("حدد مجلدًا موجودًا لحفظ الاستمارات.")
    prefs = config.load_json(config.user_dir() / "tools.json", {})
    prefs = prefs if isinstance(prefs, dict) else {}
    prefs["project_forms_dir"] = str(target)
    config.save_json(config.user_dir() / "tools.json", prefs)
    return str(target)


def preview(section: dict, group_size: int = 5,
            manual_groups: list[list[int]] | None = None) -> list[dict]:
    if int(section.get("grade", 0)) != 12:
        raise ValueError("استمارات المشاريع متاحة لشعب الصف الثاني عشر.")
    if not 1 <= int(group_size) <= 5:
        raise ValueError("عدد أعضاء المجموعة بين طالب واحد وخمسة.")
    source_students = section.get("students", [])
    if manual_groups is not None:
        if not isinstance(manual_groups, list) or not manual_groups:
            raise ValueError("أنشئ مجموعة واحدة على الأقل.")
        used: set[int] = set()
        groups = []
        for group_number, raw_indices in enumerate(manual_groups, 1):
            if not isinstance(raw_indices, list) or not 1 <= len(raw_indices) <= 5:
                raise ValueError(f"المجموعة {group_number}: اختر من طالب واحد إلى خمسة.")
            try:
                indices = [int(index) for index in raw_indices]
            except (TypeError, ValueError):
                raise ValueError("اختيار أحد الطلبة غير صالح.")
            if len(indices) != len(set(indices)) or any(i < 0 or i >= len(source_students) for i in indices):
                raise ValueError("تأكد من صحة الطلبة المختارين وعدم تكرارهم.")
            if used.intersection(indices):
                raise ValueError("لا يمكن إضافة الطالب إلى أكثر من مجموعة.")
            used.update(indices)
            names = [str(source_students[i].get("name", "")) for i in indices]
            names.sort(key=lambda name: normalise(name).casefold())
            groups.append({"group": group_number, "students": names})
        if len(used) != len(source_students):
            raise ValueError("أضف جميع طلبة الشعبة إلى المجموعات قبل المعاينة.")
        return groups

    students = sorted(source_students,
                      key=lambda st: normalise(st.get("name", "")).casefold())
    return [{"group": i // int(group_size) + 1,
             "students": [s.get("name", "") for s in students[i:i + int(group_size)]]}
            for i in range(0, len(students), int(group_size))]


def generate(section: dict, semester: int, academic_year: str,
             output_path: str, group_size: int = 5,
             settings: dict | None = None,
             customization: dict | None = None,
             manual_groups: list[list[int]] | None = None) -> dict:
    if int(section.get("grade", 0)) != 12:
        raise ValueError("استمارات المشاريع متاحة لشعب الصف الثاني عشر.")
    if semester not in (1, 2):
        raise ValueError("الفصل الدراسي غير صالح.")
    if not 1 <= int(group_size) <= 5:
        raise ValueError("عدد أعضاء المجموعة بين طالب واحد وخمسة.")
    dest = Path(output_path).expanduser().resolve(strict=True)
    if not dest.is_dir():
        raise ValueError("مجلد الحفظ غير موجود.")
    groups = preview(section, group_size, manual_groups)
    if not groups:
        raise ValueError("لا توجد أسماء طلبة في الشعبة المحددة.")
    template = _template_path(semester)
    settings = settings or config.load_settings()
    customization = customization or load_customization()
    label = _safe_piece(str(section["label"]))
    topic_index = (semester - 1) * 2
    section_format = customization.get("project_form_section_format", "{section}")
    group_format = customization.get("project_form_group_format", "{section}_G{group:02d}")
    semester_name = "الأول" if semester == 1 else "الثاني"
    header = (f"استمارة تقييم مشاريع طلاب الصف الثاني عشر لمادة تقنية المعلومات"
              f"\nالفصل الدراسي {semester_name} | العام الدراسي {academic_year.replace('-', ' / ')}")
    if settings.get("school_name"):
        header = f"{settings['school_name']} - {header}"
    created = []
    for group_index, group_plan in enumerate(groups):
        group_names = group_plan["students"]
        wb = load_workbook(template)
        for sheet_name in ("المشروع الأول", "المشروع الثاني"):
            ws = wb[sheet_name]
            ws["B1"] = header
            topic_key = f"project_form_topic_{topic_index + (1 if sheet_name == 'المشروع الأول' else 2)}"
            custom_topic = str(customization.get(topic_key) or "").strip()
            if custom_topic:
                ws["D3"] = custom_topic
            values = {"grade": section["grade"], "section": label,
                      "group": group_index + 1}
            ws["H3"] = section_format.format_map(values)
            ws["K3"] = group_format.format_map(values)
            ws["M3"] = len(group_names)
            for offset in range(5):
                row = 6 + offset
                ws.cell(row, 2).value = (group_names[offset] if
                                         sheet_name == "المشروع الأول" and offset < len(group_names) else
                                         (f'=IF(\'المشروع الأول\'!B{row}="","",\'المشروع الأول\'!B{row})'
                                          if sheet_name == "المشروع الثاني" else None))
                for col in range(3, 13):
                    ws.cell(row, col).value = None
                ws.cell(row, 13).value = f"=SUM(C{row}:L{row})"
            # The source template carries formatting down to row 1000. Keep
            # only the actual five student rows and remove unused columns.
            if ws.max_row > 10:
                ws.delete_rows(11, ws.max_row - 10)
            if ws.max_column > 13:
                ws.delete_cols(14, ws.max_column - 13)
            ws.sheet_view.showGridLines = False
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.orientation = "landscape"
            ws.page_setup.paperSize = ws.PAPERSIZE_A4
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 1
            ws.page_margins.left = ws.page_margins.right = 0.25
            ws.page_margins.top = ws.page_margins.bottom = 0.35
            ws.print_area = "A1:M10"
            for col, width in {"A": 6, "B": 37, "C": 12, "D": 13, "E": 13,
                               "F": 13, "G": 13, "H": 13, "I": 13,
                               "J": 13, "K": 13, "L": 13, "M": 9}.items():
                ws.column_dimensions[col].width = width
            ws.row_dimensions[1].height = 32
            ws.row_dimensions[2].height = 32
            topic_lines = max(1, (len(str(ws["D3"].value or "")) + 37) // 38)
            ws.row_dimensions[3].height = max(34, min(58, 16 * topic_lines + 8))
            ws.row_dimensions[4].height = 30
            ws.row_dimensions[5].height = 58
            header_alignment = copy(ws["B1"].alignment)
            header_alignment.wrap_text = True
            header_alignment.vertical = "center"
            ws["B1"].alignment = header_alignment
            for row in range(6, 11):
                name = str(ws.cell(row, 2).value or "")
                name_alignment = copy(ws.cell(row, 2).alignment)
                name_alignment.wrap_text = True
                name_alignment.vertical = "center"
                name_alignment.horizontal = "right"
                ws.cell(row, 2).alignment = name_alignment
                ws.row_dimensions[row].height = max(30, min(54, 18 * ((len(name) + 35) // 36)))
        summary = wb["الإجمالي"]
        if summary.max_row > 9:
            summary.delete_rows(10, summary.max_row - 9)
        if summary.max_column > 3:
            summary.delete_cols(4, summary.max_column - 3)
        summary["A1"] = header
        summary.sheet_view.showGridLines = False
        summary.sheet_properties.pageSetUpPr.fitToPage = True
        summary.page_setup.orientation = "portrait"
        summary.page_setup.paperSize = summary.PAPERSIZE_A4
        summary.page_setup.fitToWidth = 1
        summary.page_setup.fitToHeight = 1
        summary.print_area = "A1:C9"
        summary = wb["الإجمالي"]
        for offset in range(5):
            row, project_row = 5 + offset, 6 + offset
            summary.cell(row, 1).value = offset + 1
            summary.cell(row, 2).value = (f'=IF(\'المشروع الأول\'!B{project_row}="","",'
                                          f'\'المشروع الأول\'!B{project_row})')
            summary.cell(row, 3).value = (f'=IF(B{row}="","",SUM('
                                          f'\'المشروع الأول\'!M{project_row},'
                                          f'\'المشروع الثاني\'!M{project_row}))')
        if getattr(wb, "calculation", None):
            wb.calculation.fullCalcOnLoad = True
            wb.calculation.forceFullCalc = True
        stem = _safe_piece(f"استمارة_مشاريع_{label}_مجموعة_{group_index + 1:02d}")
        target = dest / f"{stem}.xlsx"
        n = 2
        while target.exists():
            target = dest / f"{stem} ({n}).xlsx"
            n += 1
        wb.save(target)
        created.append({"path": str(target), "group": group_index + 1,
                        "students": group_names})
    return {"created": created, "group_count": len(created), "student_count": sum(len(g["students"]) for g in groups),
            "output_directory": str(dest)}
