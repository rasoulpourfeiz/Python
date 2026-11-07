"""تخصیص خودکار کالا به مبالغ فروش (جایگزین ماکروی AllocateProduct) + فاکتورهای رسمی.

دو نوع ردیف در طرح فروش:
 * ردیف خودکار: فقط «مبلغ نهایی فاکتور (با مالیات)» دارد؛ برنامه کالا و تعداد را تعیین می‌کند.
 * ردیف فاکتور رسمی: کالا + مقدار + (فی یا مبلغ نهایی) مشخص است؛ دقیقاً همان‌طور ثبت می‌شود
   (بدون گرد کردن و بدون قیمت‌گذاری مجدد) و موجودی‌اش پیش از ردیف‌های خودکار رزرو می‌شود.

نرخ مالیات هر کالا جدا است (مثلاً ۰٪، ۱۰٪ یا ۱۶٪)؛ تعداد هر کالا در ردیف خودکار از
«مبلغ باقیمانده ÷ (قیمت × (1 + نرخ مالیات آن کالا))» به دست می‌آید."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from .engine import ALL_TYPES, IN_TYPES, SELL, ItemSummary, Settings, Txn
from .textutil import date_key, mround

OFFICIAL = "رسمی"
OFFICIAL_SHORT = "رسمی — موجودی ناکافی"


@dataclass
class PlanRow:
    date: str
    buyer: str
    amount: float = 0.0           # مبلغ نهایی فاکتور با مالیات (ردیف خودکار؛ در ردیف رسمی اختیاری)
    code: str = ""                # کد کالا — فقط فاکتور رسمی
    qty: float | None = None      # مقدار — فقط فاکتور رسمی
    fee: float | None = None      # فی (قیمت واحد بدون مالیات) — فقط فاکتور رسمی

    @property
    def is_official(self) -> bool:
        return bool(self.code) and bool(self.qty) and self.qty > 0


@dataclass
class AllocLine:
    plan_index: int
    date: str
    buyer: str
    code: str
    name: str
    qty: float
    price: float
    amount: float          # qty * price
    tax: float
    gross: float
    plan_amount: float
    diff: float            # فقط روی آخرین خط هر ردیف: مبلغ فاکتور - جمع خطوط
    status: str            # کامل | جزئی | بدون موجودی | تاریخ نامعتبر | رسمی | رسمی — موجودی ناکافی
    avg: float = 0.0       # میانگین بهای کالا در تاریخ فروش


def _qty(x: float, mode: str) -> float:
    x = round(x, 9)
    if mode == "floor":
        return math.floor(x)
    if mode == "nearest":
        return math.floor(x + 0.5)
    return math.ceil(x)


def official_fee(p: PlanRow, rate: float) -> float | None:
    """فی فاکتور رسمی: اگر فی داده شده همان؛ وگرنه از مبلغ نهایی (با مالیات) استخراج می‌شود."""
    if p.fee is not None and p.fee >= 0:
        return p.fee
    if p.amount and p.amount > 0 and p.qty:
        return p.amount / (p.qty * (1 + rate))
    return None


def _official_line(idx: int, p: PlanRow, name: str, rate: float, enough: bool, avg: float = 0.0) -> AllocLine:
    fee = official_fee(p, rate) or 0.0
    amt = p.qty * fee
    tax = amt * rate
    gross = amt + tax
    diff = (p.amount - gross) if p.amount else 0.0
    return AllocLine(idx + 1, p.date, p.buyer, p.code, name, p.qty, fee, amt, tax, gross,
                     p.amount or 0.0, diff, OFFICIAL if enough else OFFICIAL_SHORT, avg)


def allocate(plan: list[PlanRow], summary: list[ItemSummary], s: Settings) -> list[AllocLine]:
    """تخصیص با موجودی و میانگین نهایی (رفتار ماکروی قدیمی)."""
    stock_all = {i.code: i.qty for i in summary}
    stock = {i.code: i.qty for i in summary if i.qty > 0 and i.price > 0}
    price = {i.code: i.price for i in summary}
    vat = {i.code: i.vat for i in summary}
    name = {i.code: i.name for i in summary}

    # ۱) فاکتورهای رسمی: ابتدا و بدون تغییر ثبت و موجودی‌شان رزرو می‌شود
    official: dict[int, AllocLine] = {}
    for idx, p in enumerate(plan):
        if p.is_official and p.code in name:
            rate = vat.get(p.code, s.tax_rate)
            if official_fee(p, rate) is None:
                continue
            enough = p.qty <= stock_all.get(p.code, 0) + 1e-9
            official[idx] = _official_line(idx, p, name[p.code], rate, enough)
            stock_all[p.code] = stock_all.get(p.code, 0) - p.qty
            if p.code in stock:
                stock[p.code] -= p.qty

    out: list[AllocLine] = []
    for idx, p in enumerate(plan):
        if idx in official:
            out.append(official[idx])
            continue
        if p.is_official or not p.amount or p.amount <= 0:
            continue
        remaining = p.amount                      # مبلغ نهایی (با مالیات)
        lines: list[AllocLine] = []
        guard = 0
        while remaining > 0.5 and guard < 50:
            guard += 1
            cands = [c for c, q in stock.items() if q > 0]
            if not cands:
                break
            unit = {c: price[c] * (1 + vat[c]) for c in cands}
            full = [c for c in cands if stock[c] >= remaining / unit[c]]
            if full:
                code = max(full, key=lambda c: stock[c])
                q = min(_qty(remaining / unit[code], s.qty_rounding), stock[code])
                if q <= 0:
                    q = min(1, stock[code])
            else:
                code = max(cands, key=lambda c: stock[c])
                q = stock[code]
            stock[code] -= q
            amt = q * price[code]
            tax = amt * vat[code]
            remaining -= amt + tax
            lines.append(AllocLine(idx + 1, p.date, p.buyer, code, name[code], q, price[code],
                                   amt, tax, amt + tax, p.amount, 0.0, ""))
            if not full and not s.allow_split:
                break
        if not lines:
            out.append(AllocLine(idx + 1, p.date, p.buyer, "", "", 0, 0, 0, 0, 0, p.amount,
                                 p.amount, "بدون موجودی"))
            continue
        status = "کامل" if remaining <= 0.5 else "جزئی"
        for l in lines:
            l.status = status
        lines[-1].diff = p.amount - sum(l.gross for l in lines)
        out.extend(lines)
    return out


def allocate_dated(plan: list[PlanRow], txns: list[Txn], items: list[tuple[str, str]],
                   s: Settings, vat_map: dict[str, float] | None = None) -> list[AllocLine]:
    """تخصیص با موجودی و میانگین بهای «همان تاریخ فروش».

    * ابتدا فاکتورهای رسمی (به ترتیب تاریخ) دقیقاً با همان کالا/مقدار/فی ثبت و مثل فروش واقعی در
      خط زمانی موجودی لحاظ می‌شوند؛ اگر در آن تاریخ موجودی کافی نباشد، علامت «موجودی ناکافی» می‌خورد
      (فاکتور رسمی یک واقعیت است و حذف نمی‌شود).
    * سپس هر ردیف خودکار (به ترتیب تاریخ):
        - میانگین بها = میانگین متحرک پس از آخرین تراکنش با تاریخ ≤ تاریخ فروش؛
        - موجودی قابل فروش = کمینه‌ی موجودی در آن تاریخ و تمام تاریخ‌های بعد؛
        - قیمت = MROUND(میانگین آن تاریخ × (1 + درصد سود)) و مالیات طبق نرخ همان کالا."""
    names = {c: n for c, n in items}
    vat_map = vat_map or {}
    ev: dict[str, list[tuple]] = defaultdict(list)
    for t in txns:
        dk = date_key(t.date)
        if t.code in names and dk is not None and t.qty > 0 and t.fee >= 0 and t.type in ALL_TYPES:
            ev[t.code].append((dk, 0 if t.type in IN_TYPES else 1, t.id, t.qty, t.fee, t.type))
    for c in ev:
        ev[c].sort()
    pseudo_id = [10 ** 9]

    def profile(code: str, dk: int) -> tuple[float, float]:
        bal = avg = bal_at = avg_at = 0.0
        later_min = float("inf")
        for d, _pri, _id, q, fee, tp in ev[code]:
            if tp in IN_TYPES:
                nb = round(bal + q, 6)
                if nb:
                    avg = (bal * avg + q * fee) / nb
                bal = nb
            else:
                bal = round(bal - q, 6)
            if d <= dk:
                bal_at, avg_at = bal, avg
            else:
                later_min = min(later_min, bal)
        return min(bal_at, later_min), avg_at

    def add_sale(code: str, dk: int, q: float, fee: float):
        pseudo_id[0] += 1
        ev[code].append((dk, 1, pseudo_id[0], q, fee, SELL))
        ev[code].sort()

    by_plan: dict[int, list[AllocLine]] = {}

    # ---- ۱) فاکتورهای رسمی
    off_idx = sorted((i for i, p in enumerate(plan) if p.is_official and p.code in names),
                     key=lambda i: (date_key(plan[i].date) or 99999999, i))
    for idx in off_idx:
        p = plan[idx]
        rate = vat_map.get(p.code, s.tax_rate)
        if official_fee(p, rate) is None:
            continue
        dk = date_key(p.date)
        if dk is None:
            by_plan[idx] = [AllocLine(idx + 1, p.date, p.buyer, p.code, names[p.code], p.qty, 0, 0, 0, 0,
                                      p.amount or 0.0, 0.0, "تاریخ نامعتبر")]
            continue
        avail, avg = profile(p.code, dk)
        by_plan[idx] = [_official_line(idx, p, names[p.code], rate, p.qty <= avail + 1e-9, avg)]
        add_sale(p.code, dk, p.qty, official_fee(p, rate))

    # ---- ۲) ردیف‌های خودکار
    order = sorted((i for i in range(len(plan)) if i not in by_plan),
                   key=lambda i: (date_key(plan[i].date) or 99999999, i))
    for idx in order:
        p = plan[idx]
        if p.is_official or not p.amount or p.amount <= 0:
            continue
        dk = date_key(p.date)
        if dk is None:
            by_plan[idx] = [AllocLine(idx + 1, p.date, p.buyer, "", "", 0, 0, 0, 0, 0, p.amount,
                                      p.amount, "تاریخ نامعتبر")]
            continue
        remaining = p.amount                      # مبلغ نهایی (با مالیات)
        lines: list[AllocLine] = []
        guard = 0
        while remaining > 0.5 and guard < 50:
            guard += 1
            cand = {}
            for code in ev:
                avail, avg = profile(code, dk)
                price = mround(avg * (1 + s.markup), s.round_to) if avg else 0.0
                if avail > 0 and price > 0:
                    rate = vat_map.get(code, s.tax_rate)
                    cand[code] = (avail, avg, price, rate, price * (1 + rate))
            if not cand:
                break
            full = [c for c, v in cand.items() if v[0] >= remaining / v[4]]
            if full:
                code = max(full, key=lambda c: cand[c][0])
                avail, avg, price, rate, unit = cand[code]
                q = min(_qty(remaining / unit, s.qty_rounding), avail)
                if q <= 0:
                    q = min(1, avail)
            else:
                code = max(cand, key=lambda c: cand[c][0])
                avail, avg, price, rate, unit = cand[code]
                q = avail
            amt = q * price
            tax = amt * rate
            remaining -= amt + tax
            lines.append(AllocLine(idx + 1, p.date, p.buyer, code, names[code], q, price, amt, tax,
                                   amt + tax, p.amount, 0.0, "", avg))
            add_sale(code, dk, q, price)
            if not full and not s.allow_split:
                break
        if not lines:
            by_plan[idx] = [AllocLine(idx + 1, p.date, p.buyer, "", "", 0, 0, 0, 0, 0, p.amount,
                                      p.amount, "بدون موجودی")]
            continue
        status = "کامل" if remaining <= 0.5 else "جزئی"
        for l in lines:
            l.status = status
        lines[-1].diff = p.amount - sum(l.gross for l in lines)
        by_plan[idx] = lines
    return [l for i in sorted(by_plan) for l in by_plan[i]]
