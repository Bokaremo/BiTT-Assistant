"""Local backend. Listens on 127.0.0.1 only."""

from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from typing import Callable

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import APP_NAME, __version__, config, naming
from .drives import list_drives
from .roster import ImportResult, import_roster
from .sections import (  # explicit – PyInstaller traces this correctly
    load_sections, save_sections, upsert_section, delete_section,
    assign_devices, assigned_slots, validate_label, Section, GradeGroup, DeviceSlot,
    find_section, rename_student, save_device_layout, section_slots,
    unseated_count,
)
from .treegen import FolderPlan, execute_tree, plan_matrix_tree, plan_tree
from . import protection, projectforms, studentcards, transfers

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


def web_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "biit" / "web"


def create_app(
    token: str,
    runtime: dict | None = None,
    drive_provider: Callable[[], list[dict]] = list_drives,
    on_shutdown: Callable[[], None] | None = None,
) -> FastAPI:
    runtime = runtime if runtime is not None else {"mode": "browser"}
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    web = web_dir()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Host check stops DNS-rebinding; the token stops other web pages
        # from calling the API through the teacher's browser.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "طلب مرفوض."}, status_code=403)
        if request.url.path.startswith("/api/"):
            sent = request.headers.get("x-biit-token", "")
            if not hmac.compare_digest(sent, token):
                return JSONResponse({"detail": "طلب مرفوض."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        html = (web / "index.html").read_text(encoding="utf-8")
        return html.replace("{{TOKEN}}", token).replace("{{VERSION}}", __version__)

    def location_state(drives: list[dict]) -> dict:
        return config.resolve_location(config.load_location(), drives)

    @app.get("/api/state")
    def state():
        settings = config.load_settings()
        return {
            "version": __version__,
            "mode": runtime.get("mode", "browser"),
            "settings": settings,
            "settings_saved": config.settings_saved_fields(),
            "limits": {"min_devices": config.MIN_DEVICES, "max_devices": config.MAX_DEVICES},
            "location": location_state(drive_provider()),
        }

    @app.put("/api/settings")
    def put_settings(data: dict = Body(...)):
        clean, errors = config.validate_settings(data)
        if errors:
            return JSONResponse(
                {"detail": "راجع الحقول المحددة.", "fields": errors}, status_code=422
            )
        config.save_settings(clean)
        return {"settings": clean}

    @app.get("/api/naming")
    def naming_preview(academic_year: str, semester: int, naming_lang: str):
        try:
            return {
                "grades": {
                    str(g): naming.term_folder(g, semester, academic_year.replace("/", "-"), naming_lang)
                    for g in (5, 11, 12)
                }
            }
        except ValueError:
            raise HTTPException(400, "بيانات التسمية غير مكتملة.")

    @app.get("/api/drives")
    def drives():
        found = drive_provider()
        return {"drives": found, "location": location_state(found)}

    @app.put("/api/location")
    def put_location(data: dict = Body(...)):
        letter = str(data.get("letter", "")).upper()[:1]
        found = drive_provider()
        drive = next((d for d in found if d["letter"] == letter), None)
        if drive is None:
            raise HTTPException(400, "القرص المختار لم يعد موجودًا. حدّث القائمة واختر من جديد.")
        if not drive.get("writable"):
            raise HTTPException(400, "لا يمكن إنشاء مجلدات على هذا القرص. اختر قرصًا آخر.")
        config.save_location(drive)
        return {"location": location_state(found)}

    # ---------------------------------------------------------- helper tools
    @app.post("/api/dialog/folder")
    def choose_folder_dialog(data: dict = Body(default={} )):
        try:
            path = protection.choose_folder(str(data.get("title") or "اختر مجلدًا"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"تعذّر فتح نافذة اختيار المجلد: {exc}")
        return {"path": path}

    @app.get("/api/protection/state")
    def protection_state():
        return {"admin": protection.is_admin(), "identity": protection.current_identity(),
                "file_system": protection.file_system_name(),
                "password_enabled": protection.password_enabled(),
                "backups": protection.backups()}

    @app.post("/api/protection/plan")
    def protection_plan(data: dict = Body(...)):
        try:
            folder = protection.validate_folder(str(data.get("folder") or ""))
            identity = protection.resolve_identity(str(data.get("scope") or "current"),
                                                   str(data.get("custom") or ""))
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc))
        return {"folder": str(folder), "identity": identity,
                "action": "منع حذف محتويات المجلد مع إبقاء القراءة والكتابة",
                "file_system": protection.file_system_name(folder),
                "admin": protection.is_admin()}

    @app.post("/api/protection/lock")
    def protection_lock(data: dict = Body(...)):
        try:
            item = protection.protect(str(data.get("folder") or ""),
                                      str(data.get("scope") or "current"),
                                      str(data.get("custom") or ""))
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc))
        return {"backup": item, "backups": protection.backups()}

    @app.post("/api/protection/backup")
    def protection_backup(data: dict = Body(...)):
        try:
            item = protection.create_backup(str(data.get("folder") or ""))
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc))
        return {"backup": item, "backups": protection.backups()}

    @app.post("/api/protection/restore/{backup_id}")
    def protection_restore(backup_id: str, data: dict = Body(default={} )):
        if protection.password_enabled() and not protection.check_password(str(data.get("password") or "")):
            raise HTTPException(403, "كلمة مرور الحماية غير صحيحة.")
        try:
            item = protection.restore(backup_id)
        except (OSError, ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc))
        return {"restored": item, "backups": protection.backups()}

    @app.put("/api/protection/password")
    def protection_password(data: dict = Body(...)):
        try:
            protection.set_password(str(data.get("new_password") or ""),
                                    str(data.get("old_password") or ""))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"password_enabled": True}

    @app.delete("/api/protection/password")
    def protection_password_remove(data: dict = Body(default={} )):
        try:
            protection.remove_password(str(data.get("password") or ""))
        except ValueError as exc:
            raise HTTPException(403, str(exc))
        return {"password_enabled": False}

    @app.get("/api/project-forms/state")
    def project_forms_state():
        sections = [s for s in load_sections() if int(s.get("grade", 0)) == 12]
        return {"sections": [{"grade": s["grade"], "label": s["label"],
                               "students": len(s.get("students", [])),
                               "roster": [{"index": i, "name": st.get("name", "")}
                                          for i, st in enumerate(s.get("students", []))]}
                              for s in sections],
                "output_directory": projectforms.output_directory(),
                "settings": config.load_settings(),
                "customization": projectforms.load_customization()}

    @app.put("/api/project-forms/customization")
    def project_forms_customization_put(data: dict = Body(...)):
        clean, errors = projectforms.validate_customization(data)
        if errors:
            return JSONResponse(
                {"detail": "راجع إعدادات استمارات المشاريع.", "fields": errors},
                status_code=422,
            )
        projectforms.save_customization(clean)
        return {"customization": clean}

    @app.post("/api/project-forms/output")
    def project_forms_output(data: dict = Body(default={} )):
        path = data.get("path")
        if not path:
            path = protection.choose_output_folder("اختر مجلد حفظ استمارات المشاريع")
        if not path:
            return {"path": None}
        try:
            return {"path": projectforms.set_output_directory(str(path))}
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/project-forms/generate")
    def project_forms_generate(data: dict = Body(...)):
        try:
            grade, label = int(data.get("grade")), str(data.get("label") or "")
        except (TypeError, ValueError):
            raise HTTPException(422, "اختر شعبة صحيحة.")
        section = find_section(grade, label)
        if section is None:
            raise HTTPException(404, "الشعبة المحددة غير موجودة.")
        settings = config.load_settings()
        customization = projectforms.load_customization()
        output = str(data.get("output_directory") or projectforms.output_directory())
        try:
            result = projectforms.generate(section, settings["semester"],
                                           settings["academic_year"], output,
                                           int(data.get("group_size", customization["project_form_group_size"])),
                                           settings=settings, customization=customization,
                                           manual_groups=data.get("manual_groups")
                                           if data.get("manual") else None)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc))
        return result

    @app.post("/api/project-forms/preview")
    def project_forms_preview(data: dict = Body(...)):
        try:
            grade, label = int(data.get("grade")), str(data.get("label") or "")
            group_size = int(data.get("group_size", 5))
        except (TypeError, ValueError):
            raise HTTPException(422, "اختر شعبة وحجم مجموعة صحيحين.")
        section = find_section(grade, label)
        if section is None:
            raise HTTPException(404, "الشعبة المحددة غير موجودة.")
        try:
            groups = projectforms.preview(section, group_size,
                                          data.get("manual_groups") if data.get("manual") else None)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"groups": groups, "semester": config.load_settings()["semester"]}

    @app.get("/api/transfers/state")
    def transfers_state(grade: int, label: str):
        root = _location_root()
        if not root:
            raise HTTPException(400, "موقع إنشاء الشجرة غير متاح الآن.")
        try:
            return transfers.section_state(root, load_sections(), config.load_settings(),
                                           int(grade), label)
        except (OSError, TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/transfers/execute")
    def transfers_execute(data: dict = Body(...)):
        root = _location_root()
        if not root:
            raise HTTPException(400, "موقع إنشاء الشجرة غير متاح الآن.")
        try:
            return transfers.move_students(
                root, load_sections(), config.load_settings(), int(data.get("grade")),
                str(data.get("label") or ""),
                [int(i) for i in data.get("student_indices", [])],
                int(data.get("target_device")))
        except (OSError, TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/student-cards/import")
    async def student_cards_import(request: Request):
        try:
            form = await request.form()
        except Exception:
            raise HTTPException(400, "أرسل ملف سجل التقويم.")
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "اختر ملف سجل التقويم.")
        import shutil, tempfile
        suffix = Path(getattr(upload, "filename", "marks.xlsx")).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(upload.file, tmp)
            tmp_path = tmp.name
        try:
            return studentcards.parse_assessment(tmp_path, config.load_settings()["semester"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @app.get("/api/student-cards/style")
    def student_cards_style_get(class_info: str = "", section_label: str = ""):
        return {"style": studentcards.get_card_style(class_info, section_label),
                "styles": studentcards.CARD_STYLES}

    @app.put("/api/student-cards/style")
    def student_cards_style_put(data: dict = Body(...)):
        try:
            style = studentcards.set_card_style(
                str(data.get("class_info") or ""),
                str(data.get("section_label") or ""),
                str(data.get("style") or ""),
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"style": style}

    # ------------------------------------------------------------------ roster
    @app.post("/api/roster/import")
    async def roster_import(request: Request):
        """Accept multipart/form-data with field 'file' (xlsx or pdf)."""
        try:
            form = await request.form()
        except Exception:
            raise HTTPException(400, "الطلب لا يحتوي على ملف.")
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "أرسل الملف في حقل 'file'.")
        import tempfile, shutil
        suffix = Path(getattr(upload, "filename", "file.xlsx")).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(upload.file, tmp)
            tmp_path = tmp.name
        result: ImportResult = import_roster(tmp_path)
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        if result.errors:
            raise HTTPException(422, " — ".join(result.errors))
        return {
            "students": [{"name": s.name, "key": s.key, "suspect": s.suspect}
                         for s in result.students],
            "warnings": result.warnings,
            "count": len(result.students),
            "grade": result.grade,
            "label": result.label,
        }

    @app.post("/api/roster/import-batch")
    async def roster_import_batch(request: Request):
        """Import several rosters at once, one section per file.

        Each MOE roster names its own grade and section in the header, so a whole
        year's worth of files can be dropped in together. A file whose header is
        unreadable is reported back by name rather than guessed at, and the rest
        still import.
        """
        import shutil
        import tempfile

        try:
            form = await request.form()
        except Exception:
            raise HTTPException(400, "الطلب لا يحتوي على ملفات.")
        uploads = form.getlist("files")
        if not uploads:
            raise HTTPException(400, "أرسل الملفات في حقل 'files'.")

        imported: list[dict] = []
        skipped: list[dict] = []
        for upload in uploads:
            filename = Path(getattr(upload, "filename", "")).name or "ملف"
            suffix = Path(filename).suffix or ".pdf"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                shutil.copyfileobj(upload.file, tmp)
                tmp_path = tmp.name
            try:
                res: ImportResult = import_roster(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if res.errors:
                skipped.append({"file": filename, "reason": " — ".join(res.errors)})
                continue
            if res.grade is None or not res.label:
                skipped.append({
                    "file": filename,
                    "reason": "تعذّر تحديد الصف والشعبة من الملف — استورده منفردًا وحدّدهما يدويًا.",
                })
                continue
            if validate_label(res.label):
                skipped.append({"file": filename, "reason": "رمز شعبة غير صالح في الملف."})
                continue
            upsert_section(res.grade, res.label, res.students)
            imported.append({
                "file": filename,
                "grade": res.grade,
                "label": res.label,
                "count": len(res.students),
                "suspect": sum(1 for s in res.students if s.suspect),
            })

        if not imported and skipped:
            raise HTTPException(422, skipped[0]["reason"])
        return {"imported": imported, "skipped": skipped, "sections": load_sections()}

    # ---------------------------------------------------------------- sections
    @app.get("/api/sections")
    def get_sections():
        return {"sections": load_sections()}

    @app.put("/api/sections/{grade}/{label}")
    def put_section(grade: int, label: str, data: dict = Body(...)):
        err = validate_label(label)
        if err:
            raise HTTPException(422, err)
        if grade not in range(1, 13):
            raise HTTPException(422, "الصف يجب أن يكون بين 1 و12.")
        raw_students = data.get("students", [])
        from .roster import Student
        from .roster import normalise, match_key
        students = []
        seen = set()
        for i, raw in enumerate(raw_students):
            name = normalise(str(raw.get("name", "")))
            key = match_key(name)
            if len(name.split()) < 2:
                raise HTTPException(422, f"اسم الطالب رقم {i + 1} يجب أن يتكوّن من كلمتين على الأقل.")
            if key in seen:
                raise HTTPException(422, f"يوجد اسم مكرر في القائمة عند الطالب رقم {i + 1}.")
            seen.add(key)
            students.append(Student(name, key, i, bool(raw.get("suspect", False))))
        upsert_section(grade, label, students)
        return {"sections": load_sections()}

    @app.delete("/api/sections/{grade}/{label}")
    def del_section(grade: int, label: str):
        delete_section(grade, label)
        return {"sections": load_sections()}

    @app.patch("/api/sections/{grade}/{label}/students/{index}")
    def patch_student(grade: int, label: str, index: int, data: dict = Body(...)):
        err = rename_student(grade, label, index, str(data.get("name", "")))
        if err:
            raise HTTPException(422, err)
        return {"sections": load_sections()}

    # ------------------------------------------------------------- device plan
    @app.get("/api/devices")
    def get_all_devices():
        """Every section's device layout in one call.

        The devices screen needs all of them at once; asking per section fired a
        burst of parallel reads of the same file for no gain.
        """
        count = config.load_settings().get("device_count", 0)
        return {
            "device_count": count,
            "sections": [
                {
                    "grade": sec["grade"],
                    "label": sec["label"],
                    "students": sec.get("students", []),
                    "slots": section_slots(sec, count),
                    "unseated": unseated_count(sec, count),
                    "config": sec.get("devices") or {"disabled": [], "pinned": {}},
                }
                for sec in load_sections()
            ],
        }

    @app.get("/api/sections/{grade}/{label}/devices")
    def get_devices(grade: int, label: str):
        sec = find_section(grade, label)
        if sec is None:
            raise HTTPException(404, "الشعبة غير موجودة.")
        count = config.load_settings().get("device_count", 0)
        return {
            "slots": section_slots(sec, count),
            "unseated": unseated_count(sec, count),
            "config": sec.get("devices") or {"disabled": [], "pinned": {}},
        }

    @app.put("/api/sections/{grade}/{label}/devices")
    def put_devices(grade: int, label: str, data: dict = Body(...)):
        err = save_device_layout(
            grade, label,
            [int(d) for d in data.get("disabled", [])],
            {str(k): str(v) for k, v in (data.get("pinned") or {}).items()},
        )
        if err:
            raise HTTPException(422, err)
        sec = find_section(grade, label)
        count = config.load_settings().get("device_count", 0)
        return {
            "slots": section_slots(sec, count),
            "unseated": unseated_count(sec, count),
            "config": sec.get("devices"),
        }

    # ---------------------------------------------------------------- tree plan
    def _build_plan(data: dict, missing_location: str):
        """Build the selected-section or whole-school device-first plan."""
        settings = config.load_settings()
        loc = config.resolve_location(config.load_location(), drive_provider())
        if loc.get("status") not in ("ok", "moved"):
            raise HTTPException(400, missing_location)

        mode = str(data.get("mode") or "section")
        if mode == "matrix":
            sections = load_sections()
            if not any(s.get("students") for s in sections):
                raise HTTPException(422, "لا توجد شعب بقوائم طلبة لإنشائها.")
            return plan_matrix_tree(
                Path(loc["root"]), sections, settings["semester"],
                settings["academic_year"], settings["naming_lang"],
                settings["device_count"],
            )
        if mode != "section":
            raise HTTPException(422, "اختر الشجرة الشاملة أو شعبة واحدة.")

        from .roster import Student
        raw_grade = data.get("grade")
        label = str(data.get("label") or "").strip()
        try:
            grade = int(raw_grade)
        except (TypeError, ValueError):
            raise HTTPException(422, "رقم الصف غير صالح.")
        if not label:
            raise HTTPException(422, "أرسل grade و label.")

        section = find_section(grade, label)
        if section is None:
            raise HTTPException(404, "الشعبة غير موجودة.")
        raw = section.get("students", [])
        if not raw:
            raise HTTPException(422, "لا يوجد طلبة في هذه الشعبة.")

        students = [Student(s["name"], s["key"], i, s.get("suspect", False))
                    for i, s in enumerate(raw)]
        # Use the teacher's own layout, so the folders match where students sit.
        cfg = section.get("devices") or {}
        dead = {int(d) for d in cfg.get("disabled", [])}
        by_key = {s.key: i for i, s in enumerate(students)}
        slots = assigned_slots(section, settings["device_count"], students)
        return plan_tree(Path(loc["root"]), grade,
                         settings["semester"], settings["academic_year"],
                         settings["naming_lang"], students, slots, skip_devices=dead,
                         section_label=label,
                         include_section_label=sum(
                             1 for item in load_sections()
                             if int(item.get("grade", 0)) == grade) > 1)

    # ------------------------------------------------------ reports & analysis
    def _location_root() -> str | None:
        loc = config.resolve_location(config.load_location(), drive_provider())
        return loc.get("root") if loc.get("status") in ("ok", "moved") else None

    @app.get("/api/reports/distribution")
    def reports_distribution():
        from .reports import distribution_guide
        settings = config.load_settings()
        return {"settings": settings,
                "guide": distribution_guide(load_sections(), settings)}

    @app.get("/api/reports/student")
    def reports_student(q: str = ""):
        from .deploy import load_deploy_settings, scan_inbox
        from .reports import find_students
        settings = config.load_settings()
        sections = load_sections()
        inbox = scan_inbox(load_deploy_settings(), sections, settings)
        return {"matches": find_students(q, sections, settings,
                                         _location_root(), inbox)}

    @app.get("/api/reports/devices/{grade}/{label}")
    def reports_devices(grade: int, label: str):
        from .deploy import load_deploy_settings, scan_inbox
        from .reports import device_report
        section = find_section(grade, label)
        if section is None:
            raise HTTPException(404, "الشعبة غير موجودة.")
        settings = config.load_settings()
        inbox = scan_inbox(load_deploy_settings(), [section], settings)
        return device_report(section, settings, inbox)

    # ------------------------------------------------------- archive & reset
    @app.get("/api/maintenance/archive/plan")
    def maintenance_archive_plan():
        from .maintenance import archive_plan
        root = _location_root()
        if not root:
            raise HTTPException(400, "لم يُحدد موقع الإنشاء بعد.")
        return archive_plan(root)

    @app.post("/api/maintenance/archive")
    def maintenance_archive():
        from .maintenance import archive_execute
        root = _location_root()
        if not root:
            raise HTTPException(400, "لم يُحدد موقع الإنشاء بعد.")
        try:
            return archive_execute(root)
        except OSError as exc:
            raise HTTPException(500, str(exc))

    @app.post("/api/maintenance/reset")
    def maintenance_reset(data: dict = Body(...)):
        from .maintenance import factory_reset
        try:
            factory_reset(str(data.get("confirm", "")))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"ok": True}

    # --------------------------------------------------------- deploy/collect
    @app.get("/api/deploy/settings")
    def deploy_settings_get():
        from .deploy import load_deploy_settings
        return {
            "settings": load_deploy_settings(),
            "removable": [d for d in drive_provider() if d.get("kind") == "removable"],
            "sections": [
                {"grade": s["grade"], "label": s["label"],
                 "students": len(s.get("students", []))}
                for s in load_sections() if s.get("students")
            ],
        }

    @app.put("/api/deploy/settings")
    def deploy_settings_put(data: dict = Body(...)):
        from .deploy import save_deploy_settings
        return {"settings": save_deploy_settings(data)}

    @app.post("/api/deploy/package")
    def deploy_package(data: dict = Body(...)):
        from .deploy import build_package, load_deploy_settings, veyon_collect_command

        try:
            grade = int(data.get("grade"))
        except (TypeError, ValueError):
            raise HTTPException(422, "رقم الصف غير صالح.")
        label = str(data.get("label") or "").strip()
        transport = data.get("transport")
        if transport not in ("network", "usb"):
            raise HTTPException(422, "اختر وسيلة النشر: الشبكة أو الفلاش.")
        section = find_section(grade, label)
        if section is None:
            raise HTTPException(404, "الشعبة غير موجودة.")
        if not section.get("students"):
            raise HTTPException(422, "لا يوجد طلبة في هذه الشعبة.")

        ds = load_deploy_settings()
        try:
            package_settings = config.load_settings()
            package_settings["sections"] = load_sections()
            info = build_package(section, transport, package_settings, ds,
                                 usb_root=data.get("usb_root"))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except OSError as exc:
            raise HTTPException(500, f"تعذّرت كتابة الحزمة: {exc}")
        return {
            "package_root": str(info.root),
            "label": info.label,
            "devices": info.devices,
            "folder_count": info.folder_count,
            "file_count": info.file_count,
            "deploy_unc": info.deploy_unc,
            "veyon_deploy": info.veyon_command,
            "veyon_collect": veyon_collect_command(info.label, ds),
        }

    @app.get("/api/collect/inbox")
    def collect_inbox():
        from .deploy import load_deploy_settings, scan_inbox
        return {"batches": scan_inbox(load_deploy_settings(), load_sections(),
                                      config.load_settings())}

    @app.post("/api/collect/import-usb")
    def collect_import_usb(data: dict = Body(...)):
        from .deploy import import_usb_collect, load_deploy_settings
        usb_root = str(data.get("usb_root") or "").strip()
        if not usb_root:
            raise HTTPException(422, "اختر قرص الفلاش.")
        try:
            result = import_usb_collect(usb_root, load_deploy_settings())
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc))
        except OSError as exc:
            raise HTTPException(500, f"تعذّر الاستيراد: {exc}")
        return result

    @app.post("/api/tree/plan")
    def tree_plan(data: dict = Body(...)):
        plan = _build_plan(data, "لم يُحدد موقع الإنشاء بعد. اختر القرص أولًا.")
        return {
            "root": str(plan.root),
            "new_count": len(plan.new_dirs),
            "existing_count": len(plan.existing_dirs),
            "new_dirs": [str(d) for d in plan.new_dirs[:50]],   # preview cap
            "total_students": plan.total_students,
            "mode": plan.mode,
            "section_count": plan.section_count,
            "device_count": plan.device_count,
        }

    @app.get("/api/icons")
    def list_folder_icons():
        from .foldericon import list_icons
        return {"icons": list_icons(web_dir())}

    @app.post("/api/tree/open")
    def tree_open(data: dict = Body(...)):
        """Open a planned tree path, constrained to the selected creation drive."""
        root = _location_root()
        if not root:
            raise HTTPException(400, "موقع الإنشاء غير متاح الآن.")
        try:
            allowed = Path(root).resolve(strict=True)
            requested = Path(str(data.get("path") or "")).resolve(strict=False)
            if requested != allowed and allowed not in requested.parents:
                raise HTTPException(403, "المسار خارج موقع الإنشاء.")
            folder = requested
            while not folder.is_dir() and folder != allowed:
                folder = folder.parent
            if not folder.is_dir():
                raise HTTPException(404, "مجلد الشجرة غير موجود.")
            if sys.platform != "win32":
                raise HTTPException(501, "فتح المجلد متاح في نسخة Windows فقط.")
            os.startfile(str(folder))
        except HTTPException:
            raise
        except OSError as exc:
            raise HTTPException(400, f"تعذّر فتح المسار: {exc}")
        return {"opened": str(folder)}

    @app.post("/api/tree/create")
    def tree_create(data: dict = Body(...)):
        plan = _build_plan(data, "لم يُحدد موقع الإنشاء بعد.")
        result = execute_tree(plan)
        icon_errors = []
        if bool(data.get("icons")):
            from .foldericon import apply_generated_icon
            for folder, kind, first, second in plan.icon_targets or []:
                error = apply_generated_icon(folder, kind, first, second)
                if error:
                    icon_errors.append({"path": str(folder), "msg": error})
        return {
            "created": len(result.created),
            "skipped": len(result.skipped),
            "errors": [{"path": str(p), "msg": m} for p, m in result.errors],
            "root": str(plan.root),
            "icons_applied": len((plan.icon_targets or [])) - len(icon_errors)
                              if bool(data.get("icons")) else 0,
            "icon_errors": icon_errors,
        }

    @app.post("/api/shutdown")
    def shutdown():
        if on_shutdown:
            on_shutdown()
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=str(web)), name="static")
    return app
