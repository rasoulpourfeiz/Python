"""تب‌های برنامه."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QSplitter, QVBoxLayout, QWidget)

from core import allocation
from core.allocation import PlanRow
from core.engine import SELL, Settings, Txn
from core.exporter import export_report
from core.textutil import clean_display, fmt_num, norm_date, norm_text, parse_number
from .widgets import (BAD, GOOD, WARN, ItemDialog, NumItem, ask, finish_table, info, make_table,
                      paint_row, txt, warn)


def _row(*widgets) -> QHBoxLayout:
    h = QHBoxLayout()
    for w in widgets:
        if w is None:
            h.addStretch(1)
        else:
            h.addWidget(w)
    return h


# ------------------------------------------------------------------ کدینگ کالا
class ItemsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.search = QLineEdit()
        self.search.setPlaceholderText("جستجوی کد یا نام کالا…")
        self.search.textChanged.connect(self._filter)
        self.table = make_table(["کد کالا", "نام کالا", "ارزش افزوده (٪)"],
                                stretch_col=1, sortable=False)
        self.table.itemChanged.connect(self._changed)
        add, rm = QPushButton("＋ کالای جدید"), QPushButton("حذف کالای انتخاب‌شده")
        add.clicked.connect(self.add)
        rm.clicked.connect(self.remove)
        self.count = QLabel()
        hint = QLabel("برای تغییر کد، نام یا نرخ ارزش افزوده، روی سلول دوبار کلیک کنید. نرخ ارزش افزوده برای هر کالا جدا "
                      "است (مثلاً 0، 10 یا 16)؛ اگر خالی بماند، «مالیات و عوارض» پیش‌فرض شرکت (تب تنظیمات) اعمال می‌شود. "
                      "هر شرکت کدینگ مستقل خودش را دارد.")
        hint.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(_row(self.search, add, rm))
        lay.addWidget(self.table)
        lay.addWidget(self.count)

    def reload(self):
        t = self.table
        t.blockSignals(True)
        t.setRowCount(0)
        for code, name, vat in self.main.db.items_full(self.main.cid):
            r = t.rowCount()
            t.insertRow(r)
            a, b = txt(code, True), txt(name, True)
            a.setData(Qt.UserRole, code)
            t.setItem(r, 0, a)
            t.setItem(r, 1, b)
            t.setItem(r, 2, txt("" if vat is None else f"{vat * 100:g}", True))
        t.resizeColumnToContents(0)
        t.setColumnWidth(2, 140)
        t.horizontalHeaderItem(2).setToolTip("خالی = نرخ پیش‌فرض شرکت (تب تنظیمات)")
        t.blockSignals(False)
        self.count.setText(f"{len(self.main.items)} کالا")
        self._filter()

    def _filter(self):
        q = self.search.text().strip().lower()
        for r in range(self.table.rowCount()):
            show = not q or q in (self.table.item(r, 0).text() + " " + self.table.item(r, 1).text()).lower()
            self.table.setRowHidden(r, not show)

    def add(self):
        d = ItemDialog(self)
        if d.exec():
            try:
                self.main.db.add_item(self.main.cid, d.code.text(), d.name.text(), d.vat())
            except ValueError as e:
                warn(self, "خطا", str(e))
                return
            self.main.refresh()

    def remove(self):
        rows = {i.row() for i in self.table.selectedItems()}
        if not rows:
            return
        codes = [self.table.item(r, 0).data(Qt.UserRole) for r in rows]
        used = [c for c in codes if self.main.db.item_usage(self.main.cid, c)]
        if used:
            warn(self, "امکان حذف نیست",
                 "این کالاها در تراکنش‌ها استفاده شده‌اند: " + "، ".join(used) +
                 "\nابتدا تراکنش‌های مربوط را حذف یا اصلاح کنید.")
            return
        if ask(self, "حذف", f"{len(codes)} کالا حذف شود؟"):
            for c in codes:
                self.main.db.delete_item(self.main.cid, c)
            self.main.refresh()

    def _changed(self, it):
        r = it.row()
        old = self.table.item(r, 0).data(Qt.UserRole)
        vat_txt = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
        vat = None
        if vat_txt:
            x = parse_number(vat_txt)
            if x is None or not 0 <= x <= 100:
                warn(self, "خطا", "نرخ ارزش افزوده باید عددی بین 0 و 100 باشد.")
                QTimer.singleShot(0, self.main.refresh)
                return
            vat = x / 100
        try:
            self.main.db.update_item(self.main.cid, old, self.table.item(r, 0).text(),
                                     self.table.item(r, 1).text(), vat)
        except ValueError as e:
            warn(self, "خطا", str(e))
        QTimer.singleShot(0, self.main.refresh)


# ------------------------------------------------------------------ تراکنش‌ها
class TxnTab(QWidget):
    HEAD = ["شناسه", "تاریخ", "نوع", "طرف حساب", "کد", "نام کالا", "مقدار", "فی", "مبلغ", "مالیات",
            "جمع با مالیات", "وضعیت کنترل"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.type = QComboBox()
        self.type.addItems(["همه انواع", "اول دوره", "خرید", "فروش"])
        self.search = QLineEdit()
        self.search.setPlaceholderText("جستجو در طرف حساب / کالا…")
        self.only_bad = QCheckBox("فقط ردیف‌های مغایر")
        for w in (self.type,):
            w.currentIndexChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)
        self.only_bad.toggled.connect(self.reload)
        self.table = make_table(self.HEAD, stretch_col=5)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        add, ed, rm, imp = (QPushButton("＋ تراکنش جدید"), QPushButton("ویرایش"),
                            QPushButton("حذف انتخاب‌شده‌ها"), QPushButton("ورود از اکسل…"))
        add.clicked.connect(lambda: main.add_txn())
        ed.clicked.connect(self.edit)
        rm.clicked.connect(self.remove)
        imp.clicked.connect(main.import_excel)
        self.count = QLabel()
        lay = QVBoxLayout(self)
        lay.addLayout(_row(self.type, self.search, self.only_bad))
        lay.addWidget(self.table)
        lay.addLayout(_row(add, ed, rm, None, imp))
        lay.addWidget(self.count)

    def reload(self):
        rows = self.main.result.rows if self.main.result else []
        tp = self.type.currentText()
        q = self.search.text().strip().lower()
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        n = 0
        for r in rows:
            x = r.txn
            if tp != "همه انواع" and x.type != tp:
                continue
            if self.only_bad.isChecked() and not r.status:
                continue
            if q and q not in f"{x.party} {r.name} {x.code}".lower():
                continue
            i = t.rowCount()
            t.insertRow(i)
            idc = NumItem(x.id)
            idc.setData(Qt.UserRole, x.id)
            t.setItem(i, 0, idc)
            for c, v in enumerate([x.date, x.type, x.party, x.code, r.name], 1):
                t.setItem(i, c, txt(v))
            t.setItem(i, 6, NumItem(x.qty, 3 if x.qty != int(x.qty) else 0))
            t.setItem(i, 7, NumItem(x.fee))
            amt = x.qty * x.fee
            tax = amt * self.main.vat_map.get(x.code, self.main.settings.tax_rate) if x.code else 0.0
            t.setItem(i, 8, NumItem(amt))
            t.setItem(i, 9, NumItem(tax))
            t.setItem(i, 10, NumItem(amt + tax))
            t.setItem(i, 11, txt(r.status))
            if r.status:
                paint_row(t, i, BAD)
            n += 1
        finish_table(t, 0)
        self.count.setText(f"{n} ردیف نمایش داده می‌شود از {len(rows)} تراکنش")

    def selected_ids(self) -> list[int]:
        rows = {i.row() for i in self.table.selectedItems()}
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def edit(self):
        ids = self.selected_ids()
        if ids:
            self.main.edit_txn(ids[0])

    def remove(self):
        ids = self.selected_ids()
        if ids and ask(self, "حذف", f"{len(ids)} تراکنش حذف شود؟"):
            self.main.db.delete_txns(ids)
            self.main.refresh()


# ------------------------------------------------------------------ کاردکس
class CardexTab(QWidget):
    HEAD = ["ردیف", "تاریخ", "نوع", "طرف حساب", "ورودی", "خروجی", "فی", "مبلغ", "موجودی",
            "میانگین بها", "ارزش موجودی", "انحراف", "وضعیت"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setMinimumWidth(320)
        self.combo.currentIndexChanged.connect(self.show_item)
        self.table = make_table(self.HEAD, stretch_col=3, sortable=False)
        self.foot = QLabel()
        lay = QVBoxLayout(self)
        lay.addLayout(_row(QLabel("کالا:"), self.combo, None))
        lay.addWidget(self.table)
        lay.addWidget(self.foot)

    def reload(self):
        cur = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for c, n in self.main.items:
            self.combo.addItem(f"{c} - {n}", c)
        i = self.combo.findData(cur) if cur else -1
        if i < 0:
            # اولین کالایی که تراکنش دارد
            used = [s.code for s in self.main.result.summary if s.n_txn] if self.main.result else []
            i = self.combo.findData(used[0]) if used else (0 if self.combo.count() else -1)
        self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)
        self.show_item()

    def show_item(self):
        code = self.combo.currentData()
        t = self.table
        t.setRowCount(0)
        if not code or not self.main.result:
            self.foot.setText("")
            return
        rows = self.main.result.cardex_for(code)
        for r in rows:
            x = r.txn
            i = t.rowCount()
            t.insertRow(i)
            t.setItem(i, 0, NumItem(r.rank))
            t.setItem(i, 1, txt(x.date))
            t.setItem(i, 2, txt(x.type))
            t.setItem(i, 3, txt(x.party))
            t.setItem(i, 4, NumItem(x.qty if x.type != SELL else 0))
            t.setItem(i, 5, NumItem(x.qty if x.type == SELL else 0))
            t.setItem(i, 6, NumItem(x.fee))
            t.setItem(i, 7, NumItem(r.amount))
            t.setItem(i, 8, NumItem(r.bal))
            t.setItem(i, 9, NumItem(r.avg))
            t.setItem(i, 10, NumItem(r.bal * r.avg))
            t.setItem(i, 11, NumItem(r.dev, pct=True) if r.dev is not None else txt(""))
            t.setItem(i, 12, txt(r.status))
            if r.status:
                paint_row(t, i, BAD)
        finish_table(t, None)
        if rows:
            last = rows[-1]
            self.foot.setText(f"{len(rows)} تراکنش — موجودی نهایی: {fmt_num(last.bal)} — "
                              f"میانگین بها: {fmt_num(last.avg)} — ارزش: {fmt_num(last.bal * last.avg)}")
        else:
            self.foot.setText("برای این کالا تراکنشی ثبت نشده است.")


# ------------------------------------------------------------------ خلاصه
class SummaryTab(QWidget):
    HEAD = ["کد", "نام کالا", "موجودی", "میانگین بها", "ارزش موجودی", "قیمت پیشنهادی فروش",
            "ارزش افزوده", "قیمت پیشنهادی با مالیات", "وضعیت", "دفعات منفی", "تعداد تراکنش"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.only = QCheckBox("فقط کالاهای دارای تراکنش")
        self.only.setChecked(True)
        self.only.toggled.connect(self.reload)
        self.table = make_table(self.HEAD, stretch_col=1)
        self.total = QLabel()
        self.total.setStyleSheet("font-weight:bold; font-size:14px;")
        lay = QVBoxLayout(self)
        lay.addLayout(_row(self.only, None))
        lay.addWidget(self.table)
        lay.addWidget(self.total)

    def reload(self):
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(0)
        res = self.main.result
        for s in (res.summary if res else []):
            if self.only.isChecked() and not s.n_txn:
                continue
            i = t.rowCount()
            t.insertRow(i)
            code = NumItem(int(s.code)) if s.code.isdigit() else txt(s.code)
            t.setItem(i, 0, code)
            t.setItem(i, 1, txt(s.name))
            t.setItem(i, 2, NumItem(s.qty))
            t.setItem(i, 3, NumItem(s.avg))
            t.setItem(i, 4, NumItem(s.value))
            t.setItem(i, 5, NumItem(s.price))
            t.setItem(i, 6, NumItem(s.vat, pct=True))
            t.setItem(i, 7, NumItem(s.price * (1 + s.vat)))
            t.setItem(i, 8, txt(s.status))
            t.setItem(i, 9, NumItem(s.neg_count))
            t.setItem(i, 10, NumItem(s.n_txn))
            if s.qty < 0:
                paint_row(t, i, BAD)
            elif s.n_txn and s.qty == 0:
                paint_row(t, i, WARN)
        finish_table(t, 0)
        if res:
            self.total.setText(f"ارزش کل موجودی انبار: {fmt_num(res.total_value)}      "
                               f"کالاهای دارای موجودی منفی: {res.negative_items}")


# ------------------------------------------------------------------ کنترل
class ControlTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignCenter)
        self.base_css = "padding:10px; font-weight:bold; font-size:14px; border-radius:6px;"
        self.banner.setStyleSheet(self.base_css)
        self.thr = QLabel()
        self.ctl = make_table(["کنترل", "مقدار مبنا", "مقدار کاردکس", "نتیجه"], stretch_col=0, sortable=False)
        self.ctl.setMaximumHeight(190)
        self.issues = make_table(["شناسه", "تاریخ", "نوع", "طرف حساب", "کالا", "مقدار", "فی",
                                  "میانگین قبل", "انحراف", "موجودی پس از ردیف", "وضعیت"], stretch_col=4)
        self.issues.doubleClicked.connect(self.edit)
        ed = QPushButton("ویرایش ردیف انتخاب‌شده")
        ed.clicked.connect(self.edit)
        lay = QVBoxLayout(self)
        lay.addWidget(self.banner)
        lay.addWidget(self.thr)
        lay.addWidget(self.ctl)
        lay.addWidget(QLabel("ردیف‌های مغایر (برای اصلاح، دوبار کلیک کنید):"))
        lay.addWidget(self.issues)
        lay.addLayout(_row(ed, None))

    def reload(self):
        res, s = self.main.result, self.main.settings
        if not res:
            return
        self.thr.setText(f"آستانه‌ها (از تب «تنظیمات» قابل تغییرند): انحراف نرخ خرید ±{s.dev_threshold * 100:g}٪ — "
                         f"حداقل سود فروش {s.min_margin * 100:g}٪ نسبت به میانگین بها")
        bad_ctl = sum(1 for c in res.controls if not c.ok)
        if res.all_ok:
            self.banner.setText("✔ همه کنترل‌ها سالم است — مغایرتی یافت نشد")
            self.banner.setStyleSheet(self.base_css + "background:#d9f2d9; color:#1b5e20;")
        else:
            self.banner.setText(f"⚠ {len(res.issues)} ردیف مغایر و {bad_ctl} کنترل تطبیقی ناموفق")
            self.banner.setStyleSheet(self.base_css + "background:#fde0dd; color:#b71c1c;")
        t = self.ctl
        t.setRowCount(0)
        for c in res.controls:
            i = t.rowCount()
            t.insertRow(i)
            t.setItem(i, 0, txt(c.name))
            t.setItem(i, 1, NumItem(c.expected))
            t.setItem(i, 2, NumItem(c.actual))
            t.setItem(i, 3, txt("✔" if c.ok else "✘ مغایرت"))
            paint_row(t, i, GOOD if c.ok else BAD)
        t = self.issues
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for r in res.issues:
            x = r.txn
            i = t.rowCount()
            t.insertRow(i)
            idc = NumItem(x.id)
            idc.setData(Qt.UserRole, x.id)
            t.setItem(i, 0, idc)
            t.setItem(i, 1, txt(x.date))
            t.setItem(i, 2, txt(x.type))
            t.setItem(i, 3, txt(x.party))
            t.setItem(i, 4, txt(r.name))
            t.setItem(i, 5, NumItem(x.qty))
            t.setItem(i, 6, NumItem(x.fee))
            t.setItem(i, 7, NumItem(r.prev_avg))
            t.setItem(i, 8, NumItem(r.dev, pct=True) if r.dev is not None else txt(""))
            t.setItem(i, 9, NumItem(r.bal))
            t.setItem(i, 10, txt(r.status))
            paint_row(t, i, BAD)
        finish_table(t, 0)

    def edit(self):
        rows = {i.row() for i in self.issues.selectedItems()}
        if rows:
            self.main.edit_txn(self.issues.item(min(rows), 0).data(Qt.UserRole))


# ------------------------------------------------------------------ تخصیص کالا
class AllocTab(QWidget):
    HEAD = ["ردیف", "تاریخ", "خریدار", "کد", "نام کالا", "مقدار", "فی", "مبلغ", "مالیات", "جمع",
            "مبلغ فاکتور", "اختلاف", "وضعیت", "میانگین بها در تاریخ فروش"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.out: list[allocation.AllocLine] = []
        self.plan = make_table(["تاریخ", "خریدار", "کالا (فقط فاکتور رسمی)", "مقدار (رسمی)", "فی (رسمی)",
                                "مبلغ نهایی فاکتور (با مالیات)"], stretch_col=1, sortable=False)
        self.plan.setEditTriggers(self.plan.EditTrigger.DoubleClicked | self.plan.EditTrigger.EditKeyPressed
                                  | self.plan.EditTrigger.AnyKeyPressed)
        for col, wd in ((0, 110), (2, 200), (3, 120), (4, 130), (5, 220)):
            self.plan.setColumnWidth(col, wd)
        self.plan.itemChanged.connect(self._plan_changed)
        add, rm, paste, clear = (QPushButton("＋ ردیف"), QPushButton("حذف ردیف"),
                                 QPushButton("چسباندن از کلیپ‌بورد (اکسل)"), QPushButton("پاک کردن طرح"))
        add.clicked.connect(lambda: self._add_row("", "", ""))
        rm.clicked.connect(self.remove_rows)
        paste.clicked.connect(self.paste)
        clear.clicked.connect(self.clear_plan)
        run = QPushButton("▶ اجرای تخصیص")
        run.setStyleSheet("font-weight:bold; padding:6px 18px;")
        run.clicked.connect(self.run)
        self.res = make_table(self.HEAD, stretch_col=4, sortable=False)
        self.note = QLabel()
        reg, exp = QPushButton("ثبت نتیجه به‌عنوان فروش در کاردکس"), QPushButton("خروجی اکسل تخصیص")
        reg.clicked.connect(self.register)
        exp.clicked.connect(self.export)
        hint = QLabel("ردیف عادی: فقط «مبلغ نهایی فاکتور (با مالیات)» را بنویسید؛ برنامه کالا و مقدار را بر پایه‌ی "
                      "موجودی و میانگین بهای همان تاریخ فروش (یا موجودی نهایی، طبق تنظیمات) تعیین می‌کند.\n"
                      "فاکتور رسمی: کالا، مقدار و «فی» (یا به‌جای فی، مبلغ نهایی با مالیات) را پر کنید؛ همین مقدار و مبلغ "
                      "دقیقاً ثبت می‌شود و موجودی‌اش پیش از ردیف‌های عادی کنار گذاشته می‌شود. ستون‌ها را "
                      "(تاریخ، خریدار، کالا، مقدار، فی، مبلغ) می‌توانید مستقیم از اکسل کپی و اینجا بچسبانید.")
        hint.setWordWrap(True)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(hint)
        tl.addWidget(self.plan)
        tl.addLayout(_row(add, rm, paste, clear, None, run))
        bot = QWidget()
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.res)
        bl.addWidget(self.note)
        bl.addLayout(_row(reg, exp, None))
        sp = QSplitter(Qt.Vertical)
        sp.addWidget(top)
        sp.addWidget(bot)
        lay = QVBoxLayout(self)
        lay.addWidget(sp)

    # --- طرح
    def _add_row(self, d, b, a="", item="", qty="", fee="", save=True):
        t = self.plan
        t.blockSignals(True)
        i = t.rowCount()
        t.insertRow(i)
        for c, v in enumerate((d, b, item, qty, fee, a)):
            t.setItem(i, c, txt(v, True))
        t.blockSignals(False)
        if save:
            self.save_plan()

    def load_plan(self):
        t = self.plan
        t.blockSignals(True)
        t.setRowCount(0)
        t.blockSignals(False)
        for d, b, a, item, q, f in self.main.db.plan(self.main.cid):
            self._add_row(d, b, fmt_num(a) if a else "", item or "", f"{q:g}" if q else "",
                          fmt_num(f) if f else "", save=False)
        self.out = []
        self.res.setRowCount(0)
        self.note.setText("")

    def plan_rows(self) -> list[tuple]:
        """(تاریخ، خریدار، مبلغ نهایی، کالا، مقدار، فی) از جدول."""
        t = self.plan
        rows = []
        for r in range(t.rowCount()):
            g = lambda c: (t.item(r, c).text() if t.item(r, c) else "")
            if not any(g(c).strip() for c in range(6)):
                continue
            rows.append((g(0).strip(), clean_display(g(1)), parse_number(g(5)), clean_display(g(2)),
                         parse_number(g(3)), parse_number(g(4))))
        return rows

    def save_plan(self):
        self.main.db.save_plan(self.main.cid, [(d, b, a or 0.0, it, q, f) for d, b, a, it, q, f in self.plan_rows()])

    def _plan_changed(self, it):
        self.save_plan()

    def remove_rows(self):
        for r in sorted({i.row() for i in self.plan.selectedItems()}, reverse=True):
            self.plan.removeRow(r)
        self.save_plan()

    def clear_plan(self):
        if self.plan.rowCount() and ask(self, "پاک کردن", "تمام ردیف‌های طرح پاک شود؟"):
            self.plan.setRowCount(0)
            self.save_plan()

    def paste(self):
        text = QGuiApplication.clipboard().text()
        n = 0
        for line in text.splitlines():
            cols = [c.strip() for c in line.split("\t")]
            if not any(cols):
                continue
            if len(cols) >= 5:                         # تاریخ، خریدار، کالا، مقدار، فی[، مبلغ]
                d, b, item, q, f = cols[:5]
                a = cols[5] if len(cols) > 5 else ""
                if all(parse_number(x) is None for x in (q, f, a)):
                    continue                           # سطر عنوان
                self._add_row(norm_date(d) or d, b, fmt_num(parse_number(a)) if parse_number(a) else "", item,
                              f"{parse_number(q):g}" if parse_number(q) else "",
                              fmt_num(parse_number(f)) if parse_number(f) is not None else "", save=False)
                n += 1
                continue
            amount = parse_number(cols[-1])
            if amount is None:
                continue                               # سطر عنوان
            rest = cols[:-1]
            date = next((c for c in rest if norm_date(c)), "")
            buyer = next((c for c in rest if c and c != date), "")
            self._add_row(norm_date(date) or date, buyer, fmt_num(amount), save=False)
            n += 1
        self.save_plan()
        info(self, "چسباندن", f"{n} ردیف اضافه شد." if n else "داده‌ی قابل‌فهمی در کلیپ‌بورد پیدا نشد.")

    # --- اجرا
    def _resolve_item(self, text: str) -> str:
        t = norm_text(text)
        if not t:
            return ""
        for c, n in self.main.items:
            if t in (norm_text(c), norm_text(n), norm_text(f"{c} - {n}")):
                return c
        return ""

    def run(self):
        plan, problems = [], []
        for i, (d, b, a, item, q, f) in enumerate(self.plan_rows(), 1):
            date = norm_date(d) or d
            if item or q or f:                                   # فاکتور رسمی
                code = self._resolve_item(item)
                if not code:
                    problems.append(f"ردیف {i}: کالا در کدینگ پیدا نشد")
                elif not q or q <= 0:
                    problems.append(f"ردیف {i}: مقدار فاکتور رسمی لازم است")
                else:
                    pr = PlanRow(date, b, a or 0.0, code, q, f)
                    rate = self.main.vat_map.get(code, self.main.settings.tax_rate)
                    if allocation.official_fee(pr, rate) is None:
                        problems.append(f"ردیف {i}: فی یا مبلغ نهایی فاکتور رسمی لازم است")
                    else:
                        plan.append(pr)
                        continue
                plan.append(PlanRow(date, b, 0.0))                # جای ردیف حفظ می‌شود تا شماره‌ها با جدول یکی بماند
            elif a is None or a <= 0:
                problems.append(f"ردیف {i}: مبلغ معتبر نیست")
                plan.append(PlanRow(date, b, 0.0))
            else:
                plan.append(PlanRow(date, b, a))
        if problems:
            warn(self, "ردیف‌های نادیده‌گرفته‌شده", "\n".join(problems))
        if not any(p.amount > 0 or p.is_official for p in plan):
            return
        st = self.main.settings
        if st.dated_allocation:
            txns = [r.txn for r in self.main.result.rows if r.rank]
            self.out = allocation.allocate_dated(plan, txns, self.main.items, st, self.main.vat_map)
        else:
            self.out = allocation.allocate(plan, self.main.result.summary, st)
        t = self.res
        t.setRowCount(0)
        for a in self.out:
            i = t.rowCount()
            t.insertRow(i)
            vals = [NumItem(a.plan_index), txt(a.date), txt(a.buyer), txt(a.code), txt(a.name),
                    NumItem(a.qty), NumItem(a.price), NumItem(a.amount), NumItem(a.tax),
                    NumItem(a.gross), NumItem(a.plan_amount), NumItem(a.diff), txt(a.status),
                    NumItem(a.avg)]
            for c, it in enumerate(vals):
                t.setItem(i, c, it)
            if a.status in ("بدون موجودی", "تاریخ نامعتبر"):
                paint_row(t, i, BAD)
            elif a.status in ("جزئی", allocation.OFFICIAL_SHORT):
                paint_row(t, i, WARN)
            elif a.status == allocation.OFFICIAL:
                paint_row(t, i, GOOD)
        finish_table(t, None)
        cnt = lambda *st_: len({a.plan_index for a in self.out if a.status in st_})
        self.note.setText(f"عادی کامل: {cnt('کامل')}    جزئی: {cnt('جزئی')}    بدون موجودی: {cnt('بدون موجودی', 'تاریخ نامعتبر')}    "
                          f"فاکتور رسمی: {cnt(allocation.OFFICIAL, allocation.OFFICIAL_SHORT)} "
                          f"(موجودی ناکافی: {cnt(allocation.OFFICIAL_SHORT)})    "
                          f"جمع مبلغ تخصیص‌یافته: {fmt_num(sum(a.gross for a in self.out))}")

    def register(self):
        lines = [a for a in self.out if a.code and a.qty > 0]
        if not lines:
            warn(self, "ثبت", "ابتدا تخصیص را اجرا کنید.")
            return
        bad_dates = [a.plan_index for a in lines if not norm_date(a.date)]
        if bad_dates:
            warn(self, "تاریخ نامعتبر", "برای ثبت فروش، تاریخ این ردیف‌های طرح باید شمسی و معتبر باشد: "
                 + "، ".join(map(str, sorted(set(bad_dates)))))
            return
        short = [a for a in lines if a.status == allocation.OFFICIAL_SHORT]
        extra = (f"\n\n⚠ {len(short)} ردیف فاکتور رسمی موجودی کافی ندارد. فاکتور رسمی با همان مقدار ثبت می‌شود "
                 "و در تب «کنترل» به‌صورت موجودی منفی دیده می‌شود (باید خرید/موجودی اصلاح شود).") if short else ""
        if not ask(self, "ثبت فروش", f"{len(lines)} ردیف فروش به تراکنش‌های این شرکت اضافه شود؟\n"
                                      "(پس از ثبت، طرح فعلی پاک می‌شود تا دوباره ثبت نشود.)" + extra, "ثبت", "انصراف"):
            return
        txns = [Txn(date=norm_date(a.date), type=SELL, code=a.code, qty=a.qty, fee=a.price, party=a.buyer)
                for a in lines]
        with self.main.db.undo.group(self.main.cid, "ثبت فروش از تخصیص", ("txns", "plan")):
            self.main.db.add_txns(self.main.cid, txns)
            self.main.db.save_plan(self.main.cid, [])
        self.load_plan()
        self.main.refresh()
        info(self, "ثبت شد", f"{len(txns)} ردیف فروش ثبت شد. وضعیت کنترل را در تب «کنترل» ببینید.")

    def export(self):
        if not self.out:
            warn(self, "خروجی", "ابتدا تخصیص را اجرا کنید.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره", f"{self.main.company_name()}_تخصیص.xlsx", "Excel (*.xlsx)")
        if path:
            export_report(path, self.main.company_name(), self.main.result, self.out)
            info(self, "ذخیره شد", path)


# ------------------------------------------------------------------ تنظیمات
class SettingsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        def dsb(maxv=100.0, step=0.5, suf="٪"):
            w = QDoubleSpinBox()
            w.setRange(0, maxv)
            w.setSingleStep(step)
            w.setDecimals(2)
            w.setSuffix(suf)
            return w
        self.tax, self.dev, self.margin, self.markup = dsb(), dsb(), dsb(), dsb()
        self.round = QSpinBox()
        self.round.setRange(1, 1_000_000)
        self.qround = QComboBox()
        self.qround.addItem("گرد به بالا (مثل ماکرو)", "ceil")
        self.qround.addItem("نزدیک‌ترین عدد", "nearest")
        self.qround.addItem("گرد به پایین", "floor")
        self.split = QCheckBox("اگر موجودی یک کالا کافی نبود، باقیمانده را از کالای بعدی تأمین کن")
        self.dated = QCheckBox("تخصیص با موجودی و میانگین بهای «همان تاریخ فروش» (تاریخ‌های خرید را لحاظ می‌کند)")
        form = QFormLayout()
        form.addRow("مالیات و عوارض پیش‌فرض (برای کالاهای بدون نرخ اختصاصی):", self.tax)
        form.addRow("آستانه انحراف نرخ خرید (±):", self.dev)
        form.addRow("حداقل سود فروش نسبت به میانگین بها:", self.margin)
        form.addRow("درصد سود قیمت پیشنهادی فروش:", self.markup)
        form.addRow("گرد کردن قیمت پیشنهادی به مضرب:", self.round)
        form.addRow("گرد کردن مقدار در تخصیص:", self.qround)
        form.addRow("", self.split)
        form.addRow("", self.dated)
        save = QPushButton("ذخیره‌ی تنظیمات این شرکت")
        save.clicked.connect(self.save)
        self.path = QLabel()
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box = QGroupBox("تنظیمات شرکت")
        box.setLayout(form)
        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addLayout(_row(save, None))
        lay.addStretch(1)
        lay.addWidget(self.path)

    def reload(self):
        s = self.main.settings
        self.tax.setValue(s.tax_rate * 100)
        self.dev.setValue(s.dev_threshold * 100)
        self.margin.setValue(s.min_margin * 100)
        self.markup.setValue(s.markup * 100)
        self.round.setValue(int(s.round_to))
        self.qround.setCurrentIndex(max(0, self.qround.findData(s.qty_rounding)))
        self.split.setChecked(s.allow_split)
        self.dated.setChecked(s.dated_allocation)
        self.path.setText(f"مسیر پایگاه داده: {self.main.db.path}")

    def save(self):
        s = Settings(tax_rate=self.tax.value() / 100, dev_threshold=self.dev.value() / 100,
                     min_margin=self.margin.value() / 100, markup=self.markup.value() / 100,
                     round_to=float(self.round.value()), qty_rounding=self.qround.currentData(),
                     allow_split=self.split.isChecked(), dated_allocation=self.dated.isChecked())
        self.main.db.save_settings(self.main.cid, s)
        self.main.refresh()
        info(self, "ذخیره شد", "تنظیمات ذخیره و محاسبات به‌روز شد.")
