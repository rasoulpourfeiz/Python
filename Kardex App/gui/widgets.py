"""ابزارها و دیالوگ‌های مشترک رابط گرافیکی."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDialog,
                               QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QRadioButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from core import maintenance
from core.engine import ALL_TYPES, Txn
from core.textutil import clean_display, fmt_num, norm_code, norm_date, norm_text, parse_number

BAD = QColor("#fde9e7")
WARN = QColor("#fff4ce")
GOOD = QColor("#e3f4e1")
ALIGN_NUM = Qt.AlignRight | Qt.AlignVCenter
ALIGN_TXT = Qt.AlignRight | Qt.AlignVCenter


class NumItem(QTableWidgetItem):
    """سلول عددی با مرتب‌سازی درست."""

    def __init__(self, value, dec: int = 0, pct: bool = False):
        if value is None or value == "":
            text = ""
        elif pct:
            text = f"{float(value) * 100:.2f}%"
        else:
            text = fmt_num(value, dec)
        super().__init__(text)
        self._v = float(value) if isinstance(value, (int, float)) else float("-inf")
        self.setTextAlignment(ALIGN_NUM)

    def __lt__(self, other):
        if isinstance(other, NumItem):
            return self._v < other._v
        return super().__lt__(other)


def txt(s, editable: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem("" if s is None else str(s))
    it.setTextAlignment(ALIGN_TXT)
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


def make_table(headers: list[str], stretch_col: int | None = None, sortable: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(stretch_col is None)
    t.setSortingEnabled(sortable)
    if stretch_col is not None:
        t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


def finish_table(t: QTableWidget, sort_col: int | None = 0):
    """پس از پر شدن جدول: عرض ستون‌ها و ترتیب پیش‌فرض."""
    if sort_col is not None:
        t.setSortingEnabled(True)
        t.sortByColumn(sort_col, Qt.AscendingOrder)
    hh = t.horizontalHeader()
    for c in range(t.columnCount()):
        if hh.sectionResizeMode(c) != QHeaderView.Stretch:
            t.resizeColumnToContents(c)
            t.setColumnWidth(c, min(max(t.columnWidth(c) + 14, 70), 320))


def paint_row(t: QTableWidget, r: int, color: QColor | None):
    if color is None:
        return
    for c in range(t.columnCount()):
        it = t.item(r, c)
        if it:
            it.setBackground(color)


def ask(parent, title: str, text: str, yes: str = "بله", no: str = "خیر") -> bool:
    b = QMessageBox(QMessageBox.Question, title, text, parent=parent)
    y = b.addButton(yes, QMessageBox.YesRole)
    b.addButton(no, QMessageBox.NoRole)
    b.exec()
    return b.clickedButton() is y


def info(parent, title: str, text: str):
    b = QMessageBox(QMessageBox.Information, title, text, parent=parent)
    b.addButton("تأیید", QMessageBox.AcceptRole)
    b.exec()


def warn(parent, title: str, text: str):
    b = QMessageBox(QMessageBox.Warning, title, text, parent=parent)
    b.addButton("تأیید", QMessageBox.AcceptRole)
    b.exec()


def buttons(dlg: QDialog, ok: str = "تأیید", cancel: str = "انصراف") -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(ok)
    bb.button(QDialogButtonBox.Cancel).setText(cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class ItemDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("کالای جدید")
        self.code = QLineEdit()
        self.name = QLineEdit()
        self.vat_edit = QLineEdit()
        self.vat_edit.setPlaceholderText("خالی = نرخ پیش‌فرض شرکت؛ مثلاً 0 یا 10 یا 16")
        form = QFormLayout(self)
        form.addRow("کد کالا:", self.code)
        form.addRow("نام کالا:", self.name)
        form.addRow("نرخ ارزش افزوده (٪):", self.vat_edit)
        form.addRow(buttons(self))
        self.setMinimumWidth(400)

    def vat(self) -> float | None:
        x = parse_number(self.vat_edit.text())
        return None if x is None else x / 100

    def accept(self):
        if not norm_code(self.code.text()) or not clean_display(self.name.text()):
            warn(self, "خطا", "کد و نام کالا را وارد کنید.")
            return
        t = self.vat_edit.text().strip()
        if t and (parse_number(t) is None or not 0 <= parse_number(t) <= 100):
            warn(self, "خطا", "نرخ ارزش افزوده باید عددی بین 0 و 100 باشد.")
            return
        super().accept()


class TxnDialog(QDialog):
    """افزودن/ویرایش تراکنش."""

    def __init__(self, items: list[tuple[str, str]], txn: Txn | None = None, parent=None,
                 default_type: str = "فروش"):
        super().__init__(parent)
        self.setWindowTitle("ویرایش تراکنش" if txn else "تراکنش جدید")
        self.items = items
        self.date = QLineEdit(txn.date if txn else "")
        self.date.setPlaceholderText("مثال: 1405/07/26")
        self.type = QComboBox()
        self.type.addItems(ALL_TYPES)
        self.type.setCurrentText(txn.type if txn else default_type)
        self.party = QLineEdit(txn.party if txn else "")
        self.item = QComboBox()
        self.item.setEditable(True)
        self.item.setInsertPolicy(QComboBox.NoInsert)
        for c, n in items:
            self.item.addItem(f"{c} - {n}", c)
        comp = QCompleter([f"{c} - {n}" for c, n in items], self.item)
        comp.setFilterMode(Qt.MatchContains)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.item.setCompleter(comp)
        if txn and txn.code:
            i = self.item.findData(txn.code)
            self.item.setCurrentIndex(i)
        else:
            self.item.setCurrentIndex(-1)
            self.item.setEditText(txn.raw_name if txn else "")
        self.qty = QLineEdit("" if not txn else f"{txn.qty:g}")
        self.fee = QLineEdit("" if not txn else f"{txn.fee:.6g}" if txn.fee != int(txn.fee) else f"{int(txn.fee)}")
        form = QFormLayout(self)
        form.addRow("تاریخ (شمسی):", self.date)
        form.addRow("نوع:", self.type)
        form.addRow("طرف حساب:", self.party)
        form.addRow("کالا:", self.item)
        form.addRow("مقدار:", self.qty)
        form.addRow("فی (قیمت واحد):", self.fee)
        form.addRow(buttons(self))
        self.setMinimumWidth(420)
        self._result: Txn | None = None

    def _resolve_code(self) -> str:
        data = self.item.currentData()
        text = self.item.currentText()
        if data and text == self.item.itemText(self.item.currentIndex()):
            return data
        t = norm_text(text)
        for c, n in self.items:
            if t in (norm_text(f"{c} - {n}"), norm_text(n), norm_text(c)):
                return c
        return ""

    def accept(self):
        d = norm_date(self.date.text())
        q, f = parse_number(self.qty.text()), parse_number(self.fee.text())
        code = self._resolve_code()
        if not d:
            warn(self, "خطا", "تاریخ شمسی معتبر نیست (مثال: 1405/07/26).")
        elif not code:
            warn(self, "خطا", "کالا را از فهرست کدینگ انتخاب کنید.")
        elif not q or q <= 0:
            warn(self, "خطا", "مقدار باید بزرگ‌تر از صفر باشد.")
        elif f is None or f <= 0:
            warn(self, "خطا", "فی باید بزرگ‌تر از صفر باشد.")
        else:
            self._result = Txn(date=d, type=self.type.currentText(), code=code, qty=q, fee=f,
                               party=clean_display(self.party.text()))
            super().accept()

    def txn(self) -> Txn:
        assert self._result is not None
        return self._result


class ImportDialog(QDialog):
    def __init__(self, sheets, has_txns: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ورود از اکسل / CSV")
        self.sheets = sheets
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("شیت‌هایی که باید وارد شوند را انتخاب کنید:"))
        self.list = QListWidget()
        for s in sheets:
            what = "کدینگ کالا" if s.kind == "items" else "تراکنش‌ها"
            it = QListWidgetItem(f"{s.name} — {what} ({len(s.rows)} ردیف)")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if s.default_checked else Qt.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        self.append = QRadioButton("افزودن به تراکنش‌های موجود")
        self.replace = QRadioButton("جایگزینی: ابتدا تمام تراکنش‌های قبلی این شرکت حذف شود (دوره‌ی جدید)")
        self.replace_items = QCheckBox("کدینگ کالای قبلی هم حذف و از فایل جدید ساخته شود")
        self.replace_items.setEnabled(False)
        self.replace.toggled.connect(self.replace_items.setEnabled)
        self.append.setChecked(True)
        if has_txns:
            lay.addWidget(self.append)
            lay.addWidget(self.replace)
            lay.addWidget(self.replace_items)
        lay.addWidget(QLabel("توجه: شیت‌های ساخته‌شده از روی خرید/فروش (مثل «ادغام» و «کاردکس زنده») وارد نمی‌شوند."))
        lay.addWidget(buttons(self, "ورود داده"))
        self.setMinimumWidth(520)

    def selected(self):
        return [s for i, s in enumerate(self.sheets) if self.list.item(i).checkState() == Qt.Checked]

    def replace_txns(self) -> bool:
        return self.replace.isChecked()

    def replace_coding(self) -> bool:
        return self.replace.isChecked() and self.replace_items.isChecked()


class ClearDialog(QDialog):
    """حذف اطلاعات قبلی یک شرکت."""

    def __init__(self, db, cid: int, company: str, parent=None):
        super().__init__(parent)
        self.db, self.cid = db, cid
        self.setWindowTitle(f"حذف اطلاعات قبلی — {company}")
        self.txns = QCheckBox("حذف تراکنش‌ها (اول دوره، خرید، فروش)")
        self.txns.setChecked(True)
        self.until = QLineEdit()
        self.until.setPlaceholderText("خالی = همه‌ی تراکنش‌ها؛ یا مثلاً 1405/12/29")
        self.carry = QCheckBox("موجودی و میانگین بهای پایان دوره را به‌عنوان «اول دوره» منتقل کن")
        self.plan = QCheckBox("پاک کردن طرح تخصیص")
        self.plan.setChecked(True)
        self.items = QCheckBox("حذف کدینگ کالا (فقط وقتی همه‌ی تراکنش‌ها حذف می‌شوند)")
        self.count = QLabel()
        self.count.setStyleSheet("font-weight:bold;")
        form = QFormLayout()
        form.addRow("حذف تراکنش‌های تا تاریخ (شامل):", self.until)
        lay = QVBoxLayout(self)
        lay.addWidget(self.txns)
        lay.addLayout(form)
        lay.addWidget(self.carry)
        lay.addWidget(self.plan)
        lay.addWidget(self.items)
        lay.addWidget(self.count)
        note = QLabel("قبل از حذف، به‌صورت خودکار یک نسخه‌ی پشتیبان ساخته می‌شود "
                      "(از منوی فایل ← «بازیابی از پشتیبان» قابل برگشت است).\n"
                      "اگر فایل دوره‌ی جدید خودش «اول دوره» دارد، گزینه‌ی انتقال موجودی را روشن نکنید تا دوبار شمرده نشود.")
        note.setWordWrap(True)
        lay.addWidget(note)
        bb = buttons(self, "حذف", "انصراف")
        bb.button(QDialogButtonBox.Ok).setStyleSheet("color:#b71c1c; font-weight:bold;")
        lay.addWidget(bb)
        for w in (self.txns, self.carry, self.plan, self.items):
            w.toggled.connect(self._sync)
        self.until.textChanged.connect(self._sync)
        self.setMinimumWidth(520)
        self._sync()

    def options(self) -> maintenance.ClearOptions:
        return maintenance.ClearOptions(txns=self.txns.isChecked(), until=self.until.text().strip(),
                                        carry=self.carry.isChecked(), plan=self.plan.isChecked(),
                                        items=self.items.isChecked())

    def _sync(self, *_):
        has_date = bool(self.until.text().strip())
        self.until.setEnabled(self.txns.isChecked() and not self.items.isChecked())
        self.carry.setEnabled(self.txns.isChecked() and has_date)
        if not self.carry.isEnabled():
            self.carry.setChecked(False)
        self.items.setEnabled(self.txns.isChecked() and not has_date)
        if not self.items.isEnabled():
            self.items.setChecked(False)
        o = self.options()
        n = maintenance.preview_count(self.db, self.cid, o) if not (o.until and not norm_date(o.until)) else 0
        total = len(self.db.txns(self.cid))
        self.count.setText(f"{n} تراکنش از {total} تراکنش حذف می‌شود." if o.txns else "تراکنش‌ها حذف نمی‌شوند.")

    def accept(self):
        err = maintenance.validate(self.options())
        if err:
            warn(self, "خطا", err)
            return
        if not (self.txns.isChecked() or self.plan.isChecked() or self.items.isChecked()):
            warn(self, "خطا", "حداقل یک مورد را برای حذف انتخاب کنید.")
            return
        super().accept()
