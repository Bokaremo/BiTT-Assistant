"""Settings storage.

- Teacher settings: per Windows user  -> %APPDATA%\\BiitAssistant\\settings.json
- Device settings (creation drive): per machine -> %PROGRAMDATA%\\BiitAssistant\\device.json
  (falls back to %LOCALAPPDATA% when ProgramData is not writable)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .naming import valid_year

APP_DIR = "BiitAssistant"
MIN_DEVICES, MAX_DEVICES = 20, 40


def _ensure(path: Path) -> Path | None:
    """Create the directory and confirm it is writable.

    The probe file is named per thread. A shared name let concurrent callers
    delete each other's probe, and the FileNotFoundError that followed read as
    "this directory is not writable" — which silently redirected the app's data
    to the temp folder and made saved sections vanish.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write_test-{os.getpid()}-{threading.get_ident()}"
        probe.write_text("ok", encoding="utf-8")
    except OSError:
        return None
    try:
        probe.unlink()
    except OSError:
        pass        # the write is what was being tested; a leftover probe is harmless
    return path


# Resolving a data directory touches the disk, and it happens on every request.
# The answer only changes when the environment does, so it is kept per path.
_DIR_LOCK = threading.Lock()
_dir_cache: dict[Path, Path] = {}


def _resolve(base: Path, fallback) -> Path:
    with _DIR_LOCK:
        hit = _dir_cache.get(base)
        if hit is not None:
            return hit
        value = _ensure(base) or fallback()
        _dir_cache[base] = value
        return value


def user_dir() -> Path:
    override = os.environ.get("BIIT_DATA_DIR")
    if override:
        base = Path(override) / "user"
    else:
        base = Path(os.environ.get("APPDATA") or Path.home() / ".config") / APP_DIR
    return _resolve(base, lambda: Path(tempfile.gettempdir()))


def device_dir() -> Path:
    override = os.environ.get("BIIT_DATA_DIR")
    if override:
        candidates = [Path(override) / "device"]
    else:
        candidates = []
        if os.environ.get("PROGRAMDATA"):
            candidates.append(Path(os.environ["PROGRAMDATA"]) / APP_DIR)
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / APP_DIR)
    for c in candidates:
        resolved = _resolve(c, lambda: None)
        if resolved is not None:
            return resolved
    return user_dir()


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomic write: never leaves a half-written file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- teacher settings ----------

def _default_year(today: _dt.date | None = None) -> str:
    today = today or _dt.date.today()
    start = today.year if today.month >= 8 else today.year - 1
    return f"{start}-{start + 1}"


def default_settings() -> dict:
    return {
        "school_name": "",
        "teacher_name": "",
        "academic_year": _default_year(),
        "semester": 1,
        "naming_lang": "en",
        "device_count": MIN_DEVICES,
    }


def validate_settings(data: dict) -> tuple[dict, dict]:
    """Returns (clean, errors). errors maps field -> Arabic message."""
    clean, errors = {}, {}

    for key, label in (("school_name", "اسم المدرسة"), ("teacher_name", "اسم المعلم")):
        value = " ".join(str(data.get(key, "")).split())
        if len(value) > 80:
            errors[key] = f"{label} أطول من 80 حرفًا."
        clean[key] = value

    year = str(data.get("academic_year", "")).strip().replace("/", "-")
    if not valid_year(year):
        errors["academic_year"] = "اكتب العام الدراسي بالصيغة 2026-2027 (عامان متتاليان)."
    clean["academic_year"] = year

    if data.get("semester") in (1, 2, "1", "2"):
        clean["semester"] = int(data["semester"])
    else:
        errors["semester"] = "اختر الفصل الدراسي الأول أو الثاني."

    if data.get("naming_lang") in ("ar", "en"):
        clean["naming_lang"] = data["naming_lang"]
    else:
        errors["naming_lang"] = "اختر لغة تسمية المجلدات."

    try:
        count = int(data.get("device_count"))
        if not MIN_DEVICES <= count <= MAX_DEVICES:
            raise ValueError
        clean["device_count"] = count
    except (TypeError, ValueError):
        errors["device_count"] = f"عدد الأجهزة بين {MIN_DEVICES} و{MAX_DEVICES}."

    return clean, errors


def load_settings() -> dict:
    stored = load_json(user_dir() / "settings.json", {})
    merged = {**default_settings(), **(stored if isinstance(stored, dict) else {})}
    clean, errors = validate_settings(merged)
    if errors:  # corrupted file: keep valid fields, reset the rest
        defaults = default_settings()
        for field in errors:
            clean[field] = defaults[field]
    return clean


def save_settings(clean: dict) -> None:
    save_json(user_dir() / "settings.json", clean)


def settings_saved_fields() -> dict[str, bool]:
    stored = load_json(user_dir() / "settings.json", {})
    stored = stored if isinstance(stored, dict) else {}
    return {key: key in stored for key in
            ("school_name", "teacher_name", "device_count", "academic_year", "semester")}


# ---------- device location ----------

def load_location() -> dict | None:
    data = load_json(device_dir() / "device.json", {})
    loc = data.get("location") if isinstance(data, dict) else None
    return loc if isinstance(loc, dict) and loc.get("letter") else None


def save_location(drive: dict) -> dict:
    path = device_dir() / "device.json"
    data = load_json(path, {})
    if not isinstance(data, dict):
        data = {}
    data["location"] = {
        "letter": drive["letter"],
        "label": drive.get("label", ""),
        "serial": drive.get("serial", ""),
        "total": drive.get("total", 0),
    }
    save_json(path, data)
    return data["location"]


def resolve_location(saved: dict | None, drives: list[dict]) -> dict:
    """Match the saved choice against the drives present right now.

    Drive letters can change (USB sticks, re-imaging), so the volume serial
    number is the identity; the letter is only what we show.
    """
    if not saved:
        return {"status": "unset"}

    match = None
    if saved.get("serial"):
        match = next((d for d in drives if d.get("serial") == saved["serial"]), None)
    else:
        match = next((d for d in drives if d["letter"] == saved["letter"]), None)

    if match is None:
        return {"status": "missing", "letter": saved["letter"], "label": saved.get("label", "")}

    result = {
        "letter": match["letter"], "label": match.get("label", ""), "root": match["root"],
        "free": match.get("free", 0), "total": match.get("total", 0), "kind": match.get("kind"),
    }
    if not match.get("writable"):
        result["status"] = "readonly"
    elif match["letter"] != saved["letter"]:
        result["status"] = "moved"
        result["previous_letter"] = saved["letter"]
        save_location(match)
    else:
        result["status"] = "ok"
    return result
