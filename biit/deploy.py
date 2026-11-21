"""Deployment and collection packages for the lab computers.

One package serves all three transports — what differs is where it lands and
how it is triggered:

  A  network  the package sits in the shared drop folder on the teacher PC and
              each student machine pulls only its own device folders from it
  B  usb      the same package on a flash drive, run machine by machine; the
              collected work rides back on the drive
  C  veyon    the network package, launched on every machine at once through
              Veyon's "Start application"

The direction follows what was actually proven in this lab: student machines
can open the teacher's share; the teacher cannot reach theirs. So deployment
is a pull and collection is a push, both executed on the student machine.

Scripts are generated ASCII-only: cmd.exe reads batch files in the OEM code
page and mangles Arabic literals, so folder names never appear inside a script
— they are walked from the package structure instead. The .bat wrappers exist
for a double-click with a visible window; Veyon calls the .ps1 directly, which
must therefore never pause.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
from datetime import date
from pathlib import Path
from typing import NamedTuple

from . import config
from .naming import section_folder, tree_root_folder
from .roster import Student
from .sections import assigned_slots
from .treegen import G12_SUBFOLDERS, device_folder, section_icon_number

SHARE_NAME = "biitdrop"

_EOL = "\r\n"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def default_deploy_settings() -> dict:
    return {
        "drop_root": "D:\\biitdrop",        # the folder that is shared
        "share_unc": "",                     # \\TEACHER-PC\biitdrop; derived when empty
        "hostname_pattern": r"(\d+)\s*$",   # device number = trailing digits of hostname
        "target_root": "D:\\",              # partition on the student machines
    }


def _deploy_settings_path() -> Path:
    return config.user_dir() / "deploy.json"


def load_deploy_settings() -> dict:
    stored = config.load_json(_deploy_settings_path(), {})
    merged = {**default_deploy_settings(), **(stored if isinstance(stored, dict) else {})}
    if not merged["share_unc"]:
        merged["share_unc"] = f"\\\\{socket.gethostname()}\\{SHARE_NAME}"
    return merged


def save_deploy_settings(data: dict) -> dict:
    clean = default_deploy_settings()
    for key in clean:
        value = str(data.get(key, "")).strip()
        if value:
            clean[key] = value
    try:
        re.compile(clean["hostname_pattern"])
    except re.error:
        clean["hostname_pattern"] = default_deploy_settings()["hostname_pattern"]
    config.save_json(_deploy_settings_path(), clean)
    return load_deploy_settings()


# ---------------------------------------------------------------------------
# Per-device folder structure
# ---------------------------------------------------------------------------

def device_tree(section: dict, settings: dict) -> dict[int, list[str]]:
    """Relative folder paths per device, mirroring treegen's local layout.

    Keys are device numbers that actually hold students; a machine that is out
    of service or empty ships nothing. Paths are relative to the target
    partition root, so `devices/NN/جهاز NN/<section>/...` copies onto the
    same device-first layout under the target partition.
    """
    raw = section.get("students", [])
    students = [Student(s.get("name", ""), s.get("key", ""), i, s.get("suspect", False))
                for i, s in enumerate(raw)]
    cfg = section.get("devices") or {}
    dead = {int(d) for d in cfg.get("disabled", [])}
    slots = assigned_slots(section, settings["device_count"], students)

    grade = int(section["grade"])
    tree_root = tree_root_folder(settings["semester"], settings["academic_year"],
                                 settings["naming_lang"])
    section_count = int(settings.get("grade_section_count", 1))
    term = section_folder(grade, str(section["label"]), settings["semester"],
                          settings["academic_year"], settings["naming_lang"],
                          include_label=section_count > 1)
    out: dict[int, list[str]] = {}
    for slot in slots:
        if slot.device_no in dead:
            continue
        seated = [students[i] for i in (slot.primary, slot.secondary) if i >= 0]
        if not seated:
            continue
        device_dir = device_folder(slot.device_no)
        dirs: list[str] = [tree_root, f"{tree_root}/{device_dir}",
                           f"{tree_root}/{device_dir}/{term}"]
        for st in seated:
            student_dir = f"{tree_root}/{device_dir}/{term}/{st.name}"
            dirs.append(student_dir)
            if grade == 12:
                dirs.extend(f"{student_dir}/{sub}" for sub in G12_SUBFOLDERS)
        out[slot.device_no] = dirs
    return out


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

class PackageInfo(NamedTuple):
    root: Path                 # the package folder that was written
    label: str
    devices: list[int]         # device numbers included
    folder_count: int
    deploy_unc: str            # what to run on a student machine (network/veyon)
    veyon_command: str
    file_count: int = 0        # files included below the packaged student folders


def _write_script(path: Path, text: str) -> None:
    path.write_text(text.replace("\n", _EOL), encoding="ascii", newline="")


def build_package(section: dict, transport: str, app_settings: dict,
                  deploy_settings: dict, usb_root: str | None = None) -> PackageInfo:
    """Write the package for one section. transport: "network" or "usb"."""
    label = str(section["label"])
    if transport == "usb":
        if not usb_root:
            raise ValueError("حدد قرص الفلاش أولًا.")
        base = Path(usb_root) / "BiTT"
    else:
        base = Path(deploy_settings["drop_root"])
    pkg = base / "deploy" / label
    pkg.mkdir(parents=True, exist_ok=True)

    app_settings = dict(app_settings)
    app_settings["grade_section_count"] = sum(
        1 for item in app_settings.get("sections", [])
        if int(item.get("grade", 0)) == int(section["grade"]))
    grade = int(section["grade"])
    sec_name = section_folder(grade, label, app_settings["semester"],
                              app_settings["academic_year"], app_settings["naming_lang"],
                              include_label=app_settings["grade_section_count"] > 1)
    tree = device_tree(section, app_settings)
    count = 0
    for no, dirs in tree.items():
        for rel in dirs:
            (pkg / "devices" / f"{no:02d}" / rel).mkdir(parents=True, exist_ok=True)
            count += 1

    # Include teacher-provided files from the master tree. Student work is
    # collected into a separate inbox, so this only mirrors teacher-side
    # student folders. Never replace a file already present in the package.
    from .drives import list_drives
    location = config.resolve_location(config.load_location(), list_drives())
    payload_roots: list[Path] = []
    if location.get("status") in ("ok", "moved"):
        location_root = Path(location["root"]).resolve()
        # device_tree() paths are relative to the selected drive root and
        # already begin with the whole-tree directory.
        matrix_root = location_root
        section_root = location_root / section_folder(
            grade, label, app_settings["semester"], app_settings["academic_year"],
            app_settings["naming_lang"], include_label=app_settings["grade_section_count"] > 1)
        student_names = {str(st.get("name") or "") for st in section.get("students", [])}
        copied: set[Path] = set()
        for no, dirs in tree.items():
            for rel in dirs:
                rel_path = Path(rel.replace("/", os.sep))
                if rel_path.name not in student_names or rel_path.parent.name != sec_name:
                    continue
                matrix_student = (matrix_root / rel_path).resolve()
                direct_student = (section_root / rel_path.name).resolve() if grade == 12 else None
                source_student = (matrix_student if matrix_student.is_dir() else
                                  direct_student if direct_student and direct_student.is_dir() else None)
                if source_student is None:
                    continue
                try:
                    source_student.relative_to(location_root)
                except ValueError:
                    continue
                package_student = (pkg / "devices" / f"{no:02d}" / rel_path).resolve()
                try:
                    package_student.relative_to(pkg.resolve())
                except ValueError:
                    continue
                payload_roots.append(package_student)
                for source_file in source_student.rglob("*"):
                    if not source_file.is_file() or source_file.is_symlink():
                        continue
                    try:
                        source_file.resolve().relative_to(location_root)
                    except ValueError:
                        continue
                    target_file = package_student / source_file.relative_to(source_student)
                    if target_file in copied:
                        continue
                    copied.add(target_file)
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    created_target = False
                    try:
                        with source_file.open("rb") as src:
                            with target_file.open("xb") as dst:
                                created_target = True
                                shutil.copyfileobj(src, dst, length=1024 * 1024)
                        shutil.copystat(source_file, target_file)
                    except FileExistsError:
                        continue
                    except Exception:
                        if created_target:
                            target_file.unlink(missing_ok=True)
                        raise
    file_count = sum(1 for root in set(payload_roots) if root.is_dir()
                     for item in root.rglob("*") if item.is_file() and not item.is_symlink())

    # The package mirrors the local device-first tree, including its generated
    # device and section icons. They travel with the folders when copied.
    from .foldericon import apply_generated_icon
    sec_no = section_icon_number(label)
    tree_root = tree_root_folder(app_settings["semester"], app_settings["academic_year"],
                                 app_settings["naming_lang"])
    for no in tree:
        base = pkg / "devices" / f"{no:02d}"
        device_path = base / tree_root / device_folder(no)
        apply_generated_icon(device_path, "device", no)
        if sec_no:
            apply_generated_icon(device_path / sec_name, "section", grade, sec_no)

    unc_pkg = f"{deploy_settings['share_unc']}\\deploy\\{label}"
    cfg = {
        "label": label,
        "hostname_pattern": deploy_settings["hostname_pattern"],
        "target_root": deploy_settings["target_root"],
        # usb: collected work rides back on the drive, two levels up from here
        "collect_dest": ("..\\..\\collect" if transport == "usb"
                         else f"{deploy_settings['share_unc']}\\collect"),
        "collect_relative": transport == "usb",
    }
    (pkg / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                     encoding="utf-8")

    _write_script(pkg / "deploy.ps1", _DEPLOY_PS1)
    _write_script(pkg / "collect.ps1", _COLLECT_PS1)
    _write_script(pkg / "deploy.bat", _bat("deploy.ps1"))
    _write_script(pkg / "collect.bat", _bat("collect.ps1"))

    return PackageInfo(
        root=pkg, label=label, devices=sorted(tree), folder_count=count,
        deploy_unc=f"{unc_pkg}\\deploy.bat",
        veyon_command=("powershell -NoProfile -ExecutionPolicy Bypass -File "
                       f"\"{unc_pkg}\\deploy.ps1\""),
        file_count=file_count,
    )


def veyon_collect_command(label: str, deploy_settings: dict) -> str:
    unc_pkg = f"{deploy_settings['share_unc']}\\deploy\\{label}"
    return ("powershell -NoProfile -ExecutionPolicy Bypass -File "
            f"\"{unc_pkg}\\collect.ps1\"")


# ---------------------------------------------------------------------------
# Collection inbox
# ---------------------------------------------------------------------------

def scan_inbox(deploy_settings: dict, sections: list[dict],
               app_settings: dict) -> list[dict]:
    """What has arrived in <drop_root>/collect, newest day first.

    Every batch is compared with the section's expected devices, so the
    machines that have not handed anything in are named, not merely absent.
    """
    root = Path(deploy_settings["drop_root"]) / "collect"
    expected = {str(s["label"]): sorted(device_tree(s, app_settings))
                for s in sections}
    out: list[dict] = []
    if not root.exists():
        return out
    for label_dir in sorted(root.iterdir()):
        if not label_dir.is_dir():
            continue
        for day_dir in sorted(label_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            devices = []
            for dev_dir in sorted(day_dir.iterdir()):
                if not dev_dir.is_dir() or not dev_dir.name.isdigit():
                    continue
                files = [f for f in dev_dir.rglob("*") if f.is_file()]
                devices.append({
                    "device_no": int(dev_dir.name),
                    "files": len(files),
                    "bytes": sum(f.stat().st_size for f in files),
                })
            arrived = {d["device_no"] for d in devices}
            missing = [n for n in expected.get(label_dir.name, []) if n not in arrived]
            out.append({
                "label": label_dir.name,
                "date": day_dir.name,
                "devices": devices,
                "missing": missing,
            })
    return out


def import_usb_collect(usb_root: str, deploy_settings: dict) -> dict:
    """Merge <usb>/BiTT/collect into the drop folder's inbox, never overwriting."""
    src = Path(usb_root) / "BiTT" / "collect"
    if not src.exists():
        raise FileNotFoundError("لا يوجد مجلد تجميع على هذا القرص (BiTT\\collect).")
    dest = Path(deploy_settings["drop_root"]) / "collect"
    copied = skipped = 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        target = dest / f.relative_to(src)
        if target.exists():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
        copied += 1
    return {"copied": copied, "skipped": skipped}


# ---------------------------------------------------------------------------
# Generated scripts (ASCII only — see module docstring)
# ---------------------------------------------------------------------------

def _bat(ps1: str) -> str:
    return f"""@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{ps1}"
echo.
pause
"""


_DEVICE_NO_PS1 = r"""
$state = Join-Path $env:ProgramData 'BiitAssistant'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$noFile = Join-Path $state 'device_no.txt'
$no = $null
if ($env:COMPUTERNAME -match $cfg.hostname_pattern) {
    $no = [int]$Matches[1]
} elseif (Test-Path $noFile) {
    $no = [int](Get-Content $noFile | Select-Object -First 1)
} else {
    $no = [int](Read-Host 'Device number / raqm al-jihaz')
    Set-Content -Path $noFile -Value $no
}
$nn = '{0:00}' -f $no
"""


_DEPLOY_PS1 = r"""# BiTT Assistant - deploy: copy this device's folders onto this machine.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cfg  = Get-Content -Raw -Path (Join-Path $here 'config.json') | ConvertFrom-Json
""" + _DEVICE_NO_PS1 + r"""
$src = Join-Path $here ('devices\' + $nn)
if (-not (Test-Path $src)) {
    Write-Host ('Nothing packaged for device ' + $nn + '.')
    exit 0
}
$root = $cfg.target_root
if (-not (Test-Path $root)) { $root = 'C:\' }

# /XC /XN /XO: existing files are never overwritten.
robocopy $src $root /E /XC /XN /XO /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Write-Host 'Copy failed.'; exit 1 }

$roots = Get-ChildItem -Directory $src | ForEach-Object { Join-Path $root $_.Name }
$record = @{ label = $cfg.label; device = $no; roots = @($roots) } | ConvertTo-Json
Set-Content -Path (Join-Path $state ('deployed-' + $cfg.label + '.json')) -Value $record
Write-Host ('Device ' + $nn + ': folders ready under ' + $root)
exit 0
"""


_COLLECT_PS1 = r"""# BiTT Assistant - collect: send this device's work back to the teacher.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cfg  = Get-Content -Raw -Path (Join-Path $here 'config.json') | ConvertFrom-Json
""" + _DEVICE_NO_PS1 + r"""
$record = Join-Path $env:ProgramData ('BiitAssistant\deployed-' + $cfg.label + '.json')
if (-not (Test-Path $record)) {
    Write-Host 'Nothing was deployed on this machine for this section.'
    exit 0
}
$info = Get-Content -Raw -Path $record | ConvertFrom-Json

$dest = $cfg.collect_dest
if ($cfg.collect_relative) { $dest = Join-Path (Split-Path -Parent $here) $cfg.collect_dest }
$day  = Get-Date -Format 'yyyy-MM-dd'
$out  = Join-Path $dest ($cfg.label + '\' + $day + '\' + $nn)
New-Item -ItemType Directory -Force -Path $out | Out-Null

$sent = 0
foreach ($r in $info.roots) {
    if (-not (Test-Path $r)) { continue }
    $leaf = Split-Path -Leaf $r
    robocopy $r (Join-Path $out $leaf) /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Host ('Failed: ' + $r); exit 1 }
    $sent++
}
Write-Host ('Device ' + $nn + ': ' + $sent + ' folder(s) handed in.')
exit 0
"""
