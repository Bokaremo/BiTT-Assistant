"""Student roster import and Arabic name normalisation."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

try:
    import openpyxl  # type: ignore
    _HAS_OPENPYXL = True
except ImportError:  # pragma: no cover
    _HAS_OPENPYXL = False

try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except ImportError:  # pragma: no cover
    _HAS_PDFPLUMBER = False


# ---------------------------------------------------------------------------
# Arabic name normalisation
# ---------------------------------------------------------------------------

_STRIP_DIACRITICS_RE = re.compile(r"[ً-ْٰ]")  # tashkil + superscript alef
_MULTI_SPACE_RE = re.compile(r"\s+")

# Connective particles to remove for matching (not for display)
_PARTICLES = re.compile(
    r"\b(بن|بنت|ابن|ابنة|بنو|آل|ال|عبد|عبدال|أبو|ابو|أبي|ابي)\b", re.UNICODE
)


def _remove_diacritics(text: str) -> str:
    return _STRIP_DIACRITICS_RE.sub("", text)


def _normalise_alef(text: str) -> str:
    """إ أ آ أ → ا"""
    return text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا").replace("ٱ", "ا")


def _normalise_teh_marbuta(text: str) -> str:
    """ة → ه at word boundaries (for matching only)."""
    return re.sub(r"ة(?=\s|$)", "ه", text)


def normalise(name: str) -> str:
    """Return a canonical form of an Arabic name for display.

    Strips extra whitespace and diacritics, normalises Alef variants.
    Does NOT remove particles — that is done in ``match_key`` only.
    """
    name = unicodedata.normalize("NFC", name or "")
    name = _remove_diacritics(name)
    name = _normalise_alef(name)
    name = _MULTI_SPACE_RE.sub(" ", name).strip()
    return name


def match_key(name: str) -> str:
    """Return a string used only for fuzzy matching (not stored or displayed).

    Removes particles (بن, ابن …) and Teh Marbuta so
    «تميم بن علي الشهراني» and «تميم علي الشهراني» match.
    """
    k = normalise(name).lower()
    k = _normalise_teh_marbuta(k)
    k = _PARTICLES.sub(" ", k)
    k = _MULTI_SPACE_RE.sub(" ", k).strip()
    return k


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Student(NamedTuple):
    name: str         # normalised display name
    key: str          # match_key(name) for dedup / fuzzy match
    row_index: int    # 0-based row in the original source (for error messages)
    suspect: bool = False  # True when the source glyphs look lossy — needs review


class ImportResult(NamedTuple):
    students: list[Student]
    warnings: list[str]   # non-fatal issues (duplicates, empty rows …)
    errors: list[str]     # fatal issues (file not found, unreadable …)
    grade: int | None = None    # detected from the roster header
    label: str | None = None    # detected section label, e.g. "11-1"


# ---------------------------------------------------------------------------
# XLSX import
# ---------------------------------------------------------------------------

def _is_arabic_name(cell_value: object) -> bool:
    s = str(cell_value or "").strip()
    return bool(s) and bool(re.search(r"[؀-ۿ]", s))


_HEADER_WORDS = {
    "الاسم", "اسم", "اسم الطالب", "اسم الطالبة", "م", "رقم", "الصف", "الشعبة",
    # MOE PDF header row (after RTL fix)
    "الهاتف النقال", "المنطقة السكنية", "حالة القيد", "الجنسية", "الرقم المدرسي",
    # MOE PDF header row (raw visual encoding — before fix)
    "لاقنلا فتاهلا", "ةينكسلا ةقطنملا", "ةيسنجلا", "يسردملا مقرلا",
}


def _is_header(cell_value: object) -> bool:
    return str(cell_value or "").strip() in _HEADER_WORDS


def _find_name_column(sheet) -> tuple[int, int] | tuple[None, None]:
    """Return (0-based column index, 0-based first data row) of the name column."""
    for ri, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(10, sheet.max_row), values_only=True)):
        for ci, cell in enumerate(row):
            if _is_arabic_name(cell) and len(str(cell).strip()) > 3:
                # If this looks like a header, skip to next row for data start
                if _is_header(cell):
                    continue
                return ci, ri
    return None, None


def import_xlsx(path: Path | str) -> ImportResult:
    """Read student names from an Excel workbook.

    Tries every sheet and every column to find Arabic names.
    Returns the sheet with the most valid names.
    """
    path = Path(path)
    if not path.exists():
        return ImportResult([], [], [f"الملف غير موجود: {path.name}"])
    if not _HAS_OPENPYXL:
        return ImportResult([], [], ["مكتبة openpyxl غير مثبتة. شغّل: pip install openpyxl"])

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        return ImportResult([], [], [f"تعذّر فتح الملف: {exc}"])

    best: list[Student] = []
    warnings: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        col, start_row = _find_name_column(ws)
        if col is None:
            continue
        students: list[Student] = []
        seen_keys: set[str] = set()
        sheet_warns: list[str] = []
        for ri, row in enumerate(ws.iter_rows(min_row=start_row + 1, values_only=True)):
            if col >= len(row):
                continue
            raw = str(row[col] or "").strip()
            if not _is_arabic_name(raw) or _is_header(raw):
                continue
            norm = normalise(raw)
            key = match_key(norm)
            if not key:
                sheet_warns.append(f"الصف {ri + 1}: اسم فارغ بعد التنظيف — تجاهل.")
                continue
            if key in seen_keys:
                sheet_warns.append(f"الصف {ri + 1}: «{norm}» مكرر — تجاهل.")
                continue
            seen_keys.add(key)
            students.append(Student(norm, key, ri))
        if len(students) > len(best):
            best = students
            warnings = sheet_warns

    if not best:
        return ImportResult([], warnings, ["لم يُعثر على أسماء طلبة في الملف. تأكد أن الأسماء مكتوبة بالعربية في عمود واحد."])
    return ImportResult(best, warnings, [])


# ---------------------------------------------------------------------------
# PDF import
# ---------------------------------------------------------------------------

def _extract_names_from_rows(rows: list[list[str]]) -> tuple[list[Student], list[str]]:
    """Shared name-extraction logic for rows coming from any tabular source (PDF/xlsx)."""
    students: list[Student] = []
    warnings: list[str] = []
    seen_keys: set[str] = set()
    row_idx = 0
    for row in rows:
        # Join multi-line cell fragments: each element in row is one cell
        for cell in row:
            raw = " ".join(str(cell or "").split())  # collapse internal whitespace
            if not _is_arabic_name(raw) or _is_header(raw) or len(raw) < 4:
                continue
            # Must be a full name (at least 2 words)
            norm = normalise(raw)
            if len(norm.split()) < 2:
                continue
            key = match_key(norm)
            if not key:
                continue
            if key in seen_keys:
                warnings.append(f"الصف {row_idx + 1}: «{norm}» مكرر — تجاهل.")
                continue
            seen_keys.add(key)
            students.append(Student(norm, key, row_idx))
            row_idx += 1
            break  # only one name per row
    return students, warnings


def _fix_pdf_rtl(text: str) -> str:
    """Fix visually-encoded RTL Arabic text extracted from PDF.

    pdfplumber reads Arabic text from Oman MOE PDFs with both character
    order within each word AND word order reversed (visual/LTR encoding).
    Multi-line names (cell wraps) are handled by processing each line
    separately then concatenating.
    Example (single line): 'يخيشملا دمحم نب نيسح نب دمحأ' → 'أحمد بن حسين بن محمد المشيخي'
    Example (two lines): 'نوديج ملاس سورحم نب دمحأ نب ملاس\nيرماعلا' → 'سالم بن أحمد بن محروس سالم جيدون العامري'
    """
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        words = line.split()
        parts.extend(w[::-1] for w in reversed(words))
    return " ".join(parts)


# Column index (0-based, from left) of the name in a standard Oman MOE roster table.
# Table columns (RTL layout stored LTR in PDF):
#   0: الهاتف النقال  1: المنطقة السكنية  2: حالة القيد  3: الجنسية
#   4: الرقم المدرسي  5: الاسم  6: م
_MOE_NAME_COL = 5


# ---------------------------------------------------------------------------
# Collapsed-ligature recovery
# ---------------------------------------------------------------------------
# MOE roster PDFs draw some Arabic ligatures as a single glyph whose ToUnicode
# entry maps to only ONE of the letters it renders. The other letters are lost
# before any extractor sees them — pdfplumber, pdfminer and pdftotext all agree.
# The surviving evidence is the glyph's advance width: a collapsed ligature is
# several times wider than the same character elsewhere in the name column.
#
# Measured on a real roster (G11, Arial Bold): «عبدالله» arrives as «عبدا»,
# with the final alef 7.46pt wide against a 2.05pt median for a plain alef.

_ROW_TOL = 2.0      # pt — vertical tolerance when grouping glyphs into one line
_CELL_GAP = 8.0     # pt — horizontal gap that separates two table cells
_WORD_GAP = 0.8     # pt — horizontal gap that separates two words
_SUSPECT_RATIO = 1.8   # above this, the glyph is reported as unreliable
_LIG_MIN_SAMPLES = 4   # need this many samples of a char before trusting its baseline

# (character the glyph maps to, minimum width ratio, letters it really renders)
# Ordered widest-first; the first match wins.
_LIGATURES: tuple[tuple[str, float, str], ...] = (
    ("ا", 3.0, "الله"),   # ﷲ  U+FDF2 — Allah ligature
    ("ل", 2.5, "لا"),     # ﻻ  U+FEFB — lam-alef
    ("ا", 2.5, "لا"),
)


def _baseline_width(widths: list[float]) -> float:
    """Widest *ordinary* advance for a character.

    Arabic letters have four contextual forms, so their widths vary by 2-3×
    naturally; a median would make every final form look like a ligature. The
    90th percentile tracks the widest normal form while a lone ligature, which
    is rarer still, stays above it.
    """
    ordered = sorted(widths)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))]


def _expand_ligature(text: str, width: float, baseline: float) -> tuple[str, bool]:
    """Return (logical text, is_suspect) for one extracted glyph.

    ``baseline`` is the widest ordinary advance of this character in this
    document. A glyph well past it renders letters the PDF never mapped to
    Unicode, so its width is the only evidence those letters existed.
    """
    if baseline <= 0 or not text.strip():
        return text, False
    ratio = width / baseline
    for ch, min_ratio, expansion in _LIGATURES:
        if text == ch and ratio >= min_ratio:
            return expansion, True
    return text, ratio >= _SUSPECT_RATIO


def _lines(chars: list[dict]) -> list[list[dict]]:
    """Group glyphs into visual lines, each sorted left→right."""
    out: list[list[dict]] = []
    for ch in sorted(chars, key=lambda c: (c["top"], c["x0"])):
        if out and abs(ch["top"] - out[-1][0]["top"]) <= _ROW_TOL:
            out[-1].append(ch)
        else:
            out.append([ch])
    return [sorted(line, key=lambda c: c["x0"]) for line in out]


def _cells(line: list[dict]) -> list[list[dict]]:
    """Split one visual line into table cells on horizontal gaps."""
    if not line:
        return []
    out: list[list[dict]] = [[line[0]]]
    for prev, cur in zip(line, line[1:]):
        if cur["x0"] - prev["x1"] > _CELL_GAP:
            out.append([cur])
        else:
            out[-1].append(cur)
    return out


def _row_text(row: list[list[dict]], baselines: dict[str, float]) -> tuple[str, bool]:
    """Convert one visually-encoded name row into logical Arabic text.

    Glyphs arrive in visual (LTR) order with word order reversed too, so both
    the characters within each word and the words themselves are un-reversed.
    A wrapped name arrives as several lines, each reversed on its own before the
    lines are joined in reading order. Collapsed ligatures are expanded AFTER
    the reversal, where the recovered letters land in their logical position.
    """
    suspect = False
    out: list[str] = []
    for line in row:
        words: list[list[dict]] = [[]]
        prev: dict | None = None
        for ch in line:
            gap = ch["x0"] - prev["x1"] if prev else 0.0
            prev = ch
            if ch["text"].isspace() or gap > _WORD_GAP:
                if words[-1]:
                    words.append([])
            if not ch["text"].isspace():
                words[-1].append(ch)
        for word in reversed(words):
            if not word:
                continue
            buf: list[str] = []
            for ch in reversed(word):          # un-reverse characters
                txt, flag = _expand_ligature(ch["text"], ch["width"], baselines.get(ch["text"], 0.0))
                suspect = suspect or flag
                buf.append(txt)
            out.append("".join(buf))
    return " ".join(out), suspect


def _name_column(page_lines: list[list[dict]]) -> tuple[float, float] | None:
    """Locate the name column by finding the «الاسم» header cell.

    The header is drawn with kashida padding («مــــــســلا»), so it is matched
    on its letters rather than on an exact string.
    """
    for line in page_lines:
        for cell in _cells(line):
            raw = "".join(c["text"] for c in cell)
            stripped = raw.replace("ـ", "").strip()
            if stripped in {"مسلا", "الاسم"}:
                return cell[0]["x0"], cell[-1]["x1"]
    return None


def _name_cells(page_lines: list[list[dict]], span: tuple[float, float]) -> list[list[dict]]:
    """Pick the name cell out of every data row.

    Name cells are wider than the «الاسم» header on both sides, so they are
    matched by horizontal overlap rather than containment. A row counts as data
    only when it carries a serial number to the right of the name column, which
    keeps header and title lines out. A row without one continues the name above
    it — MOE rosters wrap long names onto a second line.
    """
    left, right = span
    width = right - left

    # Pass 1 — full name rows, identified by their serial number. The header is
    # kashida-centred and narrower than the names, so cells are matched by
    # overlap with it rather than by containment.
    rows: list[tuple[int, list[dict]]] = []
    for i, line in enumerate(page_lines):
        parts: list[dict] = []
        has_serial = False
        for cell in _cells(line):
            x0, x1 = cell[0]["x0"], cell[-1]["x1"]
            if x0 >= right and "".join(c["text"] for c in cell).strip().isdigit():
                has_serial = True
                continue
            if min(x1, right) - max(x0, left) > 0 and x1 <= right + width and x0 >= left - width:
                parts.extend(cell)
        if not (has_serial and parts):
            continue
        parts.sort(key=lambda c: c["x0"])
        if parts[-1]["x1"] - parts[0]["x0"] >= width * 0.5:
            rows.append((i, parts))
    if not rows:
        return []

    # Pass 2 — wrapped names. A continuation fragment is right-aligned inside
    # the column and can fall clear of the header, so the column's true extent
    # is taken from the rows just matched. Each fragment stays its own line:
    # lines reverse individually, then join in reading order.
    col_left = min(p[0]["x0"] for _, p in rows)
    col_right = max(p[-1]["x1"] for _, p in rows)
    out: list[list[list[dict]]] = []
    at = {i: n for n, (i, _) in enumerate(rows)}
    for i, line in enumerate(page_lines):
        if i in at:
            out.append([rows[at[i]][1]])
            continue
        if not out:
            continue
        frag = [c for c in line if c["x0"] >= col_left - 1 and c["x1"] <= col_right + 1]
        if frag and any(c["text"].strip() for c in frag):
            out[-1].append(sorted(frag, key=lambda c: c["x0"]))
    return out


# Arabic ordinals as they appear in the «الصف:» header line.
_GRADE_WORDS: tuple[tuple[str, int], ...] = (
    ("الثاني عشر", 12), ("الحادي عشر", 11), ("العاشر", 10), ("التاسع", 9),
    ("الثامن", 8), ("السابع", 7), ("السادس", 6), ("الخامس", 5),
    ("الرابع", 4), ("الثالث", 3), ("الثاني", 2), ("الاول", 1), ("الأول", 1),
)


def _detect_grade_section(lines: list[list[dict]]) -> tuple[int | None, str | None]:
    """Read grade and section from the «الصف: الحادي عشر/تقنية المعلومات 1» header.

    Returns (grade, label) — e.g. (11, "11-1") — or (None, None) when absent.
    """
    for line in lines:
        text = _fix_pdf_rtl("".join(c["text"] for c in line))
        if "الصف" not in text:
            continue
        flat = normalise(text)
        for word, num in _GRADE_WORDS:
            if word in flat:
                tail = flat.split(word, 1)[1]
                digits = re.findall(r"\d+", tail)
                section = digits[0] if digits else "1"
                return num, f"{num}-{section}"
    return None, None


def _import_pdf_tables(pdf) -> tuple[list[Student], list[str]]:
    """Fallback extractor: pdfplumber's own table parser, no ligature recovery."""
    students: list[Student] = []
    warnings: list[str] = []
    seen_keys: set[str] = set()
    row_idx = 0
    for page in pdf.pages:
        for table in page.extract_tables() or []:
            for row in table:
                if not row:
                    continue
                candidates = []
                if len(row) > _MOE_NAME_COL:
                    candidates.append(str(row[_MOE_NAME_COL] or "").strip())
                for c in row:
                    cell = str(c or "").strip()
                    if cell and cell not in candidates:
                        candidates.append(cell)
                for raw in candidates:
                    fixed = _fix_pdf_rtl(raw)
                    if not _is_arabic_name(fixed) or _is_header(fixed) or _is_header(raw):
                        continue
                    norm = normalise(fixed)
                    if len(norm.split()) < 2:
                        continue
                    key = match_key(norm)
                    if not key:
                        continue
                    if key in seen_keys:
                        warnings.append(f"الصف {row_idx + 1}: «{norm}» مكرر — تجاهل.")
                        break
                    seen_keys.add(key)
                    students.append(Student(norm, key, row_idx))
                    row_idx += 1
                    break
    return students, warnings


def import_pdf(path: Path | str) -> ImportResult:
    """Read student names from an Oman MOE student-roster PDF.

    The roster table runs right→left:
    م | الاسم | الرقم المدرسي | الجنسية | حالة القيد | المنطقة السكنية | الهاتف النقال

    Text is stored visually (LTR) with every Arabic word reversed. Rather than
    using pdfplumber's table parser — which discards glyph geometry — this reads
    the raw glyph stream so collapsed ligatures can be recovered from their
    advance width, and falls back to the table parser if the layout is unknown.
    """
    path = Path(path)
    if not path.exists():
        return ImportResult([], [], [f"الملف غير موجود: {path.name}"])
    if not _HAS_PDFPLUMBER:
        return ImportResult([], [], ["مكتبة pdfplumber غير مثبتة. شغّل: pip install pdfplumber"])

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:  # noqa: BLE001
        return ImportResult([], [], [f"تعذّر فتح الملف: {exc}"])

    students: list[Student] = []
    warnings: list[str] = []
    seen_keys: set[str] = set()
    row_idx = 0
    grade: int | None = None
    label: str | None = None

    try:
        for page in pdf.pages:
            lines = _lines(page.chars)
            if grade is None:
                grade, label = _detect_grade_section(lines)

            span = _name_column(lines)
            if span is None:
                continue
            left, right = span

            # Glyph-width baseline, measured on the name column of this page only:
            # header text is kashida-stretched and would skew the baselines.
            rows = _name_cells(lines, (left, right))
            samples: dict[str, list[float]] = {}
            for row in rows:
                for line in row:
                    for ch in line:
                        if ch["text"].strip():
                            samples.setdefault(ch["text"], []).append(ch["width"])
            baselines = {
                ch: _baseline_width(ws)
                for ch, ws in samples.items()
                if len(ws) >= _LIG_MIN_SAMPLES
            }

            for row in rows:
                text, suspect = _row_text(row, baselines)
                if not _is_arabic_name(text) or _is_header(text):
                    continue
                norm = normalise(text)
                if len(norm.split()) < 2:
                    continue
                key = match_key(norm)
                if not key:
                    continue
                if key in seen_keys:
                    warnings.append(f"الصف {row_idx + 1}: «{norm}» مكرر — تجاهل.")
                    continue
                seen_keys.add(key)
                students.append(Student(norm, key, row_idx, suspect))
                row_idx += 1

        if not students:
            students, warnings = _import_pdf_tables(pdf)
    finally:
        pdf.close()

    if not students:
        return ImportResult([], warnings, ["لم يُعثر على أسماء طلبة في الـ PDF. تأكد أن الأسماء مكتوبة بالعربية."])

    n_suspect = sum(1 for s in students if s.suspect)
    if n_suspect:
        warnings.append(
            f"{n_suspect} اسمًا قد يكون ناقصًا بسبب خلل في ترميز الـ PDF — راجعها وصحّحها يدويًا."
        )
    return ImportResult(students, warnings, [], grade, label)


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def import_roster(path: Path | str) -> ImportResult:
    """Auto-detect xlsx/xls/pdf and call the appropriate importer."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        return import_xlsx(p)
    if ext == ".pdf":
        return import_pdf(p)
    return ImportResult([], [], [f"صيغة الملف «{ext}» غير مدعومة. استخدم xlsx أو pdf."])


# ---------------------------------------------------------------------------
# Review / merge helper
# ---------------------------------------------------------------------------

def find_suspicious_pairs(students: list[Student], threshold: int = 2) -> list[tuple[int, int]]:
    """Return pairs of indices whose match_keys differ by ≤ threshold characters.

    Uses simple character-set difference (not full edit distance) for speed.
    """
    pairs: list[tuple[int, int]] = []
    keys = [s.key for s in students]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = set(keys[i].split()), set(keys[j].split())
            diff = len(a.symmetric_difference(b))
            if diff <= threshold:
                pairs.append((i, j))
    return pairs
