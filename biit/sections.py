"""Grade / section / device-assignment model."""

from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from typing import NamedTuple

from . import config
from .roster import Student

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class DeviceSlot(NamedTuple):
    device_no: int          # 1-based
    primary: int            # student index in Section.students (-1 = empty)
    secondary: int          # second student if overflow (-1 = none)


class Section(NamedTuple):
    grade: int
    label: str              # e.g. "5-1" or "12-3"
    students: list[Student]
    slots: list[DeviceSlot]  # built by assign_devices()


class GradeGroup(NamedTuple):
    grade: int
    sections: list[Section]


# ---------------------------------------------------------------------------
# Sections file (per-user, lives next to settings.json)
# ---------------------------------------------------------------------------

def _sections_path() -> Path:
    return config.user_dir() / "sections.json"


# The UI opens one screen and asks about every section at once, so this file is
# read by several worker threads at the same moment. A transient read failure
# must never read as "there are no sections" — that silently empties the app.
_CACHE_LOCK = threading.RLock()
_cache: tuple[tuple[int, int], list[dict]] | None = None


def _read_sections(path: Path, attempts: int = 3) -> list[dict] | None:
    """Parse the file, retrying briefly. Returns None if it could not be read."""
    for n in range(attempts):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if n == attempts - 1:
                return None
            time.sleep(0.02 * (n + 1))
            continue
        return data if isinstance(data, list) else []
    return None


def load_sections() -> list[dict]:
    """Return raw list; each item: {grade, label, students:[{name,key}]}.

    The result is a private copy — callers mutate it before saving it back.
    """
    global _cache
    p = _sections_path()
    try:
        stat = p.stat()
    except FileNotFoundError:
        return []
    except OSError:
        stat = None
    stamp = (stat.st_mtime_ns, stat.st_size) if stat else None

    with _CACHE_LOCK:
        if _cache is not None and stamp is not None and _cache[0] == stamp:
            return copy.deepcopy(_cache[1])
        data = _read_sections(p)
        if data is None:
            # Serve the last good copy rather than claim the file is empty.
            return copy.deepcopy(_cache[1]) if _cache is not None else []
        if stamp is not None:
            _cache = (stamp, data)
        return copy.deepcopy(data)


def save_sections(sections_data: list[dict]) -> None:
    """Atomic write of raw section list."""
    global _cache
    path = _sections_path()
    with _CACHE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        config.save_json(path, sections_data)
        try:
            stat = path.stat()
            _cache = ((stat.st_mtime_ns, stat.st_size), copy.deepcopy(sections_data))
        except OSError:
            _cache = None


def _as_dicts(students: list[Student]) -> list[dict]:
    return [{"name": st.name, "key": st.key, "suspect": bool(st.suspect)} for st in students]


def upsert_section(grade: int, label: str, students: list[Student]) -> None:
    """Add or replace a section's student list, keeping its device layout."""
    all_secs = load_sections()
    for s in all_secs:
        if s["grade"] == grade and s["label"] == label:
            s["students"] = _as_dicts(students)
            break
    else:
        all_secs.append({
            "grade": grade,
            "label": label,
            "students": _as_dicts(students),
            "devices": {"disabled": [], "pinned": {}},
        })
    save_sections(all_secs)


def find_section(grade: int, label: str) -> dict | None:
    for s in load_sections():
        if s["grade"] == grade and s["label"] == label:
            return s
    return None


def rename_student(grade: int, label: str, index: int, new_name: str) -> str | None:
    """Correct one student's name in place. Returns an error message or None.

    Keeps the device layout intact: pins are held by student key, so the key is
    rewritten in both places together.
    """
    from .roster import match_key, normalise

    name = normalise(new_name)
    if len(name.split()) < 2:
        return "الاسم يجب أن يتكوّن من كلمتين على الأقل."
    all_secs = load_sections()
    for s in all_secs:
        if s["grade"] != grade or s["label"] != label:
            continue
        students = s.get("students", [])
        if not 0 <= index < len(students):
            return "رقم الطالب خارج النطاق."
        old_key = students[index].get("key")
        new_key = match_key(name)
        if any(i != index and st.get("key") == new_key for i, st in enumerate(students)):
            return "يوجد طالب آخر بالاسم نفسه في هذه الشعبة."
        students[index] = {"name": name, "key": new_key, "suspect": False}
        pinned = s.setdefault("devices", {}).setdefault("pinned", {})
        for dev, k in list(pinned.items()):
            if k == old_key:
                pinned[dev] = new_key
        save_sections(all_secs)
        return None
    return "الشعبة غير موجودة."


def save_device_layout(grade: int, label: str, disabled: list[int],
                       pinned: dict[str, str]) -> str | None:
    """Store which devices are out of service and which students are fixed.

    ``pinned`` maps a device number (as a string key) to a student key.
    """
    all_secs = load_sections()
    for s in all_secs:
        if s["grade"] != grade or s["label"] != label:
            continue
        keys = {st.get("key") for st in s.get("students", [])}
        clean_pins = {
            str(int(d)): k for d, k in pinned.items()
            if k in keys and str(int(d)) not in {str(x) for x in disabled}
        }
        if len(set(clean_pins.values())) != len(clean_pins):
            return "لا يمكن تثبيت الطالب نفسه على أكثر من جهاز."
        transfer_map = (s.get("devices") or {}).get("transfers", {})
        clean_transfers = {str(k): int(v) for k, v in transfer_map.items()
                           if k in keys and str(int(v)) not in {str(x) for x in disabled}}
        s["devices"] = {"disabled": sorted({int(d) for d in disabled}),
                        "pinned": clean_pins, "transfers": clean_transfers}
        save_sections(all_secs)
        return None
    return "الشعبة غير موجودة."


def delete_section(grade: int, label: str) -> None:
    all_secs = [s for s in load_sections()
                if not (s["grade"] == grade and s["label"] == label)]
    save_sections(all_secs)


# ---------------------------------------------------------------------------
# Device assignment
# ---------------------------------------------------------------------------

def assign_devices(students: list[Student], device_count: int,
                   overrides: dict[int, list[int]] | None = None,
                   disabled: list[int] | None = None,
                   pinned: dict[int, int] | None = None) -> list[DeviceSlot]:
    """Assign students to devices.

    Args:
        students: ordered list of students.
        device_count: total devices in the lab.
        overrides: mapping {device_no (1-based): [primary_idx, secondary_idx|-1]}.
            Applied last, over everything else.
        disabled: device numbers that are out of service. They stay in the list
            as empty slots and take no students — a lab rarely has every machine
            working, and renumbering around a dead one would relabel the room.
        pinned: mapping {device_no: student_idx} fixed by the teacher. Pinned
            students keep their device; everyone else flows around them.

    Rules:
      - Students are placed on working devices only, in roster order.
      - One student per device while there are enough devices.
      - Beyond that, the earliest working devices take a second student.
    """
    n = len(students)
    dead = {int(d) for d in (disabled or [])}
    pins = {int(d): int(i) for d, i in (pinned or {}).items()
            if int(d) not in dead and 0 <= int(i) < n}

    usable = [d for d in range(1, device_count + 1) if d not in dead]
    free_devices = [d for d in usable if d not in pins]
    queue = [i for i in range(n) if i not in set(pins.values())]

    seats: dict[int, list[int]] = {d: [] for d in range(1, device_count + 1)}
    for dev, idx in pins.items():
        seats[dev].append(idx)

    # First pass: one student per free device. Second pass: double up, earliest
    # working devices first, so the crowding is visible at the front of the room.
    for dev in free_devices:
        if not queue:
            break
        seats[dev].append(queue.pop(0))
    for dev in usable:
        if not queue:
            break
        if len(seats[dev]) < 2:
            seats[dev].append(queue.pop(0))

    slots = [
        DeviceSlot(d,
                   seats[d][0] if len(seats[d]) > 0 else -1,
                   seats[d][1] if len(seats[d]) > 1 else -1)
        for d in range(1, device_count + 1)
    ]

    # Apply manual overrides
    if overrides:
        slot_map = {sl.device_no: i for i, sl in enumerate(slots)}
        for dev_no, assignment in overrides.items():
            idx = slot_map.get(dev_no)
            if idx is None:
                continue
            p = assignment[0] if len(assignment) > 0 else -1
            s = assignment[1] if len(assignment) > 1 else -1
            slots[idx] = DeviceSlot(dev_no, p, s)

    return slots


def section_slots(section: dict, device_count: int) -> list[dict]:
    """Compute one section's device layout for the UI.

    Returns a row per device: its number, whether it is out of service, and the
    students seated on it.
    """
    from .roster import Student as _S

    raw = section.get("students", [])
    students = [_S(s.get("name", ""), s.get("key", ""), i, s.get("suspect", False))
                for i, s in enumerate(raw)]
    cfg = section.get("devices") or {}
    disabled = [int(d) for d in cfg.get("disabled", [])]
    by_key = {s.key: i for i, s in enumerate(students)}
    pinned = {int(d): by_key[k] for d, k in (cfg.get("pinned") or {}).items() if k in by_key}

    slots = assigned_slots(section, device_count, students=students)
    return [
        {
            "device_no": sl.device_no,
            "disabled": sl.device_no in set(disabled),
            "pinned": sl.device_no in pinned,
            "primary": raw[sl.primary] if sl.primary >= 0 else None,
            "secondary": raw[sl.secondary] if sl.secondary >= 0 else None,
        }
        for sl in slots
    ]


def assigned_slots(section: dict, device_count: int,
                   students: list[Student] | None = None) -> list[DeviceSlot]:
    """Return computed seats, including explicit student-to-device transfers."""
    raw = section.get("students", [])
    students = students or [Student(s.get("name", ""), s.get("key", ""), i,
                                    s.get("suspect", False)) for i, s in enumerate(raw)]
    cfg = section.get("devices") or {}
    disabled = [int(d) for d in cfg.get("disabled", [])]
    by_key = {s.key: i for i, s in enumerate(students)}
    pinned = {int(d): by_key[k] for d, k in (cfg.get("pinned") or {}).items()
              if k in by_key}
    base = assign_devices(students, device_count, disabled=disabled, pinned=pinned)
    seats = {slot.device_no: [i for i in (slot.primary, slot.secondary) if i >= 0]
             for slot in base}
    transfers = cfg.get("transfers") or {}
    for key, destination in transfers.items():
        index = by_key.get(str(key))
        try:
            destination = int(destination)
        except (TypeError, ValueError):
            continue
        if index is None or destination not in seats or destination in disabled:
            continue
        source = next((device for device, members in seats.items() if index in members), None)
        if source is None or source == destination or len(seats[destination]) >= 2:
            continue
        seats[source].remove(index)
        seats[destination].append(index)
    return [DeviceSlot(device, seats[device][0] if seats[device] else -1,
                       seats[device][1] if len(seats[device]) > 1 else -1)
            for device in range(1, device_count + 1)]


def transfer_students(grade: int, label: str, destinations: dict[str, int]) -> str | None:
    """Persist per-student device moves without changing other layout pins."""
    all_secs = load_sections()
    for section in all_secs:
        if int(section.get("grade", 0)) != grade or section.get("label") != label:
            continue
        keys = {str(st.get("key") or "") for st in section.get("students", [])}
        transfers = section.setdefault("devices", {}).setdefault("transfers", {})
        for key, device in destinations.items():
            if key not in keys:
                return "أحد الطلبة المحددين لم يعد ضمن الشعبة."
            transfers[key] = int(device)
        save_sections(all_secs)
        return None
    return "الشعبة غير موجودة."


def unseated_count(section: dict, device_count: int) -> int:
    """How many students no working device can hold."""
    raw = section.get("students", [])
    cfg = section.get("devices") or {}
    dead = {int(d) for d in cfg.get("disabled", [])}
    usable = len([d for d in range(1, device_count + 1) if d not in dead])
    return max(0, len(raw) - usable * 2)


def validate_label(label: str) -> str | None:
    """Return error message or None if valid."""
    label = label.strip()
    if not label:
        return "اسم الشعبة لا يمكن أن يكون فارغًا."
    if len(label) > 20:
        return "اسم الشعبة طويل جدًا (الحد 20 حرفًا)."
    return None
