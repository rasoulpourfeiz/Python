"""پاک‌سازی اطلاعات قبلی یک شرکت (با پشتیبان خودکار و امکان انتقال موجودی به اول دوره)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import engine
from .engine import OPENING, Txn
from .textutil import date_key, norm_date


@dataclass
class ClearOptions:
    txns: bool = True          # حذف تراکنش‌ها
    until: str = ""            # خالی = همه؛ در غیر این صورت فقط تراکنش‌های با تاریخ ≤ این تاریخ
    carry: bool = False        # انتقال موجودی/میانگین پایان دوره به «اول دوره» (به تاریخ until)
    plan: bool = True          # پاک کردن طرح تخصیص
    items: bool = False        # حذف کدینگ کالا (فقط وقتی تمام تراکنش‌ها حذف می‌شوند)


@dataclass
class ClearReport:
    deleted: int = 0
    carried: int = 0
    skipped_negative: list[str] = field(default_factory=list)
    items_deleted: int = 0
    plan_cleared: bool = False
    backup: str = ""


def validate(o: ClearOptions) -> str:
    """پیام خطا یا رشته‌ی خالی."""
    if o.until and not norm_date(o.until):
        return "تاریخ معتبر نیست (مثال: 1405/07/30)."
    if o.carry and not o.until:
        return "برای انتقال موجودی، تاریخ پایان دوره را وارد کنید."
    if o.carry and not o.txns:
        return "انتقال موجودی فقط همراه با حذف تراکنش‌ها معنی دارد."
    if o.items and (o.until or not o.txns):
        return "حذف کدینگ فقط با حذف «همه‌ی» تراکنش‌ها ممکن است."
    return ""


def targets(txns: list[Txn], o: ClearOptions) -> list[Txn]:
    if not o.txns:
        return []
    if not o.until:
        return list(txns)
    uk = date_key(o.until)
    return [t for t in txns if (dk := date_key(t.date)) is not None and dk <= uk]


def preview_count(db, cid: int, o: ClearOptions) -> int:
    return len(targets(db.txns(cid), o))


def clear(db, cid: int, o: ClearOptions) -> ClearReport:
    err = validate(o)
    if err:
        raise ValueError(err)
    with db.undo.group(cid, "حذف اطلاعات قبلی", ("items", "txns", "plan")):
        return _clear(db, cid, o)


def _clear(db, cid: int, o: ClearOptions) -> ClearReport:
    rep = ClearReport()
    rep.backup = str(db.auto_backup("before_clear"))
    txns = db.txns(cid)
    tg = targets(txns, o)
    carry_rows: list[Txn] = []
    if o.carry:
        res = engine.compute(tg, db.items(cid), db.get_settings(cid))
        d = norm_date(o.until)
        for s in res.summary:
            if s.qty > 0 and s.avg > 0:
                carry_rows.append(Txn(date=d, type=OPENING, code=s.code, qty=s.qty, fee=s.avg,
                                      party="انتقال از دوره قبل"))
            elif s.qty < 0:
                rep.skipped_negative.append(f"{s.code} - {s.name} ({s.qty:g})")
    if tg:
        db.delete_txns([t.id for t in tg])
    rep.deleted = len(tg)
    if carry_rows:
        db.add_txns(cid, carry_rows)
    rep.carried = len(carry_rows)
    if o.items:
        rep.items_deleted = len(db.items(cid))
        db.clear_items(cid)
    if o.plan:
        db.save_plan(cid, [])
        rep.plan_cleared = True
    return rep
