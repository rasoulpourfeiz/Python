"""ذخیره‌سازی چندشرکتی با SQLite (هر شرکت: کدینگ کالا، تراکنش‌ها، تنظیمات، طرح فروش)."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from .engine import Settings, Txn
from .undo import ALL, UndoStack
from .textutil import clean_display, norm_code, norm_date

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS companies(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, settings TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS items(
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, vat_rate REAL, UNIQUE(company_id, code));
CREATE TABLE IF NOT EXISTS txns(
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    date TEXT NOT NULL, type TEXT NOT NULL, party TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL DEFAULT '', raw_name TEXT NOT NULL DEFAULT '',
    qty REAL NOT NULL, fee REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_txns_company ON txns(company_id);
CREATE TABLE IF NOT EXISTS plan(
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    date TEXT NOT NULL DEFAULT '', buyer TEXT NOT NULL DEFAULT '', amount REAL NOT NULL DEFAULT 0,
    item TEXT NOT NULL DEFAULT '', qty REAL, fee REAL);
"""


def default_data_dir() -> Path:
    return Path.home() / "KardexApp"


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_data_dir() / "kardex.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrate()
        self.undo = UndoStack(self)

    def _migrate(self):
        cols = {r["name"] for r in self.con.execute("PRAGMA table_info(items)")}
        if "vat_rate" not in cols:                       # پایگاه‌داده‌ی نسخه‌های قبلی
            self.con.execute("ALTER TABLE items ADD COLUMN vat_rate REAL")
        pcols = {r["name"] for r in self.con.execute("PRAGMA table_info(plan)")}
        for col, ddl in (("item", "TEXT NOT NULL DEFAULT ''"), ("qty", "REAL"), ("fee", "REAL")):
            if col not in pcols:
                self.con.execute(f"ALTER TABLE plan ADD COLUMN {col} {ddl}")
        self.con.commit()

    def close(self):
        self.con.close()

    def backup(self, dest: str | Path):
        self.con.commit()
        shutil.copyfile(self.path, dest)

    def auto_backup(self, label: str = "auto", keep: int = 30) -> Path:
        """نسخه‌ی پشتیبان خودکار در پوشه‌ی backups (قبل از هر عملیات حذف/جایگزینی)."""
        d = self.path.parent / "backups"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{self.path.stem}_{datetime.now():%Y%m%d_%H%M%S}_{label}.db"
        self.con.commit()
        out = sqlite3.connect(str(dest))
        try:
            self.con.backup(out)
        finally:
            out.close()
        old = sorted(d.glob(f"{self.path.stem}_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in old[keep:]:
            p.unlink(missing_ok=True)
        return dest

    def restore(self, src: str | Path):
        """بازیابی از یک فایل پشتیبان (قبل از آن، از وضعیت فعلی نسخه‌ی خودکار گرفته می‌شود)."""
        src = Path(src)
        try:
            t = sqlite3.connect(str(src))
            names = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            t.close()
        except sqlite3.DatabaseError:
            names = set()
        if not {"companies", "items", "txns", "plan"} <= names:
            raise ValueError("این فایل، پشتیبان معتبر برنامه نیست.")
        self.auto_backup("before_restore")
        self.con.close()
        shutil.copyfile(src, self.path)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrate()
        self.undo.clear()

    # ---------- شرکت‌ها ----------
    def companies(self) -> list[tuple[int, str]]:
        return [(r["id"], r["name"]) for r in
                self.con.execute("SELECT id, name FROM companies ORDER BY name")]

    def add_company(self, name: str) -> int:
        name = clean_display(name)
        if not name:
            raise ValueError("نام شرکت خالی است")
        cur = self.con.execute("INSERT INTO companies(name, settings) VALUES(?, ?)",
                               (name, json.dumps(asdict(Settings()))))
        self.con.commit()
        self.undo.record_added(cur.lastrowid)
        return cur.lastrowid

    def rename_company(self, cid: int, name: str):
        self.undo.record(cid, "تغییر نام شرکت", ("company",))
        self.con.execute("UPDATE companies SET name=? WHERE id=?", (clean_display(name), cid))
        self.con.commit()

    def delete_company(self, cid: int):
        self.undo.record(cid, "حذف شرکت", ALL)
        self.con.execute("DELETE FROM companies WHERE id=?", (cid,))
        self.con.commit()

    def get_settings(self, cid: int) -> Settings:
        r = self.con.execute("SELECT settings FROM companies WHERE id=?", (cid,)).fetchone()
        return Settings.from_dict(json.loads(r["settings"]) if r else {})

    def save_settings(self, cid: int, s: Settings):
        self.undo.record(cid, "تغییر تنظیمات", ("settings",))
        self.con.execute("UPDATE companies SET settings=? WHERE id=?",
                         (json.dumps(asdict(s)), cid))
        self.con.commit()

    # ---------- کدینگ کالا ----------
    def items(self, cid: int) -> list[tuple[str, str]]:
        rows = [(r["code"], r["name"]) for r in
                self.con.execute("SELECT code, name FROM items WHERE company_id=?", (cid,))]
        rows.sort(key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]))
        return rows

    def items_full(self, cid: int) -> list[tuple[str, str, float | None]]:
        """(کد، نام، نرخ ارزش افزوده به‌صورت کسر یا None = نرخ پیش‌فرض شرکت)."""
        rows = [(r["code"], r["name"], r["vat_rate"]) for r in
                self.con.execute("SELECT code, name, vat_rate FROM items WHERE company_id=?", (cid,))]
        rows.sort(key=lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]))
        return rows

    def vat_map(self, cid: int, default: float) -> dict[str, float]:
        return {c: (default if v is None else v) for c, _n, v in self.items_full(cid)}

    def add_item(self, cid: int, code: str, name: str, vat: float | None = None):
        code, name = norm_code(code), clean_display(name)
        if not code or not name:
            raise ValueError("کد و نام کالا باید پر باشند")
        self.undo.record(cid, "افزودن کالا", ("items",))
        try:
            self.con.execute("INSERT INTO items(company_id, code, name, vat_rate) VALUES(?,?,?,?)",
                             (cid, code, name, vat))
        except sqlite3.IntegrityError:
            raise ValueError(f"کد «{code}» قبلاً ثبت شده است")
        self.con.commit()

    def update_item(self, cid: int, old_code: str, code: str, name: str, vat: float | None = None):
        code, name = norm_code(code), clean_display(name)
        if not code or not name:
            raise ValueError("کد و نام کالا باید پر باشند")
        self.undo.record(cid, "ویرایش کالا", ("items", "txns") if code != old_code else ("items",))
        try:
            self.con.execute("UPDATE items SET code=?, name=?, vat_rate=? WHERE company_id=? AND code=?",
                             (code, name, vat, cid, old_code))
            if code != old_code:
                self.con.execute("UPDATE txns SET code=? WHERE company_id=? AND code=?",
                                 (code, cid, old_code))
        except sqlite3.IntegrityError:
            self.con.rollback()
            raise ValueError(f"کد «{code}» قبلاً ثبت شده است")
        self.con.commit()

    def delete_item(self, cid: int, code: str):
        self.undo.record(cid, "حذف کالا", ("items",))
        self.con.execute("DELETE FROM items WHERE company_id=? AND code=?", (cid, code))
        self.con.commit()

    def clear_items(self, cid: int):
        self.undo.record(cid, "حذف کدینگ کالا", ("items",))
        self.con.execute("DELETE FROM items WHERE company_id=?", (cid,))
        self.con.commit()

    def item_usage(self, cid: int, code: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM txns WHERE company_id=? AND code=?",
                                (cid, code)).fetchone()[0]

    def upsert_items(self, cid: int, rows: list[tuple]) -> tuple[int, int]:
        """ردیف‌ها: (کد، نام) یا (کد، نام، نرخ ارزش افزوده)؛ نرخ None موجود را تغییر نمی‌دهد."""
        added = updated = 0
        self.undo.record(cid, "ورود کدینگ کالا", ("items",))
        for row in rows:
            code, name = norm_code(row[0]), clean_display(row[1])
            vat = row[2] if len(row) > 2 else None
            if not code or not name:
                continue
            ex = self.con.execute("SELECT id FROM items WHERE company_id=? AND code=?",
                                  (cid, code)).fetchone()
            if ex:
                self.con.execute("UPDATE items SET name=? WHERE id=?", (name, ex["id"]))
                if vat is not None:
                    self.con.execute("UPDATE items SET vat_rate=? WHERE id=?", (vat, ex["id"]))
                updated += 1
            else:
                self.con.execute("INSERT INTO items(company_id, code, name, vat_rate) VALUES(?,?,?,?)",
                                 (cid, code, name, vat))
                added += 1
        self.con.commit()
        return added, updated

    # ---------- تراکنش‌ها ----------
    def txns(self, cid: int) -> list[Txn]:
        return [Txn(id=r["id"], date=r["date"], type=r["type"], party=r["party"],
                    code=r["code"], raw_name=r["raw_name"], qty=r["qty"], fee=r["fee"])
                for r in self.con.execute(
                    "SELECT * FROM txns WHERE company_id=? ORDER BY id", (cid,))]

    def add_txn(self, cid: int, t: Txn, commit: bool = True) -> int:
        if commit:
            self.undo.record(cid, "افزودن تراکنش", ("txns",))
        d = norm_date(t.date) or clean_display(t.date)
        cur = self.con.execute(
            "INSERT INTO txns(company_id,date,type,party,code,raw_name,qty,fee) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (cid, d, t.type, clean_display(t.party), norm_code(t.code),
             clean_display(t.raw_name), t.qty, t.fee))
        if commit:
            self.con.commit()
        return cur.lastrowid

    def add_txns(self, cid: int, txns: list[Txn]):
        self.undo.record(cid, f"افزودن {len(txns)} تراکنش", ("txns",))
        for t in txns:
            self.add_txn(cid, t, commit=False)
        self.con.commit()

    def _txn_company(self, tid: int) -> int | None:
        r = self.con.execute("SELECT company_id FROM txns WHERE id=?", (tid,)).fetchone()
        return r["company_id"] if r else None

    def update_txn(self, tid: int, t: Txn):
        cid = self._txn_company(tid)
        if cid:
            self.undo.record(cid, "ویرایش تراکنش", ("txns",))
        d = norm_date(t.date) or clean_display(t.date)
        self.con.execute(
            "UPDATE txns SET date=?,type=?,party=?,code=?,raw_name=?,qty=?,fee=? WHERE id=?",
            (d, t.type, clean_display(t.party), norm_code(t.code),
             clean_display(t.raw_name), t.qty, t.fee, tid))
        self.con.commit()

    def delete_txns(self, ids: list[int]):
        cid = self._txn_company(ids[0]) if ids else None
        if cid:
            self.undo.record(cid, f"حذف {len(ids)} تراکنش", ("txns",))
        self.con.executemany("DELETE FROM txns WHERE id=?", [(i,) for i in ids])
        self.con.commit()

    def clear_txns(self, cid: int):
        self.undo.record(cid, "حذف تراکنش‌ها", ("txns",))
        self.con.execute("DELETE FROM txns WHERE company_id=?", (cid,))
        self.con.commit()

    # ---------- طرح فروش (تخصیص) ----------
    def plan(self, cid: int) -> list[tuple]:
        """هر ردیف: (تاریخ، خریدار، مبلغ نهایی، کالا، مقدار، فی)."""
        return [(r["date"], r["buyer"], r["amount"], r["item"], r["qty"], r["fee"]) for r in
                self.con.execute("SELECT date,buyer,amount,item,qty,fee FROM plan WHERE company_id=? ORDER BY id",
                                 (cid,))]

    def save_plan(self, cid: int, rows: list[tuple]):
        self.undo.record(cid, "تغییر طرح تخصیص", ("plan",))
        self.con.execute("DELETE FROM plan WHERE company_id=?", (cid,))
        self.con.executemany(
            "INSERT INTO plan(company_id,date,buyer,amount,item,qty,fee) VALUES(?,?,?,?,?,?,?)",
            [(cid, r[0], r[1], r[2] or 0.0, r[3] if len(r) > 3 else "", r[4] if len(r) > 4 else None,
              r[5] if len(r) > 5 else None) for r in rows])
        self.con.commit()
