"""Device-first student folder trees and non-destructive previews."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from .naming import section_folder, term_folder, tree_root_folder
from .sections import DeviceSlot, section_slots
from .roster import Student

G12_SUBFOLDERS = [
    "نشاط عملي 1",
    "نشاط عملي 2",
    "اختبار عملي",
    "المشاريع/المشروع الأول والثاني",
    "المشاريع/المشروع الثالث والرابع",
]


def device_folder(device_no: int) -> str:
    return f"جهاز {device_no:02d}"


def section_icon_number(label: str) -> int | None:
    """Return the 1–12 section number used by the text icon scheme."""
    import re
    match = re.search(r"(\d{1,2})\s*$", str(label or ""))
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 12 else None


class FolderPlan(NamedTuple):
    root: Path
    new_dirs: list[Path]
    existing_dirs: list[Path]
    total_students: int
    mode: str = "section"
    section_count: int = 1
    device_count: int = 0
    # (folder path, icon kind, first value, second value)
    icon_targets: list[tuple[Path, str, int, int]] | None = None


def _finish_plan(root: Path, dirs: list[Path], total_students: int, mode: str,
                 section_count: int, icon_targets: list[tuple[Path, str, int, int]],
                 device_count: int | None = None) -> FolderPlan:
    # Keep preview order stable while avoiding repeated parent directories.
    unique = list(dict.fromkeys(dirs))
    new_dirs = [d for d in unique if not d.exists()]
    existing_dirs = [d for d in unique if d.exists()]
    return FolderPlan(root, new_dirs, existing_dirs, total_students, mode,
                      section_count, (device_count if device_count is not None else
                                      len({x[0] for x in icon_targets if x[1] == "device"})),
                      icon_targets)


def _append_student_tree(dirs: list[Path], student_dir: Path, grade: int) -> None:
    dirs.append(student_dir)
    if grade == 12:
        dirs.extend(student_dir / sub for sub in G12_SUBFOLDERS)


def plan_tree(
    location_root: Path,
    grade: int,
    semester: int,
    academic_year: str,
    naming_lang: str,
    students: list[Student],
    slots: list[DeviceSlot],
    skip_devices: set[int] | None = None,
    section_label: str = "",
    include_section_label: bool = False,
) -> FolderPlan:
    """Plan the established single-section layout; full matrix has its own mode."""
    skip_devices = skip_devices or set()
    label = section_label or f"{grade}-1"
    root = Path(location_root) / section_folder(
        grade, label, semester, academic_year, naming_lang,
        include_label=include_section_label)
    dirs: list[Path] = [root]
    icons: list[tuple[Path, str, int, int]] = []
    sec_no = section_icon_number(label) or 0
    if sec_no:
        icons.append((root, "section", grade, sec_no))

    if grade == 12:
        for student in students:
            _append_student_tree(dirs, root / student.name, grade)
    else:
        for slot in slots:
            if slot.device_no in skip_devices:
                continue
            indices = [i for i in (slot.primary, slot.secondary) if 0 <= i < len(students)]
            names = [students[i].name for i in indices]
            folder = root / (f"جهاز {slot.device_no:02d} - {' - '.join(names)}" if names
                             else f"جهاز {slot.device_no:02d}")
            dirs.append(folder)
            icons.append((folder, "device", slot.device_no, 0))

    active_devices = sum(
        1 for slot in slots if slot.device_no not in skip_devices
        and any(0 <= i < len(students) for i in (slot.primary, slot.secondary))
    )
    return _finish_plan(root, dirs, len(students), "section", 1, icons, active_devices)


def plan_matrix_tree(location_root: Path, sections: list[dict], semester: int,
                     academic_year: str, naming_lang: str,
                     device_count: int) -> FolderPlan:
    """Plan every populated section under its assigned device folder."""
    root = Path(location_root) / tree_root_folder(semester, academic_year, naming_lang)
    dirs: list[Path] = []
    icons: list[tuple[Path, str, int, int]] = []
    icon_seen: set[tuple[Path, str, int, int]] = set()
    populated = [s for s in sections if s.get("students")]
    section_counts: dict[int, int] = {}
    for section in sections:
        grade = int(section["grade"])
        section_counts[grade] = section_counts.get(grade, 0) + 1
    for section in populated:
        grade = int(section["grade"])
        label = str(section["label"])
        sec_name = section_folder(grade, label, semester, academic_year, naming_lang,
                                  include_label=section_counts.get(grade, 0) > 1)
        sec_no = section_icon_number(label)
        for slot in section_slots(section, device_count):
            seated = [st for st in (slot["primary"], slot["secondary"]) if st]
            if not seated:
                continue
            dev_dir = root / device_folder(slot["device_no"])
            sec_dir = dev_dir / sec_name
            dirs.extend((dev_dir, sec_dir))
            dev_icon = (dev_dir, "device", slot["device_no"], 0)
            if dev_icon not in icon_seen:
                icons.append(dev_icon)
                icon_seen.add(dev_icon)
            if sec_no:
                sec_icon = (sec_dir, "section", grade, sec_no)
                if sec_icon not in icon_seen:
                    icons.append(sec_icon)
                    icon_seen.add(sec_icon)
            for st in seated:
                _append_student_tree(dirs, sec_dir / st["name"], grade)

    return _finish_plan(root, dirs, sum(len(s.get("students", [])) for s in populated),
                        "matrix", len(populated), icons)


class TreeResult(NamedTuple):
    created: list[Path]
    skipped: list[Path]
    errors: list[tuple[Path, str]]


def execute_tree(plan: FolderPlan) -> TreeResult:
    """Create only missing directories. Existing content is never removed."""
    created: list[Path] = []
    skipped: list[Path] = list(plan.existing_dirs)
    errors: list[tuple[Path, str]] = []
    for directory in plan.new_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            created.append(directory)
        except OSError as exc:
            errors.append((directory, str(exc)))
    return TreeResult(created, skipped, errors)


def grade_label_ar(grade: int) -> str:
    from .naming import GRADES_AR
    return f"الصف {GRADES_AR.get(grade, str(grade))}"
