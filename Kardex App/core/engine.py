"""موتور کاردکس: میانگین موزون متحرک، کنترل‌ها و خلاصه‌ی موجودی.
منطق دقیقاً مطابق شیت‌های «کاردکس زنده»، «خلاصه موجودی و نرخ» و «کنترل» فایل اکسل است."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, fields

from .textutil import date_key, mround, norm_date

OPENING, BUY, SELL = "اول دوره", "خرید", "فروش"
IN_TYPES = (OPENING, BUY)
ALL_TYPES = (OPENING, BUY, SELL)

ST_DATE = "تاریخ نامعتبر"
ST_ITEM = "نام کالا نامعتبر"
ST_TYPE = "نوع نامعتبر"
ST_VALUE = "مقدار/فی نامعتبر"
ST_NEG = "موجودی منفی"
ST_DEV = "انحراف نرخ خرید"
ST_LOW = "فروش کمتر از حد سود مجاز"


@dataclass
class Settings:
    tax_rate: float = 0.10        # مالیات و عوارض
    dev_threshold: float = 0.05   # آستانه انحراف نرخ خرید (±)
    min_margin: float = 0.02      # حداقل سود فروش نسبت به میانگین بها
    markup: float = 0.025         # درصد سود برای قیمت پیشنهادی
    round_to: float = 500         # گرد کردن قیمت پیشنهادی
    qty_rounding: str = "ceil"    # ceil | nearest | floor
    allow_split: bool = True      # تقسیم یک فروش بین چند کالا
    dated_allocation: bool = True # تخصیص با موجودی و میانگین بهای همان تاریخ فروش

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Txn:
    date: str
    type: str
    code: str
    qty: float
    fee: float
    party: str = ""
    raw_name: str = ""
    id: int = 0


@dataclass
class Row:
    txn: Txn
    name: str = ""
    rank: int = 0
    prev_bal: float = 0.0
    bal: float = 0.0
    prev_avg: float = 0.0
    avg: float = 0.0
    dev: float | None = None
    status: str = ""

    @property
    def amount(self) -> float:
        return self.txn.qty * self.txn.fee


@dataclass
class ItemSummary:
    code: str
    name: str
    qty: float = 0.0
    avg: float = 0.0
    value: float = 0.0
    price: float = 0.0       # قیمت پیشنهادی فروش
    status: str = ""
    neg_count: int = 0
    n_txn: int = 0
    vat: float = 0.0         # نرخ ارزش افزوده‌ی کالا (کسر)


@dataclass
class Control:
    name: str
    expected: float
    actual: float
    ok: bool


@dataclass
class Result:
    rows: list[Row] = field(default_factory=list)
    summary: list[ItemSummary] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)

    @property
    def issues(self) -> list[Row]:
        return [r for r in self.rows if r.status]

    @property
    def total_value(self) -> float:
        return sum(s.value for s in self.summary)

    @property
    def negative_items(self) -> int:
        return sum(1 for s in self.summary if s.status == "منفی است!")

    @property
    def all_ok(self) -> bool:
        return not self.issues and all(c.ok for c in self.controls)

    def cardex_for(self, code: str) -> list[Row]:
        return sorted([r for r in self.rows if r.txn.code == code and r.rank],
                      key=lambda r: r.rank)


def compute(txns: list[Txn], items: list[tuple[str, str]], s: Settings,
            vat_map: dict[str, float] | None = None) -> Result:
    names = {c: n for c, n in items}
    vat_map = vat_map or {}
    res = Result()
    by_code: dict[str, list[Row]] = defaultdict(list)
    all_rows: list[Row] = []

    for t in txns:
        row = Row(txn=t, name=names.get(t.code, t.raw_name))
        all_rows.append(row)
        if t.type not in ALL_TYPES:
            row.status = ST_TYPE
        elif t.code not in names:
            row.status = ST_ITEM
        elif not (t.qty and t.qty > 0) or t.fee is None or t.fee < 0:
            row.status = ST_VALUE
        else:
            by_code[t.code].append(row)

    for code, rows in by_code.items():
        def key(r: Row):
            dk = date_key(r.txn.date)
            return (dk if dk is not None else 99999999,
                    0 if r.txn.type in IN_TYPES else 1, r.txn.id)
        rows.sort(key=key)
        bal = avg = 0.0
        for i, r in enumerate(rows, 1):
            r.rank = i
            t = r.txn
            r.prev_bal, r.prev_avg = bal, avg
            if t.type in IN_TYPES:
                nb = round(bal + t.qty, 6)
                if nb != 0:
                    avg = (bal * avg + t.qty * t.fee) / nb
                bal = nb
            else:
                bal -= t.qty
            bal = round(bal, 6)   # حذف خطای اعشاری (مثلاً 2e-13 به‌جای صفر)
            r.bal, r.avg = bal, avg
            if t.type != OPENING and r.prev_avg != 0:
                r.dev = t.fee / r.prev_avg - 1
            # وضعیت کنترل (هم‌ارز ستون «وضعیت کنترل» شیت زنده)
            if date_key(t.date) is None:
                r.status = ST_DATE
            elif r.bal < 0:
                r.status = ST_NEG if r.prev_bal >= 0 else ""
            elif r.dev is None:
                r.status = ""
            elif t.type == SELL:
                r.status = ST_LOW if r.dev < s.min_margin else ""
            elif abs(r.dev) > s.dev_threshold:
                r.status = ST_DEV

    res.rows = all_rows

    for code, name in items:
        rows = sorted(by_code.get(code, []), key=lambda r: r.rank)
        it = ItemSummary(code=code, name=name, vat=vat_map.get(code, s.tax_rate))
        if rows:
            last = rows[-1]
            it.qty, it.avg = last.bal, last.avg
            it.neg_count = sum(1 for r in rows if r.bal < 0)
            it.n_txn = len(rows)
        it.value = it.qty * it.avg
        it.price = mround(it.avg * (1 + s.markup), s.round_to) if it.avg else 0.0
        it.status = "منفی است!" if it.qty < 0 else ("موجودی صفر" if it.qty == 0 else "موجودی دارد")
        res.summary.append(it)

    # ---- کنترل‌های تطبیقی ----
    valid = [r for rows in by_code.values() for r in rows]
    net = sum(r.txn.qty if r.txn.type in IN_TYPES else -r.txn.qty for r in valid)
    sum_stock = sum(i.qty for i in res.summary)
    n_bad_item = sum(1 for r in all_rows if r.status == ST_ITEM)
    n_bad_date = sum(1 for r in all_rows if r.status == ST_DATE)
    n_bad_val = sum(1 for r in all_rows if r.status in (ST_VALUE, ST_TYPE))
    res.controls = [
        Control("تعداد تراکنش‌های ثبت‌شده برابر ردیف‌های واردشده به محاسبه‌ی کاردکس",
                len(txns), len(valid), len(txns) == len(valid)),
        Control("خالص مقدار (خرید − فروش) برابر مجموع موجودی کالاها در خلاصه", net, sum_stock,
                abs(net - sum_stock) < 1e-6),
        Control("ردیف‌های با نام/کد کالای نامعتبر (در کدینگ نیست)", 0, n_bad_item, n_bad_item == 0),
        Control("ردیف‌های با تاریخ نامعتبر", 0, n_bad_date, n_bad_date == 0),
        Control("ردیف‌های با مقدار/فی/نوع نامعتبر", 0, n_bad_val, n_bad_val == 0),
    ]
    return res
