"""Undo / Redo برای تمام عملیات تغییردهنده‌ی داده.

هر عملیات قبل از اجرا «عکس» بخش‌های تغییرپذیر داده‌ی همان شرکت را ذخیره می‌کند (فقط بخش‌های لازم:
مثلاً ویرایش طرح تخصیص فقط عکس طرح را می‌گیرد، نه ۱۰ هزار تراکنش). بازگردانی همان بخش‌ها را
دقیقاً (با همان شناسه‌ها) برمی‌گرداند و از وضعیت فعلی برای Redo عکس می‌گیرد.
حذف شرکت و ساخت شرکت هم قابل بازگردانی است."""
from __future__ import annotations

import marshal
import zlib
from contextlib import contextmanager
from dataclasses import dataclass

ALL = ("company", "settings", "items", "txns", "plan")


@dataclass
class Snap:
    exists: bool = True
    name: str | None = None
    settings: str | None = None
    items: list | None = None
    txns: list | None = None
    plan: list | None = None

    def rows(self) -> int:
        return sum(len(x) for x in (self.items, self.txns, self.plan) if x)


def pack(sn: Snap) -> bytes:
    """عکس را فشرده می‌کند تا حافظه‌ی شرکت‌های بزرگ (۱۰ هزار تراکنش) زیاد نشود."""
    return zlib.compress(marshal.dumps((sn.exists, sn.name, sn.settings, sn.items, sn.txns, sn.plan)), 1)


def unpack(blob: bytes) -> Snap:
    exists, name, settings, items, txns, plan = marshal.loads(zlib.decompress(blob))
    return Snap(exists, name, settings, items, txns, plan)


@dataclass
class Entry:
    label: str
    cid: int
    scopes: tuple
    blob: bytes
    n: int = 0                    # تعداد ردیف‌های عکس (برای سقف حافظه)

    @property
    def snap(self) -> Snap:
        return unpack(self.blob)


def make_entry(label: str, cid: int, scopes, sn: Snap) -> Entry:
    return Entry(label, cid, tuple(scopes), pack(sn), sn.rows())


class UndoStack:
    def __init__(self, db, max_entries: int = 50, max_rows: int = 600_000):
        self.db = db
        self.max_entries, self.max_rows = max_entries, max_rows
        self.undo_stack: list[Entry] = []
        self.redo_stack: list[Entry] = []
        self._depth = 0
        self.on_change = None            # callback بدون آرگومان، برای به‌روزرسانی دکمه‌ها

    # ---------- عکس‌برداری و بازگردانی ----------
    def capture(self, cid: int, scopes) -> Snap:
        con = self.db.con
        row = con.execute("SELECT name, settings FROM companies WHERE id=?", (cid,)).fetchone()
        if row is None:
            return Snap(exists=False)
        sn = Snap(exists=True)
        if "company" in scopes:
            sn.name = row["name"]
        if "settings" in scopes:
            sn.settings = row["settings"]
        if "items" in scopes:
            sn.items = [tuple(r) for r in con.execute(
                "SELECT code, name, vat_rate FROM items WHERE company_id=?", (cid,))]
        if "txns" in scopes:
            sn.txns = [tuple(r) for r in con.execute(
                "SELECT id, date, type, party, code, raw_name, qty, fee FROM txns WHERE company_id=? ORDER BY id",
                (cid,))]
        if "plan" in scopes:
            sn.plan = [tuple(r) for r in con.execute(
                "SELECT date, buyer, amount, item, qty, fee FROM plan WHERE company_id=? ORDER BY id", (cid,))]
        return sn

    def apply(self, cid: int, scopes, sn: Snap):
        con = self.db.con
        if not sn.exists:
            con.execute("DELETE FROM companies WHERE id=?", (cid,))      # CASCADE: کالا/تراکنش/طرح
            con.commit()
            return
        exists = con.execute("SELECT 1 FROM companies WHERE id=?", (cid,)).fetchone()
        if not exists:
            name = sn.name or f"شرکت {cid}"
            if con.execute("SELECT 1 FROM companies WHERE name=?", (name,)).fetchone():
                name += " (بازیابی‌شده)"
            con.execute("INSERT INTO companies(id, name, settings) VALUES(?,?,?)",
                        (cid, name, sn.settings or "{}"))
        else:
            if sn.name is not None:
                name = sn.name
                if con.execute("SELECT 1 FROM companies WHERE name=? AND id<>?", (name, cid)).fetchone():
                    name += " (بازیابی‌شده)"
                con.execute("UPDATE companies SET name=? WHERE id=?", (name, cid))
            if sn.settings is not None:
                con.execute("UPDATE companies SET settings=? WHERE id=?", (sn.settings, cid))
        if sn.items is not None:
            con.execute("DELETE FROM items WHERE company_id=?", (cid,))
            con.executemany("INSERT INTO items(company_id, code, name, vat_rate) VALUES(?,?,?,?)",
                            [(cid, *r) for r in sn.items])
        if sn.txns is not None:
            con.execute("DELETE FROM txns WHERE company_id=?", (cid,))
            try:
                con.executemany(
                    "INSERT INTO txns(id, company_id, date, type, party, code, raw_name, qty, fee) "
                    "VALUES(?,?,?,?,?,?,?,?,?)", [(r[0], cid, *r[1:]) for r in sn.txns])
            except Exception:           # شناسه‌ی اشغال‌شده (نادر): همان ترتیب با شناسه‌های جدید
                con.execute("DELETE FROM txns WHERE company_id=?", (cid,))
                con.executemany(
                    "INSERT INTO txns(company_id, date, type, party, code, raw_name, qty, fee) "
                    "VALUES(?,?,?,?,?,?,?,?)", [(cid, *r[1:]) for r in sn.txns])
        if sn.plan is not None:
            con.execute("DELETE FROM plan WHERE company_id=?", (cid,))
            con.executemany("INSERT INTO plan(company_id, date, buyer, amount, item, qty, fee) "
                            "VALUES(?,?,?,?,?,?,?)", [(cid, *r) for r in sn.plan])
        con.commit()

    # ---------- ثبت ----------
    def _push(self, e: Entry):
        self.undo_stack.append(e)
        self.redo_stack.clear()
        total = 0
        for i in range(len(self.undo_stack) - 1, -1, -1):
            total += self.undo_stack[i].n
            if total > self.max_rows and i < len(self.undo_stack) - 1:
                del self.undo_stack[: i + 1]
                break
        if len(self.undo_stack) > self.max_entries:
            del self.undo_stack[: len(self.undo_stack) - self.max_entries]
        self._changed()

    def record(self, cid: int, label: str, scopes=("txns",)):
        """پیش از هر تغییر صدا زده می‌شود. داخل group نادیده گرفته می‌شود (فقط یک مرحله ثبت شده است)."""
        if self._depth > 0:
            return
        self._push(make_entry(label, cid, scopes, self.capture(cid, scopes)))

    def record_added(self, cid: int, label: str = "ساخت شرکت"):
        if self._depth > 0:
            return
        self._push(make_entry(label, cid, ALL, Snap(exists=False)))

    @contextmanager
    def group(self, cid: int, label: str, scopes=("txns",)):
        self.record(cid, label, scopes)
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

    # ---------- اجرا ----------
    def _swap(self, src: list, dst: list):
        e = src.pop()
        current = make_entry(e.label, e.cid, e.scopes, self.capture(e.cid, e.scopes))
        self.apply(e.cid, e.scopes, e.snap)
        dst.append(current)
        self._changed()
        return e.label, e.cid

    def undo(self):
        return self._swap(self.undo_stack, self.redo_stack) if self.undo_stack else None

    def redo(self):
        return self._swap(self.redo_stack, self.undo_stack) if self.redo_stack else None

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._changed()

    @property
    def undo_label(self) -> str:
        return self.undo_stack[-1].label if self.undo_stack else ""

    @property
    def redo_label(self) -> str:
        return self.redo_stack[-1].label if self.redo_stack else ""

    def _changed(self):
        if self.on_change:
            self.on_change()
