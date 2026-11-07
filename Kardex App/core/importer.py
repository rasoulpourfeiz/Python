"""ورود داده از اکسل/CSV: کدینگ کالا و تراکنش‌ها (خرید، فروش، اول دوره).
هدرها خودکار تشخیص داده می‌شوند (فارسی و انگلیسی)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .engine import BUY, OPENING, SELL, Txn
from .textutil import clean_display, norm_code, norm_date, norm_text, parse_number

# شیت‌هایی که از روی خرید/فروش ساخته شده‌اند و نباید دوباره وارد شوند
DERIVED_SHEETS = {"ادغام", "کاردکس", "کاردکس زنده", "خلاصه موجودی و نرخ", "کنترل", "پیش_بینی_فروش"}
PREFERRED_SHEETS = {"کدینگ کالا", "خرید", "فروش"}

_HEADERS = {
    "date": ["تاریخ", "date"],
    "type": ["نوع", "type", "نوع سند"],
    "party": ["طرف حساب", "طرف حساب خرید", "خریدار", "فروشنده", "party", "buyer", "supplier"],
    "code": ["کد کالا", "کد", "code", "item code", "کد کالا/خدمت"],
    "name": ["نام کالا", "نام کامل کالا", "شرح کالا", "نام", "کالا", "name", "item", "item name"],
    "qty": ["مقدار", "تعداد", "qty", "quantity"],
    "fee": ["فی", "قیمت واحد", "نرخ", "قیمت", "price", "fee", "unit price"],
    "vat": ["نرخ ارزش افزوده", "نرخ ارزش‌افزوده", "ارزش افزوده", "نرخ مالیات", "درصد مالیات",
            "درصد ارزش افزوده", "vat", "vat rate", "tax rate"],
}
_TYPE_MAP = {
    "اول دوره": OPENING, "اولدوره": OPENING, "opening": OPENING, "موجودی اول دوره": OPENING,
    "خرید": BUY, "buy": BUY, "purchase": BUY, "ورود": BUY,
    "فروش": SELL, "sell": SELL, "sale": SELL, "sales": SELL, "خروج": SELL,
}


@dataclass
class SheetInfo:
    name: str
    kind: str                       # items | txns
    header_row: int
    columns: dict[str, int]
    rows: list[list]
    default_checked: bool = False


@dataclass
class ImportReport:
    items_added: int = 0
    items_updated: int = 0
    vat_items: int = 0          # تعداد کالاهایی که نرخ ارزش افزوده‌شان از فایل خوانده شد
    txns_added: int = 0
    unresolved: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)


def _detect(rows: list[list]) -> tuple[int, dict[str, int]] | None:
    best = None
    for ri, row in enumerate(rows[:15]):
        cols: dict[str, int] = {}
        for ci, v in enumerate(row):
            t = norm_text(v)
            if not t:
                continue
            for key, syns in _HEADERS.items():
                if key in cols:
                    continue
                if t in [norm_text(x) for x in syns] or (key == "party" and t.startswith("طرف حساب")):
                    cols[key] = ci
        score = len(cols)
        if score >= 2 and (best is None or score > best[0]):
            best = (score, ri, cols)
    return (best[1], best[2]) if best else None


def _kind(cols: dict[str, int]) -> str | None:
    if "qty" in cols and "fee" in cols and ("code" in cols or "name" in cols):
        return "txns"
    if "code" in cols and "name" in cols and "qty" not in cols:
        return "items"
    return None


def read_sheets(path: str | Path) -> list[SheetInfo]:
    path = Path(path)
    raw: dict[str, list[list]] = {}
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            raw[path.stem] = [list(r) for r in csv.reader(f)]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            raw[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    out = []
    for name, rows in raw.items():
        det = _detect(rows)
        if not det:
            continue
        hr, cols = det
        kind = _kind(cols)
        if not kind and "type" not in cols and name.strip() in ("خرید", "فروش") and "qty" in cols:
            kind = "txns"
        if not kind:
            continue
        info = SheetInfo(name=name, kind=kind, header_row=hr, columns=cols, rows=rows[hr + 1:])
        out.append(info)
    out = [s for s in out if s.name.strip() not in DERIVED_SHEETS]
    names = {s.name.strip() for s in out}
    has_pref = bool(names & PREFERRED_SHEETS)
    for s in out:
        n = s.name.strip()
        if has_pref:
            s.default_checked = n in PREFERRED_SHEETS
        else:
            s.default_checked = n not in DERIVED_SHEETS
    return out


def _cell(row: list, cols: dict[str, int], key: str):
    i = cols.get(key)
    return row[i] if i is not None and i < len(row) else None


def _parse_vat(v) -> float | None:
    """۱۰ یا «10%» یا ۰٫۱ → 0.10؛ خالی/نامعتبر → None (یعنی نرخ پیش‌فرض شرکت)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    x = parse_number(str(v).replace("%", "").replace("٪", ""))
    if x is None or x < 0:
        return None
    x = x / 100 if x > 1 else x
    return x if x <= 1 else None


def build_items(sheet: SheetInfo) -> list[tuple[str, str, float | None]]:
    res = []
    for r in sheet.rows:
        c, n = norm_code(_cell(r, sheet.columns, "code")), clean_display(_cell(r, sheet.columns, "name"))
        if c and n:
            res.append((c, n, _parse_vat(_cell(r, sheet.columns, "vat")) if "vat" in sheet.columns else None))
    return res


def build_txns(sheet: SheetInfo, items: list[tuple], rep: ImportReport) -> list[Txn]:
    name_to_code = {norm_text(i[1]): i[0] for i in items}
    codes = {i[0] for i in items}
    default_type = "فروش" if sheet.name.strip() == "فروش" else ("خرید" if sheet.name.strip() == "خرید" else "")
    res = []
    for r in sheet.rows:
        if all(v in (None, "") for v in r):
            continue
        qty = parse_number(_cell(r, sheet.columns, "qty"))
        fee = parse_number(_cell(r, sheet.columns, "fee"))
        date_raw = _cell(r, sheet.columns, "date")
        if qty is None and fee is None and date_raw in (None, ""):
            continue
        tp_raw = norm_text(_cell(r, sheet.columns, "type"))
        tp = _TYPE_MAP.get(tp_raw) or _TYPE_MAP.get(tp_raw.replace(" ", "")) or default_type
        if not tp:
            rep.skipped += 1
            rep.messages.append(f"نوع تراکنش نامشخص ({tp_raw!r}) — ردیف نادیده گرفته شد")
            continue
        code = norm_code(_cell(r, sheet.columns, "code"))
        nm = clean_display(_cell(r, sheet.columns, "name"))
        if code not in codes:
            code = name_to_code.get(norm_text(nm), "")
        if not code:
            rep.unresolved += 1
        d = norm_date(date_raw) or clean_display(date_raw)
        res.append(Txn(date=d, type=tp, code=code, raw_name=nm,
                       party=clean_display(_cell(r, sheet.columns, "party")),
                       qty=qty if qty is not None else 0.0, fee=fee if fee is not None else 0.0))
    return res


def import_into(db, cid: int, sheets: list[SheetInfo], replace: bool = False,
                replace_items: bool = False) -> ImportReport:
    with db.undo.group(cid, "ورود از اکسل", ("items", "txns")):
        return _import_into(db, cid, sheets, replace, replace_items)


def _import_into(db, cid: int, sheets: list[SheetInfo], replace: bool, replace_items: bool) -> ImportReport:
    rep = ImportReport()
    if replace or replace_items:
        db.auto_backup("before_import_replace")
    if replace:
        db.clear_txns(cid)
    if replace_items:
        db.clear_txns(cid)
        db.clear_items(cid)
    items: list[tuple[str, str]] = []
    for s in sheets:
        if s.kind == "items":
            rows = build_items(s)
            a, u = db.upsert_items(cid, rows)
            rep.items_added += a
            rep.items_updated += u
            rep.vat_items += sum(1 for r in rows if r[2] is not None)
    items = db.items(cid)
    if not items:
        # فایل کدینگ جدا ندارد: کد و نام را از خود شیت‌های تراکنش می‌سازیم
        pairs: dict[str, str] = {}
        for s in sheets:
            if s.kind == "txns" and "code" in s.columns and "name" in s.columns:
                for r in s.rows:
                    c, n = norm_code(_cell(r, s.columns, "code")), clean_display(_cell(r, s.columns, "name"))
                    if c and n and c not in pairs:
                        pairs[c] = n
        if pairs:
            a, _u = db.upsert_items(cid, list(pairs.items()))
            rep.items_added += a
            rep.messages.append("کدینگ جدا در فایل نبود؛ کد و نام کالاها از شیت‌های تراکنش ساخته شد.")
            items = db.items(cid)
    for s in sheets:
        if s.kind == "txns":
            tx = build_txns(s, items, rep)
            db.add_txns(cid, tx)
            rep.txns_added += len(tx)
    return rep


def count_duplicates(db, cid: int, sheets: list[SheetInfo]) -> tuple[int, int]:
    """(تعداد ردیف‌های تراکنش فایل، تعداد ردیف‌هایی که عیناً از قبل در شرکت ثبت شده‌اند).
    مقایسه چندمجموعه‌ای است: دو فروش یکسان در یک روز فقط وقتی تکراری حساب می‌شوند که قبلاً هم دوبار ثبت شده باشند."""
    from collections import Counter
    items = db.items(cid)
    names = {norm_text(n): c for c, n in items}
    existing: Counter = Counter()
    for t in db.txns(cid):
        existing[(t.date, t.type, t.code, round(t.qty, 6), round(t.fee, 4))] += 1
    rep = ImportReport()
    total = dup = 0
    for sh in sheets:
        if sh.kind != "txns":
            continue
        for t in build_txns(sh, items, rep):
            code = t.code or names.get(norm_text(t.raw_name), "")
            key = (t.date, t.type, code, round(t.qty, 6), round(t.fee, 4))
            total += 1
            if existing[key] > 0:
                existing[key] -= 1
                dup += 1
    return total, dup


def read_file_settings(path: str | Path) -> dict:
    """تنظیمات داخل فایل اکسل قدیمی: درصد سود پیشنهادی (شیت خلاصه، سلول E2) و در نسخه‌های جدید
    آستانه‌های شیت «کنترل» (E2 انحراف نرخ خرید، E3 حداقل سود فروش). اگر نبود، دیکشنری خالی."""
    path = Path(path)
    out: dict = {}
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return out
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        def val(sheet, addr):
            if sheet not in wb.sheetnames:
                return None
            v = wb[sheet][addr].value
            return float(v) if isinstance(v, (int, float)) and 0 < v < 1 else None
        mk = val("خلاصه موجودی و نرخ", "E2")
        dv, mg = val("کنترل", "E2"), val("کنترل", "E3")
        wb.close()
    except Exception:
        return out
    if mk is not None:
        out["markup"] = mk
    if dv is not None:
        out["dev_threshold"] = dv
    if mg is not None:
        out["min_margin"] = mg
    return out
