"""Archiving the folder trees and resetting the app.

Archiving moves the term folders of grades 1-11 into an archive folder on the
same drive — a rename, not a copy, so it is instant and loses nothing. Grade 12
trees stay where they are: their projects span the year and the teacher said so
explicitly. The reset wipes the app's own data files and nothing else; student
folders on any drive are never touched by either operation.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import config
from .naming import GRADES_AR

ARCHIVE_DIR = "الأرشيف"

# A term folder is recognised by its name, whatever year or semester it carries:
#   حادي عشر_ف1_2026-2027   or   G11_S1_2026-2027
_AR_NAMES = "|".join(re.escape(n) for n in GRADES_AR.values())
_TERM_AR = re.compile(rf"^({_AR_NAMES})(?:_.+)?_ف[12]_\d{{4}}-\d{{4}}$")
_TERM_EN = re.compile(r"^G(\d{1,2})(?:[-_].+)?_S[12]_\d{4}-\d{4}$")
_AR_GRADE = {name: num for num, name in GRADES_AR.items()}
_DEVICE_DIR = re.compile(r"^(?:جهاز\s+\d{1,2}|PC\d{1,2})$", re.IGNORECASE)
_TREE_ROOT_AR = re.compile(r"^شجرة الطلبة_ف[12]_\d{4}-\d{4}$")
_TREE_ROOT_EN = re.compile(r"^BiTT_Students_S[12]_\d{4}-\d{4}$", re.IGNORECASE)


def term_grade(folder_name: str) -> int | None:
    """Which grade a term folder belongs to, or None if it is not one."""
    m = _TERM_AR.match(folder_name)
    if m:
        return _AR_GRADE[m.group(1)]
    m = _TERM_EN.match(folder_name)
    if m and int(m.group(1)) in GRADES_AR:
        return int(m.group(1))
    return None


def archive_plan(location_root: str) -> dict:
    """What archiving would move, shown before anything happens."""
    root = Path(location_root)
    if not root.exists():
        return {"error": "موقع الإنشاء غير متاح الآن.", "moves": [], "kept": []}
    moves, kept = [], []

    def inspect_device(device: Path, prefix: Path) -> None:
        for section in sorted(device.iterdir()):
            if not section.is_dir():
                continue
            grade = term_grade(section.name)
            if grade is None:
                continue
            rel = prefix / device.name / section.name
            rel_text = str(rel) if str(rel) != "." else section.name
            if grade == 12:
                kept.append(rel_text)
            else:
                moves.append({"name": rel_text, "grade": grade,
                              "relative": rel_text, "source": str(section)})

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name == ARCHIVE_DIR:
            continue
        grade = term_grade(child.name)
        if grade is not None:
            if grade == 12:
                kept.append(child.name)
            else:
                moves.append({"name": child.name, "grade": grade,
                              "relative": child.name, "source": str(child)})
            continue
        if _TREE_ROOT_AR.match(child.name) or _TREE_ROOT_EN.match(child.name):
            for device in sorted(child.iterdir()):
                if device.is_dir() and _DEVICE_DIR.match(device.name):
                    inspect_device(device, Path(child.name))
            continue
        if _DEVICE_DIR.match(child.name):
            inspect_device(child, Path())
    dest = root / ARCHIVE_DIR / date.today().isoformat()
    for item in moves:
        item["target"] = str(dest / item["relative"])
    return {"dest": str(dest), "moves": moves, "kept": kept}


def archive_execute(location_root: str) -> dict:
    plan = archive_plan(location_root)
    if plan.get("error"):
        raise OSError(plan["error"])
    dest = Path(plan["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    moved, failed = [], []
    for item in plan["moves"]:
        src = Path(item.get("source") or (Path(location_root) / item["name"]))
        target = dest / item.get("relative", item["name"])
        n = 2
        while target.exists():               # same tree archived twice in a day
            target = target.with_name(f"{target.name} ({n})")
            n += 1
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            src.rename(target)
            moved.append(item["name"])
        except OSError:
            failed.append(item["name"])      # a file inside is open somewhere
    return {"dest": str(dest), "moved": moved, "failed": failed,
            "kept": plan["kept"]}


RESET_WORD = "تهيئة"


def factory_reset(confirm: str) -> None:
    """Delete the app's own data files; the word is typed, not clicked."""
    if confirm != RESET_WORD:
        raise ValueError(f"اكتب كلمة «{RESET_WORD}» للتأكيد.")
    for path in (
        config.user_dir() / "sections.json",
        config.user_dir() / "settings.json",
        config.user_dir() / "deploy.json",
        config.user_dir() / "tools.json",
        config.device_dir() / "device.json",
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    from . import sections
    with sections._CACHE_LOCK:
        sections._cache = None
