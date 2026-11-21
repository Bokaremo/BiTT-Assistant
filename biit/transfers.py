"""Move existing student work folders between lab devices."""

from __future__ import annotations

from pathlib import Path

from .naming import section_folder, tree_root_folder
from .sections import section_slots, transfer_students as persist_transfers
from .treegen import device_folder


def section_state(location_root: str | Path, sections: list[dict], settings: dict,
                  grade: int, label: str) -> dict:
    section = next((s for s in sections
                    if int(s.get("grade", 0)) == grade and s.get("label") == label), None)
    if section is None:
        raise ValueError("الشعبة غير موجودة.")
    root = Path(location_root) / tree_root_folder(
        settings["semester"], settings["academic_year"], settings["naming_lang"])
    if not root.is_dir():
        raise ValueError("لم تُنشأ الشجرة الشاملة بعد. أنشئها أولاً من شاشة إنشاء المجلدات.")
    counts: dict[int, int] = {}
    for item in sections:
        g = int(item.get("grade", 0))
        counts[g] = counts.get(g, 0) + 1
    section_name = section_folder(grade, label, settings["semester"],
                                  settings["academic_year"], settings["naming_lang"],
                                  include_label=counts.get(grade, 0) > 1)
    slots = section_slots(section, int(settings["device_count"]))
    assignments: dict[str, int] = {}
    devices = []
    for slot in slots:
        seated = [st for st in (slot["primary"], slot["secondary"]) if st]
        devices.append({"device_no": slot["device_no"], "disabled": slot["disabled"],
                        "students": [st["name"] for st in seated]})
        for student in seated:
            assignments[str(student.get("key") or student["name"])] = slot["device_no"]
    students = []
    for index, student in enumerate(section.get("students", [])):
        key = str(student.get("key") or student["name"])
        device_no = assignments.get(key)
        if device_no is None:
            continue
        folder = root / device_folder(device_no) / section_name / str(student["name"])
        students.append({"index": index, "name": student["name"], "device_no": device_no,
                         "folder_exists": folder.is_dir()})
    return {"root": str(root), "grade": grade, "label": label,
            "section_folder": section_name, "students": students, "devices": devices}


def move_students(location_root: str | Path, sections: list[dict], settings: dict,
                  grade: int, label: str, student_indices: list[int],
                  target_device: int) -> dict:
    if not student_indices:
        raise ValueError("اختر مجلداً واحداً على الأقل.")
    if len(student_indices) != len(set(student_indices)):
        raise ValueError("تكرر اختيار أحد الطلبة.")
    state = section_state(location_root, sections, settings, grade, label)
    section = next(s for s in sections
                   if int(s.get("grade", 0)) == grade and s.get("label") == label)
    devices = {int(d["device_no"]): d for d in state["devices"]}
    if target_device not in devices or devices[target_device]["disabled"]:
        raise ValueError("اختر جهازاً متاحاً لاستقبال المجلدات.")
    students_by_index = {int(st["index"]): st for st in state["students"]}
    selected = []
    for index in student_indices:
        item = students_by_index.get(int(index))
        if item is None:
            raise ValueError("أحد الطلبة غير موزع على جهاز صالح.")
        if item["device_no"] == target_device:
            raise ValueError(f"الطالب {item['name']} موجود بالفعل على الجهاز الهدف.")
        if not item["folder_exists"]:
            raise FileNotFoundError(f"مجلد الطالب {item['name']} غير موجود في الشجرة.")
        selected.append(item)

    occupants = len(devices[target_device]["students"])
    if occupants + len(selected) > 2:
        raise ValueError(f"الجهاز الهدف يحتوي {occupants} طالباً؛ لا يمكن أن يزيد العدد على طالبين.")

    root = Path(state["root"]).resolve(strict=True)
    section_path = state["section_folder"]
    moves: list[tuple[Path, Path]] = []
    for item in selected:
        name = str(item["name"])
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError("اسم مجلد أحد الطلبة غير صالح.")
        source = (root / device_folder(int(item["device_no"])) / section_path / name).resolve(strict=True)
        destination_parent = root / device_folder(target_device) / section_path
        destination_parent.mkdir(parents=True, exist_ok=True)
        destination = destination_parent / name
        if root not in source.parents or root not in destination.resolve(strict=False).parents:
            raise ValueError("مسار أحد المجلدات خارج شجرة الطلبة.")
        if destination.exists():
            raise FileExistsError(f"يوجد مجلد آخر بالاسم نفسه على الجهاز الهدف: {name}.")
        moves.append((source, destination))

    moved: list[tuple[Path, Path]] = []
    try:
        for source, destination in moves:
            source.rename(destination)
            moved.append((source, destination))

        assignments = {str(section["students"][int(item["index"])].get("key") or ""):
                       target_device for item in selected}
        err = persist_transfers(grade, label, assignments)
        if err:
            raise ValueError(err)
    except Exception:
        for source, destination in reversed(moved):
            try:
                destination.rename(source)
            except OSError:
                pass
        raise

    return {"moved": [{"name": item["name"], "from": item["device_no"],
                       "to": target_device} for item in selected],
            "root": state["root"]}
