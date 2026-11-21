"""List partitions available for creating the folder tree (Windows)."""

from __future__ import annotations

import json
import os
import shutil
import string
import sys
import uuid

DRIVE_REMOVABLE, DRIVE_FIXED = 2, 3
FILE_READ_ONLY_VOLUME = 0x00080000
SEM_FAILCRITICALERRORS = 0x0001


def _can_create_folder(root: str) -> bool:
    """The tree is made of folders, so test exactly that: create one, remove it."""
    probe = os.path.join(root, f".biit_probe_{uuid.uuid4().hex[:8]}")
    try:
        os.mkdir(probe)
    except OSError:
        return False
    try:
        os.rmdir(probe)
    except OSError:
        pass
    return True


def _windows_drives() -> list[dict]:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    k32.GetDriveTypeW.restype = wintypes.UINT
    k32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    k32.GetVolumeInformationW.restype = wintypes.BOOL
    # No "insert a disk" dialogs for empty card readers.
    k32.SetErrorMode(SEM_FAILCRITICALERRORS)

    system_letter = (os.environ.get("SystemDrive") or "C:")[0].upper()
    mask = k32.GetLogicalDrives()
    drives = []
    for index, letter in enumerate(string.ascii_uppercase):
        if not (mask >> index) & 1:
            continue
        root = f"{letter}:\\"
        dtype = k32.GetDriveTypeW(root)
        if dtype not in (DRIVE_FIXED, DRIVE_REMOVABLE):
            continue

        label = ctypes.create_unicode_buffer(261)
        fs = ctypes.create_unicode_buffer(261)
        serial, max_len, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        ok = k32.GetVolumeInformationW(
            root, label, 261, ctypes.byref(serial), ctypes.byref(max_len),
            ctypes.byref(flags), fs, 261,
        )
        if not ok:  # no media / locked (BitLocker) volume
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue

        read_only = bool(flags.value & FILE_READ_ONLY_VOLUME)
        drives.append({
            "letter": letter,
            "root": root,
            "label": label.value,
            "fs": fs.value,
            "serial": f"{serial.value:08X}",
            "kind": "fixed" if dtype == DRIVE_FIXED else "removable",
            "system": letter == system_letter,
            "total": usage.total,
            "free": usage.free,
            "writable": (not read_only) and _can_create_folder(root),
        })
    return drives


def _sample_drives() -> list[dict]:
    """Development only (non-Windows): shows the screen with sample data."""
    raw = os.environ.get("BIIT_FAKE_DRIVES")
    if raw:
        return json.loads(raw)
    gb = 1024 ** 3
    return [
        {"letter": "C", "root": "C:\\", "label": "Windows", "fs": "NTFS", "serial": "A1B2C3D4",
         "kind": "fixed", "system": True, "total": 237 * gb, "free": 81 * gb, "writable": True},
        {"letter": "D", "root": "D:\\", "label": "Data", "fs": "NTFS", "serial": "0F0F1234",
         "kind": "fixed", "system": False, "total": 238 * gb, "free": 204 * gb, "writable": True},
        {"letter": "E", "root": "E:\\", "label": "KINGSTON", "fs": "FAT32", "serial": "77AA0001",
         "kind": "removable", "system": False, "total": 29 * gb, "free": 12 * gb, "writable": True},
    ]


def mark_recommended(drives: list[dict]) -> list[dict]:
    """Prefer a fixed non-system partition (survives a Windows re-install),
    otherwise the system drive. Never a removable drive."""
    for d in drives:
        d["recommended"] = False
    usable = [d for d in drives if d.get("writable") and d.get("kind") == "fixed"]
    pool = [d for d in usable if not d.get("system")] or usable
    if pool:
        max(pool, key=lambda d: d.get("free", 0))["recommended"] = True
    return drives


def list_drives() -> list[dict]:
    drives = _windows_drives() if sys.platform == "win32" else _sample_drives()
    return mark_recommended(drives)
