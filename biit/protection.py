"""Windows folder deletion protection with ACL backups and on-demand elevation."""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import locale
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config

EVERYONE_SID = "*S-1-1-0"
PBKDF2_ROUNDS = 310_000


def _store() -> Path:
    path = config.user_dir() / "protection"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path() -> Path:
    return _store() / "backups.json"


def _read_manifest() -> list[dict]:
    try:
        data = json.loads(_manifest_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_manifest(items: list[dict]) -> None:
    config.save_json(_manifest_path(), items)


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def current_identity() -> str:
    if os.name != "nt":
        return ""
    try:
        return subprocess.check_output(["whoami"], text=True, encoding="mbcs",
                                       errors="replace", stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return f"{os.environ.get('COMPUTERNAME', 'COMPUTER')}\\{os.environ.get('USERNAME', '')}"


def file_system_name(folder: str | Path | None = None) -> str | None:
    """Return the volume file system so unsupported ACL volumes are explained early."""
    if os.name != "nt":
        return None
    try:
        candidate = str(Path(folder).resolve(strict=True)) if folder else str(Path.home())
        volume = ctypes.create_unicode_buffer(32768)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetVolumePathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
        kernel32.GetVolumePathNameW.restype = ctypes.c_int
        kernel32.GetVolumeInformationW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.c_wchar_p, ctypes.c_ulong,
        ]
        kernel32.GetVolumeInformationW.restype = ctypes.c_int
        if not kernel32.GetVolumePathNameW(candidate, volume, len(volume)):
            return None
        fs_name = ctypes.create_unicode_buffer(64)
        if not kernel32.GetVolumeInformationW(volume.value, None, 0, None, None, None,
                                             fs_name, len(fs_name)):
            return None
        return fs_name.value
    except (OSError, TypeError, ValueError):
        return None


def resolve_identity(scope: str, custom: str = "") -> str:
    if scope == "current":
        return current_identity()
    if scope == "everyone":
        return EVERYONE_SID
    identity = " ".join(custom.split())
    if scope != "custom" or not identity or len(identity) > 128:
        raise ValueError("اختر هوية صحيحة أو أدخل اسم الحساب بالنمط DOMAIN\\User.")
    if not re.fullmatch(r"[\w.@$\\-]+(?: [\w.@$\\-]+)*", identity, re.UNICODE):
        raise ValueError("صيغة الحساب المخصص غير صالحة.")
    return identity


def validate_folder(value: str) -> Path:
    if os.name != "nt":
        raise ValueError("حماية المجلدات متاحة على Windows فقط.")
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("المسار المحدد ليس مجلدًا.")
    if path == Path(path.anchor):
        raise ValueError("اختر مجلدًا داخل القرص، ولا تحدد جذر القرص.")
    protected_roots = [Path(os.environ.get(k, "__missing__")).resolve()
                       for k in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)")
                       if os.environ.get(k)]
    if any(path == root or root in path.parents for root in protected_roots):
        raise ValueError("لا يمكن تطبيق الحماية على مجلدات Windows أو البرامج.")
    fs_name = file_system_name(path)
    if fs_name and fs_name.casefold() not in {"ntfs", "refs"}:
        raise ValueError(f"نظام الملفات {fs_name} لا يدعم صلاحيات حماية Windows المطلوبة. استخدم مجلداً على NTFS أو ReFS.")
    return path


def password_enabled() -> bool:
    value = config.load_json(_store() / "password.json", {})
    return bool(value.get("salt") and value.get("hash")) if isinstance(value, dict) else False


def set_password(password: str, old_password: str | None = None) -> None:
    if len(password) < 6:
        raise ValueError("كلمة المرور يجب أن تتكون من 6 أحرف على الأقل.")
    path = _store() / "password.json"
    if path.exists() and not check_password(old_password or ""):
        raise ValueError("كلمة المرور الحالية غير صحيحة.")
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    config.save_json(path, {"salt": salt.hex(), "hash": digest.hex(), "rounds": PBKDF2_ROUNDS})


def check_password(password: str) -> bool:
    data = config.load_json(_store() / "password.json", {})
    if not isinstance(data, dict) or not data.get("salt") or not data.get("hash"):
        return True
    try:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(data["salt"]),
                                     int(data.get("rounds", PBKDF2_ROUNDS))).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, str(data["hash"]))


def remove_password(password: str) -> None:
    if not check_password(password):
        raise ValueError("كلمة المرور غير صحيحة.")
    (_store() / "password.json").unlink(missing_ok=True)


def backups() -> list[dict]:
    return list(reversed(_read_manifest()))


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p), ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_ulong), ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def _elevated_run(job: dict) -> dict:
    """Run a one-shot helper using UAC; the main app itself stays unelevated."""
    job_path = _store() / f"job-{secrets.token_hex(8)}.json"
    result_path = job_path.with_suffix(".result.json")
    config.save_json(job_path, {**job, "result_path": str(result_path)})
    if is_admin():
        code = run_helper(str(job_path))
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result = {"ok": False, "detail": "لم تُرجع عملية الصلاحيات نتيجة قابلة للقراءة."}
        finally:
            job_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)
        if code or not result.get("ok"):
            raise OSError(result.get("detail") or "فشلت عملية تعديل صلاحيات المجلد.")
        return result
    # A folder owner can often save or change its ACL without elevation. Try
    # that first, which also works on school devices where the signed-in
    # teacher is not an administrator but owns the selected data folder.
    local_code = run_helper(str(job_path))
    try:
        local_result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        local_result = {"ok": False, "detail": "تعذّر قراءة نتيجة فحص صلاحيات المجلد."}
    if local_code == 0 and local_result.get("ok"):
        job_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
        return local_result
    local_detail = str(local_result.get("detail") or "تعذّر تعديل صلاحيات المجلد بحساب المستخدم الحالي.")
    result_path.unlink(missing_ok=True)
    if "not recognized" in local_detail.casefold() or "لم يتم التعرف" in local_detail:
        job_path.unlink(missing_ok=True)
        raise OSError(local_detail)
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = f'--biit-acl-helper "{job_path}"'
        cwd = str(Path(sys.executable).parent)
    else:
        executable = sys.executable
        runner = Path(__file__).resolve().parent.parent / "run.py"
        params = f'"{runner}" --biit-acl-helper "{job_path}"'
        cwd = str(runner.parent)

    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = params
    info.lpDirectory = cwd
    info.nShow = 0
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = ctypes.c_bool
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        job_path.unlink(missing_ok=True)
        if result_path.exists():
            result_path.unlink(missing_ok=True)
        if err == 1223:
            raise OSError(err, f"أُلغيت مطالبة صلاحيات المسؤول. فشل التنفيذ بالحساب الحالي: {local_detail}")
        raise OSError(err, f"تعذّر تشغيل مطالبة صلاحيات المسؤول (Windows {err}). فشل التنفيذ بالحساب الحالي: {local_detail}")
    try:
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
    finally:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {"ok": False, "detail": "لم تُرجع عملية الصلاحيات نتيجة قابلة للقراءة."}
    finally:
        job_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
    if exit_code.value or not result.get("ok"):
        detail = result.get("detail") or "فشلت عملية تعديل صلاحيات المجلد."
        raise OSError(f"{detail} فشل التنفيذ بالحساب الحالي أيضاً: {local_detail}")
    return result


def _run_icacls(args: list[str]) -> str:
    proc = subprocess.run(["icacls", *args], capture_output=True, text=True,
                          encoding="mbcs", errors="replace", shell=False)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(output.strip() or f"فشل icacls برمز {proc.returncode}.")
    return output.strip()


def run_helper(job_path: str) -> int:
    """Entry point called by the elevated copy of the app."""
    result_path: Path | None = None
    job: dict = {}
    try:
        job = json.loads(Path(job_path).read_text(encoding="utf-8"))
        result_path = Path(job["result_path"])
        folder = str(validate_folder(job["folder"]))
        identity = str(job.get("identity") or "")
        operation = job.get("operation")
        if operation in {"backup", "lock"}:
            backup_file = Path(job["backup_file"])
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            _run_icacls([folder, "/save", str(backup_file), "/t", "/c"])
            if operation == "lock":
                _run_icacls([folder, "/deny", f"{identity}:(CI)(DC)", "/t", "/c"])
                _run_icacls([folder, "/deny", f"{identity}:(OI)(IO)(D)", "/t", "/c"])
                _run_icacls([folder, "/grant", f"{identity}:(R,W)", "/t", "/c"])
        elif operation == "restore":
            backup_file = Path(job["backup_file"])
            if not backup_file.is_file():
                raise FileNotFoundError("ملف نسخة الأذونات غير موجود.")
            _run_icacls([folder, "/restore", str(backup_file), "/c"])
        else:
            raise ValueError("عملية صلاحيات غير معروفة.")
        config.save_json(result_path, {"ok": True})
        return 0
    except Exception as exc:  # noqa: BLE001
        recovery_note = ""
        try:
            if job.get("operation") == "lock" and Path(job["backup_file"]).is_file():
                _run_icacls([str(job["folder"]), "/restore", str(job["backup_file"]), "/c"])
        except Exception as recovery_error:  # noqa: BLE001
            recovery_note = f" وتعذّر الرجوع للصلاحيات السابقة: {recovery_error}"
        if result_path:
            config.save_json(result_path, {"ok": False, "detail": str(exc) + recovery_note})
        return 1


def _new_backup_record(folder: Path, identity: str, locked: bool) -> dict:
    ident = secrets.token_hex(8)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = _store() / "backups" / f"acl_{stamp}_{ident}.txt"
    record = {"id": ident, "folder": str(folder), "identity": identity,
              "backup_file": str(backup_path), "created_at": datetime.now().isoformat(timespec="seconds"),
              "locked": locked, "restored": False, "status": "جارٍ التنفيذ"}
    items = _read_manifest()
    items.append(record)
    _write_manifest(items)
    try:
        _elevated_run({"operation": "lock" if locked else "backup", "folder": str(folder),
                       "identity": identity, "backup_file": str(backup_path)})
        record["status"] = "جاهز"
    except Exception as exc:
        record["status"] = "تعذّر التطبيق؛ نسخة الاستعادة متاحة" if backup_path.is_file() else "فشل"
        record["error"] = str(exc)
        if not backup_path.is_file():
            items = [item for item in items if item.get("id") != ident]
        _write_manifest(items)
        raise
    _write_manifest(items)
    return record


def create_backup(folder_text: str) -> dict:
    folder = validate_folder(folder_text)
    return _new_backup_record(folder, "", False)


def protect(folder_text: str, scope: str, custom: str = "") -> dict:
    folder = validate_folder(folder_text)
    identity = resolve_identity(scope, custom)
    return _new_backup_record(folder, identity, True)


def restore(backup_id: str) -> dict:
    items = _read_manifest()
    item = next((x for x in items if x.get("id") == backup_id), None)
    if not item:
        raise ValueError("نسخة الأذونات غير موجودة.")
    folder = validate_folder(item["folder"])
    backup_file = Path(item["backup_file"])
    _elevated_run({"operation": "restore", "folder": str(folder),
                   "identity": item.get("identity", ""), "backup_file": str(backup_file)})
    item["restored"] = True
    item["restored_at"] = datetime.now().isoformat(timespec="seconds")
    _write_manifest(items)
    return item


def choose_folder(title: str = "اختر مجلدًا") -> str | None:
    if os.name != "nt":
        return None
    safe_title = title.replace("'", "''")
    script = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
              f"$d.Description='{safe_title}'; $d.ShowNewFolderButton=$false; "
              "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
              "{[Console]::Write($d.SelectedPath)}")
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script],
                          capture_output=True, text=True,
                          encoding=locale.getpreferredencoding(False) or "mbcs", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode:
        raise OSError(proc.stderr.strip() or "تعذّر فتح نافذة اختيار المجلد.")
    return proc.stdout.strip() or None


def choose_output_folder(title: str = "اختر مجلد حفظ الملفات") -> str | None:
    return choose_folder(title)
