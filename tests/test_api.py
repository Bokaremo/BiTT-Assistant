import copy

import pytest
from fastapi.testclient import TestClient

from biit import config, naming
from biit.drives import mark_recommended
from biit.server import create_app

GB = 1024 ** 3
TOKEN = "test-token"
H = {"x-biit-token": TOKEN}

BASE_DRIVES = [
    {"letter": "C", "root": "C:\\", "label": "Windows", "serial": "AAAA0001", "kind": "fixed",
     "system": True, "total": 200 * GB, "free": 50 * GB, "writable": True},
    {"letter": "D", "root": "D:\\", "label": "Data", "serial": "BBBB0002", "kind": "fixed",
     "system": False, "total": 300 * GB, "free": 250 * GB, "writable": True},
    {"letter": "E", "root": "E:\\", "label": "USB", "serial": "CCCC0003", "kind": "removable",
     "system": False, "total": 30 * GB, "free": 29 * GB, "writable": True},
    {"letter": "F", "root": "F:\\", "label": "Locked", "serial": "DDDD0004", "kind": "fixed",
     "system": False, "total": 100 * GB, "free": 90 * GB, "writable": False},
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIIT_DATA_DIR", str(tmp_path))
    box = {"drives": copy.deepcopy(BASE_DRIVES), "stopped": False}
    app = create_app(
        TOKEN, {"mode": "window"},
        drive_provider=lambda: mark_recommended(copy.deepcopy(box["drives"])),
        on_shutdown=lambda: box.__setitem__("stopped", True),
    )
    return TestClient(app), box


def test_naming():
    assert naming.term_folder(11, 1, "2026-2027", "en") == "G11_S1_2026-2027"
    assert naming.term_folder(11, 1, "2026-2027", "ar") == "حادي عشر_ف1_2026-2027"
    assert naming.term_folder(12, 2, "2026-2027", "ar") == "ثاني عشر_ف2_2026-2027"
    for bad in ("2026-2028", "2026", "26-27", ""):
        with pytest.raises(ValueError):
            naming.term_folder(11, 1, bad, "en")
    with pytest.raises(ValueError):
        naming.term_folder(13, 1, "2026-2027", "en")


def test_api_requires_token_and_local_host(env):
    client, _ = env
    assert client.get("/api/state").status_code == 403
    assert client.get("/api/state", headers={"x-biit-token": "wrong"}).status_code == 403
    assert client.get("/api/state", headers={**H, "host": "evil.example"}).status_code == 403
    assert client.get("/api/state", headers=H).status_code == 200


def test_index_injects_token(env):
    client, _ = env
    r = client.get("/")
    assert r.status_code == 200 and TOKEN in r.text and "{{TOKEN}}" not in r.text


def test_default_state(env):
    client, _ = env
    s = client.get("/api/state", headers=H).json()
    assert s["location"] == {"status": "unset"}
    assert s["settings"]["device_count"] == 20
    assert naming.valid_year(s["settings"]["academic_year"])


def test_settings_roundtrip_and_validation(env):
    client, _ = env
    good = {"school_name": "  مدرسة   صلالة ", "teacher_name": "محمود", "academic_year": "2026/2027",
            "semester": 2, "naming_lang": "ar", "device_count": 32}
    r = client.put("/api/settings", headers=H, json=good)
    assert r.status_code == 200
    saved = client.get("/api/state", headers=H).json()["settings"]
    assert saved["school_name"] == "مدرسة صلالة"
    assert saved["academic_year"] == "2026-2027"
    assert saved["device_count"] == 32 and saved["semester"] == 2

    bad = {**good, "device_count": 41, "academic_year": "2026-2030", "semester": 3}
    r = client.put("/api/settings", headers=H, json=bad)
    assert r.status_code == 422
    assert set(r.json()["fields"]) == {"device_count", "academic_year", "semester"}
    # a rejected save must not change stored settings
    assert client.get("/api/state", headers=H).json()["settings"]["device_count"] == 32


def test_corrupt_settings_file_recovers(env, tmp_path):
    client, _ = env
    (config.user_dir() / "settings.json").write_text("{not json", encoding="utf-8")
    assert client.get("/api/state", headers=H).json()["settings"]["semester"] == 1


def test_drives_and_recommendation(env):
    client, _ = env
    drives = client.get("/api/drives", headers=H).json()["drives"]
    rec = [d["letter"] for d in drives if d["recommended"]]
    assert rec == ["D"]  # fixed, non-system, most free; never removable / read-only


def test_recommend_system_drive_when_alone():
    only_c = mark_recommended([copy.deepcopy(BASE_DRIVES[0])])
    assert only_c[0]["recommended"] is True


def test_save_location_and_rejections(env):
    client, _ = env
    assert client.put("/api/location", headers=H, json={"letter": "Z"}).status_code == 400
    assert client.put("/api/location", headers=H, json={"letter": "F"}).status_code == 400
    r = client.put("/api/location", headers=H, json={"letter": "d"})
    assert r.status_code == 200 and r.json()["location"]["status"] == "ok"
    loc = client.get("/api/state", headers=H).json()["location"]
    assert loc["letter"] == "D" and loc["root"] == "D:\\"


def test_location_follows_volume_when_letter_changes(env):
    client, box = env
    client.put("/api/location", headers=H, json={"letter": "D"})
    for d in box["drives"]:
        if d["letter"] == "D":
            d["letter"], d["root"] = "G", "G:\\"
    loc = client.get("/api/state", headers=H).json()["location"]
    assert loc["status"] == "moved" and loc["letter"] == "G" and loc["previous_letter"] == "D"
    # the new letter is remembered, so the notice shows once
    assert client.get("/api/state", headers=H).json()["location"]["status"] == "ok"


def test_location_missing_does_not_reuse_letter_of_other_volume(env):
    client, box = env
    client.put("/api/location", headers=H, json={"letter": "E"})
    for d in box["drives"]:
        if d["letter"] == "E":
            d["serial"] = "FFFF9999"  # a different USB stick now sits on E:
    loc = client.get("/api/state", headers=H).json()["location"]
    assert loc["status"] == "missing"


def test_location_readonly(env):
    client, box = env
    client.put("/api/location", headers=H, json={"letter": "D"})
    next(d for d in box["drives"] if d["letter"] == "D")["writable"] = False
    assert client.get("/api/state", headers=H).json()["location"]["status"] == "readonly"


def test_naming_preview_endpoint(env):
    client, _ = env
    r = client.get("/api/naming", headers=H,
                   params={"academic_year": "2026-2027", "semester": 1, "naming_lang": "en"})
    assert r.json()["grades"]["12"] == "G12_S1_2026-2027"
    r = client.get("/api/naming", headers=H,
                   params={"academic_year": "2026", "semester": 1, "naming_lang": "en"})
    assert r.status_code == 400


def test_shutdown(env):
    client, box = env
    assert client.post("/api/shutdown", headers=H).status_code == 200
    assert box["stopped"] is True


# ---------------------------------------------------------------------------
# Collapsed-ligature recovery
# ---------------------------------------------------------------------------

def test_baseline_width_ignores_a_lone_wide_glyph():
    """A single ligature must not drag the baseline up to its own size."""
    from biit.roster import _baseline_width
    plain = [2.0] * 20
    assert _baseline_width(plain) == pytest.approx(2.0)
    assert _baseline_width(plain + [7.5]) < 3.0


def test_allah_ligature_is_expanded():
    from biit.roster import _expand_ligature
    assert _expand_ligature("ا", 7.46, 2.05) == ("الله", True)


def test_lam_alef_ligature_is_expanded():
    from biit.roster import _expand_ligature
    assert _expand_ligature("ل", 6.2, 2.4) == ("لا", True)


def test_ordinary_glyph_is_left_alone():
    from biit.roster import _expand_ligature
    assert _expand_ligature("ت", 5.7, 5.7) == ("ت", False)
    assert _expand_ligature("م", 3.6, 3.5) == ("م", False)


def test_wide_glyph_without_a_known_expansion_is_only_flagged():
    from biit.roster import _expand_ligature
    assert _expand_ligature("ب", 9.0, 2.4) == ("ب", True)


def test_detect_grade_section_reads_the_header():
    from biit.roster import _detect_grade_section

    def line(text):                       # visual encoding, as a PDF stores it
        return [{"text": ch, "x0": i, "x1": i + 1, "top": 0.0, "width": 1.0}
                for i, ch in enumerate(" ".join(w[::-1] for w in reversed(text.split())))]

    assert _detect_grade_section([line("الصف: الحادي عشر/تقنية المعلومات 1")]) == (11, "11-1")
    assert _detect_grade_section([line("الصف: الثاني عشر/تقنية المعلومات 3")]) == (12, "12-3")
    assert _detect_grade_section([line("لا ترويسة هنا")]) == (None, None)


# ---------------------------------------------------------------------------
# Device assignment
# ---------------------------------------------------------------------------

def _students(n):
    from biit.roster import Student
    return [Student(f"طالب رقم {i}", f"k{i}", i) for i in range(n)]


def test_disabled_device_keeps_its_number_and_stays_empty():
    from biit.sections import assign_devices
    slots = assign_devices(_students(4), 5, disabled=[2])
    assert [(s.device_no, s.primary) for s in slots] == [(1, 0), (2, -1), (3, 1), (4, 2), (5, 3)]


def test_pinned_student_holds_its_device_and_others_flow_around():
    from biit.sections import assign_devices
    slots = assign_devices(_students(3), 4, pinned={4: 0})
    assert {s.device_no: s.primary for s in slots} == {1: 1, 2: 2, 3: -1, 4: 0}


def test_a_pin_on_a_dead_device_is_ignored():
    from biit.sections import assign_devices
    slots = assign_devices(_students(2), 3, disabled=[3], pinned={3: 0})
    assert [s.primary for s in slots] == [0, 1, -1]


def test_students_double_up_only_once_every_device_is_taken():
    from biit.sections import assign_devices
    slots = assign_devices(_students(5), 3)
    assert [(s.primary, s.secondary) for s in slots] == [(0, 3), (1, 4), (2, -1)]


def test_manual_project_groups_sort_members_and_require_complete_roster():
    from biit.projectforms import preview
    section = {"grade": 12, "label": "12-1", "students": [
        {"name": "زيد بن سالم"}, {"name": "أحمد بن علي"},
        {"name": "بلال بن محمد"},
    ]}
    groups = preview(section, 5, [[0, 1], [2]])
    assert groups == [
        {"group": 1, "students": ["أحمد بن علي", "زيد بن سالم"]},
        {"group": 2, "students": ["بلال بن محمد"]},
    ]
    with pytest.raises(ValueError, match="أكثر من مجموعة"):
        preview(section, 5, [[0, 1], [0, 2]])
    with pytest.raises(ValueError, match="جميع طلبة الشعبة"):
        preview(section, 5, [[0, 1]])


def test_manual_project_workbooks_use_selected_members(tmp_path):
    from openpyxl import load_workbook
    from biit.projectforms import generate
    section = {"grade": 12, "label": "12-1", "students": [
        {"name": "زيد بن سالم"}, {"name": "أحمد بن علي"},
        {"name": "بلال بن محمد"},
    ]}
    result = generate(section, 1, "2026-2027", str(tmp_path), manual_groups=[[0, 1], [2]])
    assert result["group_count"] == 2
    workbook = load_workbook(result["created"][0]["path"], data_only=False)
    assert workbook["المشروع الأول"]["B6"].value == "أحمد بن علي"
    assert workbook["المشروع الأول"]["B7"].value == "زيد بن سالم"
    assert workbook["المشروع الأول"]["B8"].value is None


def test_student_folder_transfer_updates_tree_and_device_assignment(env, tmp_path):
    from biit.naming import section_folder, tree_root_folder
    from biit.roster import Student
    from biit.sections import load_sections, section_slots, upsert_section
    from biit.transfers import move_students

    client, _ = env
    names = ["أحمد بن علي", "بلال بن محمد", "زيد بن سالم", "سعيد بن حمد", "ناصر بن خالد"]
    upsert_section(12, "12-1", [Student(name, f"k{i}", i) for i, name in enumerate(names)])
    settings = {"semester": 1, "academic_year": "2026-2027", "naming_lang": "en", "device_count": 4}
    root = tmp_path / "drive"
    matrix = root / tree_root_folder(1, "2026-2027", "en")
    section_name = section_folder(12, "12-1", 1, "2026-2027", "en", include_label=False)
    for i, name in enumerate(names):
        device = 1 if i in (0, 4) else i + 1
        (matrix / f"جهاز {device:02d}" / section_name / name).mkdir(parents=True)

    result = move_students(root, load_sections(), settings, 12, "12-1", [0], 4)
    assert result["moved"] == [{"name": names[0], "from": 1, "to": 4}]
    assert not (matrix / "جهاز 01" / section_name / names[0]).exists()
    assert (matrix / "جهاز 04" / section_name / names[0]).is_dir()
    section = load_sections()[0]
    slots = section_slots(section, 4)
    assert names[0] in [st["name"] for st in (slots[3]["primary"], slots[3]["secondary"]) if st]
    from biit.deploy import device_tree
    tree = device_tree(section, {**settings, "grade_section_count": 1})
    assert any(path.endswith(f"/{names[0]}") for path in tree[4])


def test_student_folder_transfer_rejects_overfull_target(env, tmp_path):
    from biit.naming import section_folder, tree_root_folder
    from biit.roster import Student
    from biit.sections import load_sections, upsert_section
    from biit.transfers import move_students

    env
    names = ["أحمد بن علي", "بلال بن محمد", "زيد بن سالم", "سعيد بن حمد", "ناصر بن خالد"]
    upsert_section(12, "12-1", [Student(name, f"k{i}", i) for i, name in enumerate(names)])
    settings = {"semester": 1, "academic_year": "2026-2027", "naming_lang": "en", "device_count": 4}
    root = tmp_path / "drive"
    matrix = root / tree_root_folder(1, "2026-2027", "en")
    section_name = section_folder(12, "12-1", 1, "2026-2027", "en", include_label=False)
    for i, name in enumerate(names):
        device = 1 if i in (0, 4) else i + 1
        (matrix / f"جهاز {device:02d}" / section_name / name).mkdir(parents=True)
    with pytest.raises(ValueError, match="يزيد العدد على طالبين"):
        move_students(root, load_sections(), settings, 12, "12-1", [0, 4], 4)
    assert (matrix / "جهاز 01" / section_name / names[0]).is_dir()


def test_unseated_counts_students_no_working_device_can_hold():
    from biit.sections import unseated_count
    section = {"students": [{"name": f"ط {i}", "key": f"k{i}"} for i in range(9)],
               "devices": {"disabled": [1, 2], "pinned": {}}}
    assert unseated_count(section, 4) == 5     # 2 machines left, 4 seats
    assert unseated_count({"students": [], "devices": {}}, 4) == 0


# ---------------------------------------------------------------------------
# Correcting a name
# ---------------------------------------------------------------------------

def test_rename_student_rewrites_the_pin_that_points_at_it(env, tmp_path, monkeypatch):
    from biit import sections as sec
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(3))
    assert sec.save_device_layout(11, "11-1", [], {"2": "k0"}) is None

    assert sec.rename_student(11, "11-1", 0, "عبدالله بن بدر المشيخي") is None
    section = sec.find_section(11, "11-1")
    new_key = section["students"][0]["key"]
    assert section["students"][0]["name"] == "عبدالله بن بدر المشيخي"
    assert section["devices"]["pinned"] == {"2": new_key}


def test_rename_student_rejects_a_one_word_name(env, tmp_path, monkeypatch):
    from biit import sections as sec
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(2))
    assert sec.rename_student(11, "11-1", 0, "أحمد") is not None
    assert sec.rename_student(11, "11-1", 9, "أحمد بن علي") is not None


def test_a_student_cannot_be_pinned_to_two_devices(env, tmp_path, monkeypatch):
    from biit import sections as sec
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(3))
    assert sec.save_device_layout(11, "11-1", [], {"1": "k0", "2": "k0"}) is not None


def test_load_sections_survives_concurrent_reads(env, tmp_path, monkeypatch):
    """Eight screens asking at once must never read as 'no sections'."""
    import concurrent.futures as cf
    from biit import sections as sec

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(3))
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: sec.find_section(11, "11-1"), range(64)))
    assert all(r is not None for r in results)


def test_load_sections_keeps_the_last_good_copy_when_a_read_fails(env, tmp_path, monkeypatch):
    from biit import sections as sec

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(2))
    assert sec.load_sections()                      # warms the cache
    monkeypatch.setattr(sec, "_read_sections", lambda *a, **k: None)
    (tmp_path / "sections.json").write_text("x", encoding="utf-8")   # change the stamp
    assert len(sec.load_sections()) == 1            # not silently emptied


def test_callers_cannot_mutate_the_cached_sections(env, tmp_path, monkeypatch):
    from biit import sections as sec

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(2))
    sec.load_sections()[0]["students"].clear()
    assert len(sec.load_sections()[0]["students"]) == 2


def test_all_device_plans_come_back_in_one_call(env, tmp_path, monkeypatch):
    from biit import sections as sec

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    client, _ = env
    sec.upsert_section(11, "11-1", _students(3))
    sec.upsert_section(12, "12-2", _students(5))
    body = client.get("/api/devices", headers=H).json()
    assert [s["label"] for s in body["sections"]] == ["11-1", "12-2"]
    assert all(len(s["slots"]) == body["device_count"] for s in body["sections"])


def test_write_probe_is_not_shared_between_threads(tmp_path, monkeypatch):
    """Concurrent callers must not delete each other's probe.

    A shared probe name made _ensure report a perfectly good directory as
    unwritable, and the app then stored its data in the temp folder instead.
    """
    import concurrent.futures as cf
    from biit import config as cfg

    monkeypatch.setenv("BIIT_DATA_DIR", str(tmp_path))
    cfg._dir_cache.clear()
    target = tmp_path / "probe-me"
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: cfg._ensure(target), range(64)))
    assert all(r == target for r in results)


def test_user_dir_is_stable_under_load(tmp_path, monkeypatch):
    import concurrent.futures as cf
    from biit import config as cfg

    monkeypatch.setenv("BIIT_DATA_DIR", str(tmp_path))
    cfg._dir_cache.clear()
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        dirs = set(pool.map(lambda _: cfg.user_dir(), range(64)))
    assert dirs == {tmp_path / "user"}


def test_tree_plan_accepts_the_grade_as_the_browser_sends_it(env, tmp_path, monkeypatch):
    """The browser sends grade as text; the sections file stores it as a number.

    Comparing the two without coercion made every section look missing, so the
    preview button answered 404 and no create button ever appeared.
    """
    from biit import sections as sec
    from biit import server as srv

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    monkeypatch.setattr(srv, "find_section", sec.find_section)
    sec.upsert_section(12, "12-2", _students(4))

    client, _ = env
    root = tmp_path / "drive"
    root.mkdir()
    monkeypatch.setattr(srv.config, "load_location",
                        lambda: {"letter": "Z:", "serial": "S1"})
    monkeypatch.setattr(srv.config, "resolve_location",
                        lambda *a, **k: {"status": "ok", "root": str(root)})

    as_text = client.post("/api/tree/plan", headers=H, json={"grade": "12", "label": "12-2"})
    as_number = client.post("/api/tree/plan", headers=H, json={"grade": 12, "label": "12-2"})
    assert as_text.status_code == 200
    assert as_text.json()["new_count"] == as_number.json()["new_count"] > 0
    assert as_text.json()["total_students"] == 4

    assert client.post("/api/tree/plan", headers=H,
                       json={"grade": "x", "label": "12-2"}).status_code == 422
    assert client.post("/api/tree/plan", headers=H,
                       json={"grade": "99", "label": "99-1"}).status_code == 404


def test_tree_plan_follows_the_saved_device_layout(env, tmp_path, monkeypatch):
    """Grade 1-11 folders are named per machine, so they must match the layout:
    the pinned student's own machine, and no folder for one out of service."""
    from biit import sections as sec
    from biit import server as srv

    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    monkeypatch.setattr(srv, "find_section", sec.find_section)
    sec.upsert_section(11, "11-1", _students(3))
    sec.save_device_layout(11, "11-1", [1], {"5": "k0"})

    client, _ = env
    root = tmp_path / "drive"
    root.mkdir()
    monkeypatch.setattr(srv.config, "load_location", lambda: {"letter": "Z:", "serial": "S1"})
    monkeypatch.setattr(srv.config, "resolve_location",
                        lambda *a, **k: {"status": "ok", "root": str(root)})

    # new_dirs are OS paths: backslashes on Windows, slashes elsewhere.
    names = [d.replace("\\", "/").rsplit("/", 1)[-1] for d in
             client.post("/api/tree/plan", headers=H,
                         json={"grade": "11", "label": "11-1"}).json()["new_dirs"]]
    assert not any(n.startswith("جهاز 01") for n in names)      # out of service
    assert any(n.startswith("جهاز 05") and "طالب رقم 0" in n for n in names)


# ---------------------------------------------------------------------------
# Deploy & collect
# ---------------------------------------------------------------------------

def _deploy_env(tmp_path, monkeypatch):
    from biit import sections as sec
    from biit import deploy as dep
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    monkeypatch.setattr(dep, "_deploy_settings_path", lambda: tmp_path / "deploy.json")
    return sec, dep


def test_package_ships_each_device_only_its_own_folders(env, tmp_path, monkeypatch):
    from biit import config as cfg
    sec, dep = _deploy_env(tmp_path, monkeypatch)
    sec.upsert_section(11, "11-1", _students(3))
    sec.save_device_layout(11, "11-1", [2], {})     # device 2 is out of service

    ds = dep.save_deploy_settings({"drop_root": str(tmp_path / "drop"),
                                   "share_unc": r"\\LRC-1\biitdrop"})
    info = dep.build_package(sec.find_section(11, "11-1"), "network",
                             cfg.load_settings(), ds)
    assert info.devices == [1, 3, 4]                 # 2 skipped, 3 students seated
    d1 = list((info.root / "devices" / "01").rglob("*"))
    assert d1 and all(p.is_dir() or "\u062c\u0647\u0627\u0632 01" in str(p) for p in d1)
    assert not (info.root / "devices" / "02").exists()
    for script in ("deploy.bat", "deploy.ps1", "collect.bat", "collect.ps1"):
        (info.root / script).read_text(encoding="ascii")   # cmd-safe: ASCII only
    assert "11-1" in info.veyon_command and info.veyon_command.startswith("powershell")


def test_usb_package_collects_back_onto_the_drive_itself(env, tmp_path, monkeypatch):
    import json as _json
    from biit import config as cfg
    sec, dep = _deploy_env(tmp_path, monkeypatch)
    sec.upsert_section(11, "11-1", _students(2))
    ds = dep.save_deploy_settings({"drop_root": str(tmp_path / "drop")})
    usb = tmp_path / "usb"
    info = dep.build_package(sec.find_section(11, "11-1"), "usb",
                             cfg.load_settings(), ds, usb_root=str(usb))
    assert str(info.root).startswith(str(usb))
    c = _json.loads((info.root / "config.json").read_text(encoding="utf-8"))
    assert c["collect_relative"] is True and c["collect_dest"] == "..\\..\\collect"


def test_inbox_names_the_devices_that_did_not_hand_in(env, tmp_path, monkeypatch):
    from biit import config as cfg
    sec, dep = _deploy_env(tmp_path, monkeypatch)
    sec.upsert_section(11, "11-1", _students(3))
    ds = dep.save_deploy_settings({"drop_root": str(tmp_path / "drop")})
    got = tmp_path / "drop" / "collect" / "11-1" / "2026-11-16" / "02" / "work.docx"
    got.parent.mkdir(parents=True)
    got.write_bytes(b"x" * 100)

    batches = dep.scan_inbox(ds, sec.load_sections(), cfg.load_settings())
    assert len(batches) == 1
    assert [d["device_no"] for d in batches[0]["devices"]] == [2]
    assert batches[0]["missing"] == [1, 3]


def test_usb_import_merges_without_overwriting(env, tmp_path, monkeypatch):
    _, dep = _deploy_env(tmp_path, monkeypatch)
    ds = dep.save_deploy_settings({"drop_root": str(tmp_path / "drop")})
    f = tmp_path / "usb" / "BiTT" / "collect" / "11-1" / "2026-11-16" / "01" / "a.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"new")
    kept = tmp_path / "drop" / "collect" / "11-1" / "2026-11-16" / "01" / "a.pdf"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"original")

    result = dep.import_usb_collect(str(tmp_path / "usb"), ds)
    assert result == {"copied": 0, "skipped": 1}
    assert kept.read_bytes() == b"original"           # never overwritten


# ---------------------------------------------------------------------------
# Reports, archive, reset
# ---------------------------------------------------------------------------

def test_distribution_guide_mirrors_the_seating(env, tmp_path, monkeypatch):
    from biit import config as cfg, reports as rep, sections as sec
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(3))
    sec.save_device_layout(11, "11-1", [1], {"4": "k2"})
    guide = rep.distribution_guide(sec.load_sections(), cfg.load_settings())
    rows = {r["name"]: r["device_no"] for r in guide[0]["rows"]}
    assert rows["طالب رقم 2"] == 4          # pinned
    assert 1 not in rows.values()            # out of service


def test_student_search_returns_the_folder_path(env, tmp_path, monkeypatch):
    from biit import config as cfg, reports as rep, sections as sec
    monkeypatch.setattr(sec, "_sections_path", lambda: tmp_path / "sections.json")
    sec.upsert_section(11, "11-1", _students(2))
    hits = rep.find_students("رقم 1", sec.load_sections(), cfg.load_settings(),
                             "D:/drive", [])
    assert len(hits) == 1 and hits[0]["device_no"] == 2
    assert hits[0]["path"].endswith("جهاز 02\\G11_S1_2026-2027\\طالب رقم 1")


def test_archive_moves_1_to_11_and_keeps_grade_12(tmp_path):
    from biit import maintenance as mnt
    root = tmp_path / "drive"
    for name in ("خامس_ف1_2026-2027", "ثاني عشر_ف1_2026-2027",
                 "G7_S1_2026-2027", "مجلد عادي"):
        (root / name).mkdir(parents=True)
    result = mnt.archive_execute(str(root))
    assert sorted(result["moved"]) == ["G7_S1_2026-2027", "خامس_ف1_2026-2027"]
    assert result["kept"] == ["ثاني عشر_ف1_2026-2027"]
    assert (root / "ثاني عشر_ف1_2026-2027").exists()
    assert (root / "مجلد عادي").exists()
    assert not (root / "خامس_ف1_2026-2027").exists()


def test_reset_requires_the_exact_word(env):
    import pytest as _pytest
    from biit import maintenance as mnt
    with _pytest.raises(ValueError):
        mnt.factory_reset("نعم")
    with _pytest.raises(ValueError):
        mnt.factory_reset("")


def test_folder_icon_lands_inside_the_folder_and_survives_a_move(env, tmp_path):
    """The .ico travels with the folder, so archiving keeps the icon."""
    from pathlib import Path
    from biit.foldericon import ICON_FILE, apply_icon, list_icons

    web = Path(__file__).resolve().parent.parent / "biit" / "web"
    icons = list_icons(web)
    assert len(icons) >= 8 and all(i["preview"].startswith("/static/") for i in icons)

    folder = tmp_path / "حادي عشر_ف1_2026-2027"
    folder.mkdir()
    assert apply_icon(folder, icons[0]["id"], web) is None
    ini = (folder / "desktop.ini").read_text(encoding="utf-8")
    assert f"IconResource={ICON_FILE},0" in ini          # relative — move-safe
    assert (folder / ICON_FILE).stat().st_size > 0
    assert apply_icon(folder, "no-such-icon", web) is not None
