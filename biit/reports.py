"""Reports derived from the sections, the seating and the collection inbox.

Nothing here asks for new input: every row is computed from the links the
teacher has already made — rosters, device layout, creation location and what
has arrived in the collection inbox. The printable distribution guide mirrors
the paper guide the teacher used to type by hand (م / الطالب / الجهاز).
"""

from __future__ import annotations

from pathlib import Path

from .naming import section_folder, term_folder, tree_root_folder
from .roster import Student, match_key, normalise
from .sections import section_slots
from .treegen import G12_SUBFOLDERS, device_folder  # noqa: F401


def _seating(section: dict, settings: dict) -> dict[str, dict]:
    """student key -> {device_no, seat, shared_with} for one section."""
    out: dict[str, dict] = {}
    for slot in section_slots(section, settings["device_count"]):
        pair = [p for p in (slot["primary"], slot["secondary"]) if p]
        for seat, st in enumerate(pair, start=1):
            other = pair[1 - (seat - 1)] if len(pair) == 2 else None
            out[st["key"]] = {
                "device_no": slot["device_no"],
                "seat": seat,
                "shared_with": other["name"] if other else None,
            }
    return out


def distribution_guide(sections: list[dict], settings: dict) -> list[dict]:
    """The printable guide: every section, every student, their machine."""
    guide = []
    for section in sections:
        if not section.get("students"):
            continue
        seats = _seating(section, settings)
        rows = []
        for i, st in enumerate(section["students"]):
            at = seats.get(st.get("key"))
            rows.append({
                "no": i + 1,
                "name": st.get("name", ""),
                "device_no": at["device_no"] if at else None,
                "seat": at["seat"] if at else None,
            })
        guide.append({"grade": section["grade"], "label": section["label"], "rows": rows})
    return guide


def _student_path(section: dict, st: dict, device_no: int | None,
                  shared_with: str | None, root: str | None,
                  settings: dict) -> str | None:
    """Where this student's folder lives on the creation drive."""
    if not root:
        return None
    if device_no is None:
        return None
    grade = int(section["grade"])
    section_count = sum(1 for item in settings.get("sections", [])
                        if int(item.get("grade", 0)) == grade)
    term = section_folder(grade, str(section["label"]), settings["semester"],
                          settings["academic_year"], settings["naming_lang"],
                          include_label=section_count > 1)
    matrix = (Path(root) / tree_root_folder(settings["semester"], settings["academic_year"],
                                           settings["naming_lang"])
              / device_folder(device_no) / term / st["name"])
    if matrix.exists():
        return str(matrix)
    # Compatibility with matrix trees created before they received a parent folder.
    old_matrix = Path(root) / device_folder(device_no) / term / st["name"]
    if old_matrix.exists():
        return str(old_matrix)
    old_term = section_folder(grade, str(section["label"]), settings["semester"],
                              settings["academic_year"], settings["naming_lang"])
    legacy_matrix = (Path(root) / tree_root_folder(settings["semester"], settings["academic_year"],
                                                   settings["naming_lang"])
                     / device_folder(device_no) / old_term / st["name"])
    if legacy_matrix.exists():
        return str(legacy_matrix)
    old_direct_matrix = Path(root) / device_folder(device_no) / old_term / st["name"]
    if old_direct_matrix.exists():
        return str(old_direct_matrix)

    # Keep paths accurate for trees created with the original single-section mode.
    legacy_term = term_folder(grade, settings["semester"], settings["academic_year"],
                              settings["naming_lang"])
    if grade == 12:
        legacy = Path(root) / legacy_term / st["name"]
    else:
        names = st["name"]
        if shared_with:
            at = _seating(section, settings).get(st.get("key")) or {}
            names = f"{shared_with} - {st['name']}" if at.get("seat") == 2 else f"{st['name']} - {shared_with}"
        legacy = Path(root) / legacy_term / f"جهاز {device_no:02d} - {names}"
    return str(legacy if legacy.exists() else matrix)


def find_students(query: str, sections: list[dict], settings: dict,
                  root: str | None, inbox: list[dict]) -> list[dict]:
    """Substring search over every roster, with path and collected-file count."""
    needle = match_key(normalise(query)) or normalise(query)
    if not needle:
        return []
    settings = {**settings, "sections": sections}
    collected: dict[tuple[str, int], int] = {}
    for batch in inbox:          # newest day first per label — keep the newest
        for dev in batch["devices"]:
            collected.setdefault((batch["label"], dev["device_no"]), dev["files"])

    matches = []
    for section in sections:
        seats = _seating(section, settings)
        for st in section.get("students", []):
            hay = match_key(st.get("name", "")) or normalise(st.get("name", ""))
            if needle not in hay:
                continue
            at = seats.get(st.get("key"))
            device_no = at["device_no"] if at else None
            matches.append({
                "name": st.get("name", ""),
                "grade": section["grade"],
                "label": section["label"],
                "device_no": device_no,
                "seat": at["seat"] if at else None,
                "shared_with": at["shared_with"] if at else None,
                "path": _student_path(section, st, device_no,
                                      at["shared_with"] if at else None,
                                      root, settings),
                "collected_files": collected.get((str(section["label"]), device_no))
                                   if device_no else None,
            })
    return matches


def device_report(section: dict, settings: dict, inbox: list[dict]) -> list[dict]:
    """Per machine: who sits there and what the latest collection brought."""
    label = str(section["label"])
    latest: dict[int, dict] | None = None
    latest_date = None
    for batch in inbox:
        if batch["label"] == label:          # scan_inbox is newest-first
            latest = {d["device_no"]: d for d in batch["devices"]}
            latest_date = batch["date"]
            break
    rows = []
    for slot in section_slots(section, settings["device_count"]):
        got = (latest or {}).get(slot["device_no"])
        rows.append({
            "device_no": slot["device_no"],
            "disabled": slot["disabled"],
            "students": [p["name"] for p in (slot["primary"], slot["secondary"]) if p],
            "files": got["files"] if got else 0,
            "bytes": got["bytes"] if got else 0,
        })
    return {"date": latest_date, "rows": rows}
