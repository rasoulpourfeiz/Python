"""خروجی اکسل: گزارش کامل و فایل نمونه‌ی ورود داده."""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .allocation import AllocLine
from .engine import Result

_HDR_FILL = PatternFill("solid", fgColor="1F4E78")
_HDR_FONT = Font(bold=True, color="FFFFFF", name="Tahoma")
_BAD_FILL = PatternFill("solid", fgColor="FDE9E7")
_NUM = "#,##0"
_NUM2 = "#,##0.00"


def _sheet(wb: Workbook, title: str, headers: list[str], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = _HDR_FILL, _HDR_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    return ws


def _widths(ws, widths: list[int]):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def export_report(path: str, company: str, res: Result, alloc: list[AllocLine] | None = None):
    wb = Workbook()
    ws = _sheet(wb, "خلاصه موجودی", ["کد", "نام کالا", "موجودی", "میانگین بها", "ارزش موجودی",
                                     "قیمت پیشنهادی فروش", "وضعیت", "دفعات موجودی منفی", "تعداد تراکنش", "نرخ ارزش افزوده",
                                     "قیمت پیشنهادی با مالیات"], first=True)
    for s in res.summary:
        ws.append([s.code, s.name, s.qty, s.avg, s.value, s.price, s.status, s.neg_count, s.n_txn,
                   s.vat, s.price * (1 + s.vat)])
        ws.cell(ws.max_row, 10).number_format = "0%"
        ws.cell(ws.max_row, 11).number_format = _NUM
    n = ws.max_row
    ws.append([])
    ws.append(["", f"ارزش کل موجودی انبار ({company})", "", "", f"=SUM(E2:E{n})"])
    ws.cell(ws.max_row, 2).font = Font(bold=True)
    ws.cell(ws.max_row, 5).font = Font(bold=True)
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=6):
        for c in row:
            c.number_format = _NUM
    _widths(ws, [8, 28, 12, 16, 20, 18, 14, 12, 12, 12, 20])

    ws = _sheet(wb, "کاردکس", ["کالا", "ردیف", "تاریخ", "نوع", "طرف حساب", "مقدار ورودی", "مقدار خروجی",
                               "فی", "مبلغ", "موجودی", "میانگین بها", "ارزش موجودی", "درصد انحراف", "وضعیت"])
    for s in res.summary:
        for r in res.cardex_for(s.code):
            t = r.txn
            in_q = t.qty if t.type != "فروش" else 0
            out_q = t.qty if t.type == "فروش" else 0
            ws.append([f"{s.code} - {s.name}", r.rank, t.date, t.type, t.party, in_q, out_q, t.fee,
                       r.amount, r.bal, r.avg, r.bal * r.avg,
                       r.dev if r.dev is not None else "", r.status])
            if r.status:
                for c in ws[ws.max_row]:
                    c.fill = _BAD_FILL
            ws.cell(ws.max_row, 13).number_format = "0.00%"
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=12):
        for c in row:
            c.number_format = _NUM
    _widths(ws, [30, 7, 12, 10, 28, 12, 12, 14, 18, 12, 14, 18, 12, 24])

    ws = _sheet(wb, "مغایرت‌ها", ["شناسه", "تاریخ", "نوع", "طرف حساب", "کالا", "مقدار", "فی",
                                  "میانگین قبل", "درصد انحراف", "موجودی پس از ردیف", "وضعیت"])
    for r in res.issues:
        t = r.txn
        ws.append([t.id, t.date, t.type, t.party, r.name, t.qty, t.fee, r.prev_avg,
                   r.dev if r.dev is not None else "", r.bal, r.status])
        ws.cell(ws.max_row, 9).number_format = "0.00%"
    _widths(ws, [8, 12, 10, 28, 24, 12, 14, 14, 12, 16, 26])

    ws = _sheet(wb, "کنترل‌ها", ["کنترل", "مقدار مبنا", "مقدار کاردکس", "نتیجه"])
    for c in res.controls:
        ws.append([c.name, c.expected, c.actual, "✔" if c.ok else "✘ مغایرت"])
    _widths(ws, [90, 14, 14, 12])

    if alloc:
        ws = _sheet(wb, "تخصیص کالا", ["ردیف طرح", "تاریخ", "خریدار", "کد کالا", "نام کالا", "مقدار", "فی",
                                       "مبلغ", "مالیات", "جمع", "مبلغ فاکتور", "اختلاف", "وضعیت", "میانگین بها در تاریخ فروش"])
        for a in alloc:
            ws.append([a.plan_index, a.date, a.buyer, a.code, a.name, a.qty, a.price, a.amount,
                       a.tax, a.gross, a.plan_amount, a.diff, a.status, a.avg])
            if a.status != "کامل":
                for c in ws[ws.max_row]:
                    c.fill = _BAD_FILL
        for row in ws.iter_rows(min_row=2, min_col=6, max_col=12):
            for c in row:
                c.number_format = _NUM
        for row in ws.iter_rows(min_row=2, min_col=14, max_col=14):
            for c in row:
                c.number_format = _NUM
        _widths(ws, [9, 12, 30, 9, 26, 10, 12, 16, 14, 16, 16, 12, 14, 18])
    wb.save(path)


def export_template(path: str):
    wb = Workbook()
    ws = _sheet(wb, "کدینگ کالا", ["کد کالا", "نام کالا"], first=True)
    ws.append(["1", "نمونه کالا ۱"])
    _widths(ws, [12, 30])
    for title, tp in (("خرید", "خرید"), ("فروش", "فروش")):
        ws = _sheet(wb, title, ["تاریخ", "نوع", "طرف حساب", "کد کالا", "نام کالا", "مقدار", "فی"])
        ws.append(["1405/01/15", "اول دوره" if tp == "خرید" else "فروش", "—", "1", "نمونه کالا ۱", 100, 1000000])
        _widths(ws, [12, 10, 28, 10, 28, 12, 14])
    wb.save(path)
