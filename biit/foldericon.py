"""Generated device and section icons for the folder tree.

Windows reads a folder's icon from a desktop.ini inside it, provided the
folder carries the ReadOnly attribute (which, on a folder, means "has custom
settings" — Explorer still writes into it freely). The .ico is copied into the
folder itself and referenced relatively, so the icon survives moves, archiving
and deployment to another machine.
"""

from __future__ import annotations

import colorsys
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICON_FILE = "biit-folder.ico"
_DESKTOP_INI = f"[.ShellClassInfo]\r\nIconResource={ICON_FILE},0\r\n"


def icons_dir(web_dir: Path) -> Path:
    return web_dir / "foldericons"


def list_icons(web_dir: Path) -> list[dict]:
    out = []
    for ico in sorted(icons_dir(web_dir).glob("*.ico")):
        out.append({"id": ico.stem, "preview": f"/static/foldericons/{ico.stem}.png"})
    return out


def apply_icon(folder: Path, icon_id: str, web_dir: Path) -> str | None:
    """Give one existing folder the chosen icon. Returns an error or None.

    Nothing already in the folder is touched; only the two icon files are
    written, and an existing desktop.ini from an earlier choice is replaced —
    that file is the icon setting itself, not user work.
    """
    source = icons_dir(web_dir) / f"{icon_id}.ico"
    if not source.exists():
        return "الأيقونة غير موجودة."
    if not folder.is_dir():
        return "المجلد غير موجود."
    try:
        (folder / ICON_FILE).write_bytes(source.read_bytes())
        ini = folder / "desktop.ini"
        if sys.platform == "win32" and ini.exists():
            _set_attrs(ini, hidden=False, system=False)   # allow rewrite
        ini.write_text(_DESKTOP_INI, encoding="utf-8")
        if sys.platform == "win32":
            _set_attrs(ini, hidden=True, system=True)
            _set_attrs(folder / ICON_FILE, hidden=True, system=False)
            _set_readonly_dir(folder)
    except OSError as exc:
        return f"تعذّر تطبيق الأيقونة: {exc}"
    return None


def _icon_palette(kind: str, first: int, second: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if kind == "device":
        if not 1 <= first <= 40:
            raise ValueError("رقم الجهاز يجب أن يكون بين 1 و40.")
        group, shade = divmod(first - 1, 5)
        hue = group / 8
        saturation = 0.72 - shade * 0.025
        light = 0.62 + shade * 0.045
    elif kind == "section":
        grade, section = first, second
        if not 1 <= grade <= 12 or not 1 <= section <= 12:
            raise ValueError("الصف والشعبة يجب أن يكونا بين 1 و12.")
        hue = ((grade - 1) / 12 + 0.54) % 1.0
        saturation = 0.68 - (section - 1) * 0.012
        light = 0.57 + (section - 1) * 0.022
    else:
        raise ValueError("نوع الأيقونة غير معروف.")

    def rgb(value: float) -> tuple[int, int, int]:
        return tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, value))

    return rgb(max(0.38, light - 0.16)), rgb(min(0.92, light + 0.13))


def _draw_generated(kind: str, first: int, second: int, size: int) -> Image.Image:
    start, end = _icon_palette(kind, first, second)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = max(1, round(size * 0.035))
    radius = max(2, round(size * 0.22))
    for x in range(size):
        t = x / max(1, size - 1)
        color = tuple(round(start[c] * (1 - t) + end[c] * t) for c in range(3)) + (255,)
        draw.line((x, 0, x, size), fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1),
                                           radius=radius, fill=255)
    image.putalpha(mask)
    draw = ImageDraw.Draw(image)
    border = tuple(max(0, int(c * 0.55)) for c in start) + (230,)
    draw.rounded_rectangle((pad, pad, size - pad - 1, size - pad - 1),
                           radius=radius, outline=border,
                           width=max(1, round(size * 0.025)))

    if kind == "device":
        code = f"PC{first:02d}"
        lines = [code] if size >= 40 else [f"{first:02d}"]
    else:
        code = f"G{first:02d}-{second:02d}"
        lines = [code] if size >= 96 else ([f"G{first:02d}", f"{second:02d}"] if size >= 32 else [f"{second:02d}"])
    font_size = max(7, round(size * (0.25 if len(lines) == 2 else 0.30)))
    try:
        font = ImageFont.load_default(size=font_size)
    except TypeError:  # Pillow 10.0 compatibility
        font = ImageFont.load_default()
    ink = (255, 255, 255, 255)
    shadow = (0, 0, 0, 95)
    heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    spacing = max(0, round(size * 0.025))
    y = (size - sum(heights) - spacing * (len(lines) - 1)) / 2
    for line, height in zip(lines, heights):
        box = draw.textbbox((0, 0), line, font=font)
        x = (size - (box[2] - box[0])) / 2 - box[0]
        draw.text((x + 1, y + 1), line, font=font, fill=shadow)
        draw.text((x, y), line, font=font, fill=ink)
        y += height + spacing
    return image


def generated_icon_bytes(kind: str, first: int, second: int = 0) -> bytes:
    """Generate a multi-resolution Windows icon on demand."""
    sizes = (16, 24, 32, 48, 64, 128, 256)
    stream = io.BytesIO()
    _draw_generated(kind, first, second, 256).save(
        stream, format="ICO", sizes=[(s, s) for s in sizes]
    )
    return stream.getvalue()


def _write_icon(folder: Path, icon_data: bytes) -> str | None:
    if not folder.is_dir():
        return "المجلد غير موجود."
    ini = folder / "desktop.ini"
    try:
        if sys.platform == "win32":
            _clear_readonly_dir(folder)
        if ini.exists():
            current = ini.read_text(encoding="utf-8", errors="replace")
            if "IconResource=biit-folder.ico,0" not in current:
                if sys.platform == "win32":
                    _set_readonly_dir(folder)
                return "يوجد ملف desktop.ini مخصص لهذا المجلد؛ لم أستبدله."
            if sys.platform == "win32":
                _set_attrs(ini, hidden=False, system=False)
        (folder / ICON_FILE).write_bytes(icon_data)
        if ini.exists():
            lines = ini.read_text(encoding="utf-8", errors="replace").splitlines()
            lines = ["IconResource=biit-folder.ico,0" if line.startswith("IconResource=") else line
                     for line in lines]
            if "[.ShellClassInfo]" not in lines:
                lines.insert(0, "[.ShellClassInfo]")
            ini.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        else:
            ini.write_text(_DESKTOP_INI, encoding="utf-8")
        if sys.platform == "win32":
            _set_attrs(ini, hidden=True, system=True)
            _set_attrs(folder / ICON_FILE, hidden=True, system=False)
            _set_readonly_dir(folder)
    except OSError as exc:
        if sys.platform == "win32":
            _set_readonly_dir(folder)
        return f"تعذّر تطبيق الأيقونة: {exc}"
    return None


def apply_generated_icon(folder: Path, kind: str, first: int, second: int = 0) -> str | None:
    try:
        data = generated_icon_bytes(kind, first, second)
    except (ValueError, OSError) as exc:
        return str(exc)
    return _write_icon(folder, data)


# ---------------------------------------------------------------- win32 bits

_FILE_ATTRIBUTE_READONLY = 0x01
_FILE_ATTRIBUTE_HIDDEN = 0x02
_FILE_ATTRIBUTE_SYSTEM = 0x04


def _set_attrs(path: Path, hidden: bool, system: bool) -> None:
    import ctypes
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        return
    for flag, on in ((_FILE_ATTRIBUTE_HIDDEN, hidden), (_FILE_ATTRIBUTE_SYSTEM, system)):
        attrs = (attrs | flag) if on else (attrs & ~flag)
    ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)


def _set_readonly_dir(folder: Path) -> None:
    import ctypes
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(folder))
    if attrs != -1:
        ctypes.windll.kernel32.SetFileAttributesW(str(folder),
                                                  attrs | _FILE_ATTRIBUTE_READONLY)


def _clear_readonly_dir(folder: Path) -> None:
    import ctypes
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(folder))
    if attrs != -1:
        ctypes.windll.kernel32.SetFileAttributesW(str(folder), attrs & ~_FILE_ATTRIBUTE_READONLY)
