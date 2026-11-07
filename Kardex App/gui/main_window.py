"""پنجره‌ی اصلی."""
from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from core import engine, importer, maintenance
from core.db import Database
from core.engine import Settings
from core.exporter import export_report, export_template
from core.textutil import fmt_num
from .tabs import (AllocTab, CardexTab, ControlTab, ItemsTab, SettingsTab, SummaryTab, TxnTab)
from .widgets import ClearDialog, ImportDialog, TxnDialog, ask, info, warn

warnings.filterwarnings("ignore", message=".*Data Validation extension.*")


def ask_text(parent, title: str, label: str, text: str = "") -> str | None:
    d = QInputDialog(parent)
    d.setWindowTitle(title)
    d.setLabelText(label)
    d.setTextValue(text)
    d.setOkButtonText("تأیید")
    d.setCancelButtonText("انصراف")
    d.setMinimumWidth(380)
    return d.textValue().strip() if d.exec() and d.textValue().strip() else None


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.cid = 0
        self.items: list[tuple[str, str]] = []
        self.settings = Settings()
        self.vat_map: dict[str, float] = {}
        self.result: engine.Result | None = None
        self.setWindowTitle("کاردکس انبار — میانگین موزون متحرک")
        self.resize(1280, 780)

        # ---- نوار بالا
        self.company = QComboBox()
        self.company.setMinimumWidth(240)
        self.company.currentIndexChanged.connect(self._company_changed)
        b_new, b_ren, b_del = QPushButton("شرکت جدید"), QPushButton("تغییر نام"), QPushButton("حذف شرکت")
        b_imp, b_exp, b_bak = QPushButton("ورود از اکسل…"), QPushButton("خروجی گزارش اکسل"), QPushButton("پشتیبان‌گیری")
        b_clr = QPushButton("حذف اطلاعات قبلی…")
        b_clr.clicked.connect(self.clear_data)
        b_new.clicked.connect(self.new_company)
        b_ren.clicked.connect(self.rename_company)
        b_del.clicked.connect(self.delete_company)
        b_imp.clicked.connect(self.import_excel)
        b_exp.clicked.connect(self.export_excel)
        b_bak.clicked.connect(self.backup)
        # ---- Undo / Redo
        self.act_undo = QAction("بازگردانی (Undo)", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.do_undo)
        self.act_redo = QAction("ازنو (Redo)", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.do_redo)
        self.addAction(self.act_undo)
        self.addAction(self.act_redo)
        self.b_undo, self.b_redo = QPushButton("↶ بازگردانی"), QPushButton("↷ ازنو")
        self.b_undo.clicked.connect(self.act_undo.trigger)
        self.b_redo.clicked.connect(self.act_redo.trigger)
        self.db.undo.on_change = self.update_undo_state

        top = QHBoxLayout()
        top.addWidget(QLabel("شرکت:"))
        top.addWidget(self.company)
        for b in (b_new, b_ren, b_del):
            top.addWidget(b)
        top.addSpacing(16)
        top.addWidget(self.b_undo)
        top.addWidget(self.b_redo)
        top.addStretch(1)
        for b in (b_clr, b_imp, b_exp, b_bak):
            top.addWidget(b)

        # ---- تب‌ها
        self.t_items, self.t_txn = ItemsTab(self), TxnTab(self)
        self.t_cardex, self.t_sum = CardexTab(self), SummaryTab(self)
        self.t_ctl, self.t_alloc, self.t_set = ControlTab(self), AllocTab(self), SettingsTab(self)
        self.tabs = QTabWidget()
        for w, name in ((self.t_sum, "خلاصه موجودی و نرخ"), (self.t_txn, "تراکنش‌ها"),
                        (self.t_cardex, "کاردکس کالا"), (self.t_ctl, "کنترل"),
                        (self.t_alloc, "تخصیص کالا"), (self.t_items, "کدینگ کالا"),
                        (self.t_set, "تنظیمات")):
            self.tabs.addTab(w, name)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.status = self.statusBar()

        em = self.menuBar().addMenu("ویرایش")
        em.addAction(self.act_undo)
        em.addAction(self.act_redo)
        m = self.menuBar().addMenu("فایل")
        for text, fn in (("ورود از اکسل / CSV…", self.import_excel), ("حذف اطلاعات قبلی…", self.clear_data),
                         ("خروجی گزارش اکسل…", self.export_excel),
                         ("ساخت فایل نمونه‌ی ورود داده…", self.save_template),
                         ("باز کردن پوشه‌ی داده", self.open_data_dir), ("پشتیبان‌گیری…", self.backup),
                         ("بازیابی از پشتیبان…", self.restore)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)
        m.addSeparator()
        q = QAction("خروج", self)
        q.triggered.connect(self.close)
        m.addAction(q)

        self.reload_companies()
        self.update_undo_state()

    # ------------------------------------------------------------ Undo / Redo
    def update_undo_state(self):
        u = self.db.undo
        for act, btn, stack, label, name in ((self.act_undo, self.b_undo, u.undo_stack, u.undo_label, "بازگردانی"),
                                              (self.act_redo, self.b_redo, u.redo_stack, u.redo_label, "ازنو")):
            act.setEnabled(bool(stack))
            btn.setEnabled(bool(stack))
            act.setText(f"{name}: {label}" if label else f"{name} ({'Undo' if name == 'بازگردانی' else 'Redo'})")
            btn.setToolTip(f"{name}: {label}" if label else "چیزی برای " + name + " نیست")

    def _after_undo(self, result, msg: str):
        label, cid = result
        ids = [c for c, _ in self.db.companies()]
        self.reload_companies(cid if cid in ids else (self.cid if self.cid in ids else None))
        self.status.showMessage(f"{msg}: {label}", 8000)

    def do_undo(self):
        r = self.db.undo.undo()
        if r:
            self._after_undo(r, "بازگردانی شد")

    def do_redo(self):
        r = self.db.undo.redo()
        if r:
            self._after_undo(r, "ازنو انجام شد")

    # ------------------------------------------------------------ شرکت‌ها
    def company_name(self) -> str:
        return self.company.currentText() or "شرکت"

    def reload_companies(self, select_id: int | None = None):
        self.company.blockSignals(True)
        self.company.clear()
        for cid, name in self.db.companies():
            self.company.addItem(name, cid)
        i = self.company.findData(select_id) if select_id else 0
        self.company.setCurrentIndex(max(i, 0))
        self.company.blockSignals(False)
        self.cid = self.company.currentData() or 0
        self.on_company_loaded()

    def _company_changed(self):
        self.cid = self.company.currentData() or 0
        self.on_company_loaded()

    def on_company_loaded(self):
        self.t_alloc.load_plan()
        self.refresh()

    def new_company(self):
        name = ask_text(self, "شرکت جدید", "نام شرکت:")
        if not name:
            return
        try:
            cid = self.db.add_company(name)
        except Exception as e:
            warn(self, "خطا", f"ثبت شرکت ممکن نشد (نام تکراری؟)\n{e}")
            return
        self.reload_companies(cid)
        self.tabs.setCurrentWidget(self.t_items)
        info(self, "شرکت ساخته شد",
             "کدینگ کالای این شرکت خالی است. کالاها را در تب «کدینگ کالا» اضافه کنید "
             "یا با «ورود از اکسل» کدینگ و تراکنش‌ها را بارگذاری کنید.")

    def rename_company(self):
        if not self.cid:
            return
        name = ask_text(self, "تغییر نام", "نام جدید:", self.company_name())
        if name:
            try:
                self.db.rename_company(self.cid, name)
            except Exception as e:
                warn(self, "خطا", str(e))
                return
            self.reload_companies(self.cid)

    def delete_company(self):
        if not self.cid:
            return
        n = len(self.db.txns(self.cid))
        if ask(self, "حذف شرکت", f"شرکت «{self.company_name()}» با {n} تراکنش و تمام کدینگ آن برای همیشه حذف شود؟\n"
                                 "(پیشنهاد: قبل از حذف پشتیبان بگیرید.)", "حذف", "انصراف"):
            self.db.delete_company(self.cid)
            self.reload_companies()

    # ------------------------------------------------------------ محاسبه و نمایش
    def refresh(self):
        if not self.cid:
            self.result = None
            self.items = []
            for t in (self.t_items, self.t_txn, self.t_sum, self.t_cardex):
                pass
            return
        self.items = self.db.items(self.cid)
        self.settings = self.db.get_settings(self.cid)
        self.vat_map = self.db.vat_map(self.cid, self.settings.tax_rate)
        self.result = engine.compute(self.db.txns(self.cid), self.items, self.settings, self.vat_map)
        self.t_items.reload()
        self.t_txn.reload()
        self.t_cardex.reload()
        self.t_sum.reload()
        self.t_ctl.reload()
        self.t_set.reload()
        r = self.result
        k = "✔ کنترل‌ها سالم" if r.all_ok else f"⚠ {len(r.issues)} ردیف مغایر"
        self.status.showMessage(f"{len(r.rows)} تراکنش — {len(self.items)} کالا — "
                                f"ارزش موجودی: {fmt_num(r.total_value)} — {k}")
        idx = self.tabs.indexOf(self.t_ctl)
        self.tabs.setTabText(idx, "کنترل" if r.all_ok else f"کنترل ⚠ ({len(r.issues)})")

    # ------------------------------------------------------------ تراکنش
    def add_txn(self, default_type: str = "فروش"):
        if not self.items:
            warn(self, "کدینگ خالی است", "ابتدا کالا را در «کدینگ کالا» تعریف کنید.")
            return
        d = TxnDialog(self.items, parent=self, default_type=default_type)
        if d.exec():
            self.db.add_txn(self.cid, d.txn())
            self.refresh()

    def edit_txn(self, tid: int):
        row = next((r for r in self.result.rows if r.txn.id == tid), None)
        if not row:
            return
        d = TxnDialog(self.items, txn=row.txn, parent=self)
        if d.exec():
            self.db.update_txn(tid, d.txn())
            self.refresh()

    # ------------------------------------------------------------ ورود/خروج
    def import_excel(self):
        if not self.cid:
            return
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل", "", "Excel/CSV (*.xlsx *.xlsm *.csv)")
        if not path:
            return
        try:
            sheets = importer.read_sheets(path)
        except Exception as e:
            warn(self, "خطا در خواندن فایل", str(e))
            return
        if not sheets:
            warn(self, "داده‌ای پیدا نشد",
                 "هیچ شیتی با ستون‌های شناخته‌شده پیدا نشد.\n"
                 "برای کدینگ: «کد کالا» و «نام کالا».\nبرای تراکنش: «تاریخ، نوع، طرف حساب، کد کالا، نام کالا، مقدار، فی».\n"
                 "از منوی فایل می‌توانید «فایل نمونه» بسازید.")
            return
        dlg = ImportDialog(sheets, has_txns=bool(self.db.txns(self.cid)), parent=self)
        if not dlg.exec():
            return
        chosen = dlg.selected()
        if not chosen:
            return
        replace = dlg.replace_txns()
        if not replace:
            total, dup = importer.count_duplicates(self.db, self.cid, chosen)
            if total and dup >= max(3, total // 2):
                if not ask(self, "احتمال ورود تکراری",
                           f"از {total} تراکنش این فایل، {dup} تراکنش عیناً از قبل در این شرکت ثبت شده است.\n"
                           "ادامه‌ی ورود باعث دوبار شمرده شدن آن‌ها می‌شود.\n\n"
                           "اگر می‌خواهید داده‌ی قبلی با فایل جدید عوض شود، «انصراف» بزنید و گزینه‌ی «جایگزینی» را انتخاب کنید.",
                           "با این حال وارد کن", "انصراف"):
                    return
        if replace and not ask(self, "جایگزینی", "تمام تراکنش‌های فعلی این شرکت حذف و با داده‌ی فایل جایگزین شود؟",
                               "جایگزین کن", "انصراف"):
            return
        try:
            rep = importer.import_into(self.db, self.cid, chosen, replace=replace,
                                       replace_items=dlg.replace_coding())
        except Exception as e:
            warn(self, "خطا در ورود داده", str(e))
            return
        self.refresh()
        msg = (f"کالای جدید: {rep.items_added} — کالای به‌روزشده: {rep.items_updated}\n"
               f"تراکنش واردشده: {rep.txns_added}")
        if rep.vat_items:
            msg += f"\nنرخ ارزش افزوده‌ی اختصاصی برای {rep.vat_items} کالا از فایل خوانده شد."
        if rep.unresolved:
            msg += (f"\n\n⚠ {rep.unresolved} تراکنش کالای مشخص ندارند (نام/کد در کدینگ نیست). "
                    "در تب «کنترل» دیده می‌شوند و باید اصلاح شوند.")
        if rep.skipped:
            msg += f"\n{rep.skipped} ردیف به‌دلیل نوع نامشخص نادیده گرفته شد."
        info(self, "ورود داده", msg)
        self.tabs.setCurrentWidget(self.t_ctl if rep.unresolved else self.t_sum)
        self.offer_file_settings(path)

    def offer_file_settings(self, path: str):
        fs = importer.read_file_settings(path)
        cur = self.settings
        changed = {k: v for k, v in fs.items() if abs(getattr(cur, k) - v) > 1e-9}
        if not changed:
            return
        names = {"markup": "درصد سود پیشنهادی فروش", "dev_threshold": "آستانه انحراف نرخ خرید",
                 "min_margin": "حداقل سود فروش"}
        lines = "\n".join(f"• {names[k]}: {getattr(cur, k) * 100:g}٪ ← {v * 100:g}٪" for k, v in changed.items())
        new = {**{k: getattr(cur, k) for k in names}, **changed}
        extra = ""
        if new["markup"] <= new["min_margin"]:
            extra = ("\n\n⚠ درصد سود پیشنهادی از «حداقل سود فروش» بیشتر نیست؛ فروش با قیمت پیشنهادی در کنترل "
                     "مغایر علامت می‌خورد. «حداقل سود فروش» را در تب تنظیمات کمتر کنید.")
        if ask(self, "تنظیمات فایل", "این فایل تنظیمات زیر را دارد. برای این شرکت اعمال شود؟\n" + lines + extra,
               "اعمال کن", "نه"):
            from dataclasses import replace as _rep
            self.db.save_settings(self.cid, _rep(cur, **changed))
            self.refresh()

    def clear_data(self):
        if not self.cid:
            return
        d = ClearDialog(self.db, self.cid, self.company_name(), self)
        if not d.exec():
            return
        o = d.options()
        n = maintenance.preview_count(self.db, self.cid, o)
        what = []
        if o.txns:
            what.append(f"{n} تراکنش" + (f" (تا تاریخ {o.until})" if o.until else " (همه)"))
        if o.carry:
            what.append("با انتقال موجودی پایان دوره به «اول دوره»")
        if o.plan:
            what.append("طرح تخصیص")
        if o.items:
            what.append("کدینگ کالا")
        if not ask(self, "تأیید حذف", f"برای شرکت «{self.company_name()}» حذف شود:\n• " + "\n• ".join(what)
                   + "\n\n(قبل از حذف، پشتیبان خودکار گرفته می‌شود.)", "حذف کن", "انصراف"):
            return
        try:
            rep = maintenance.clear(self.db, self.cid, o)
        except Exception as e:
            warn(self, "خطا", str(e))
            return
        self.t_alloc.load_plan()
        self.refresh()
        msg = f"{rep.deleted} تراکنش حذف شد."
        if o.carry:
            msg += f"\n{rep.carried} کالا با موجودی پایان دوره به «اول دوره» منتقل شد."
            if rep.skipped_negative:
                msg += "\n⚠ این کالاها موجودی منفی داشتند و منتقل نشدند:\n" + "\n".join(rep.skipped_negative)
        if rep.items_deleted:
            msg += f"\n{rep.items_deleted} کالا از کدینگ حذف شد."
        msg += f"\n\nپشتیبان خودکار:\n{rep.backup}"
        info(self, "انجام شد", msg)

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل پشتیبان", str(self.db.path.parent / "backups"),
                                              "Database (*.db)")
        if not path:
            return
        if not ask(self, "بازیابی", "کل اطلاعات فعلی برنامه (همه‌ی شرکت‌ها) با این پشتیبان جایگزین شود؟\n"
                   "(از وضعیت فعلی هم یک پشتیبان خودکار گرفته می‌شود.)", "بازیابی", "انصراف"):
            return
        try:
            self.db.restore(path)
        except Exception as e:
            warn(self, "خطا", str(e))
            return
        if not self.db.companies():
            self.db.add_company("شرکت من")
        self.reload_companies()
        info(self, "انجام شد", "پشتیبان بازیابی شد.")

    def export_excel(self):
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره گزارش", f"{self.company_name()}_گزارش.xlsx",
                                              "Excel (*.xlsx)")
        if path:
            try:
                export_report(path, self.company_name(), self.result,
                              self.t_alloc.out or None)
            except Exception as e:
                warn(self, "خطا", str(e))
                return
            info(self, "ذخیره شد", path)

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره فایل نمونه", "نمونه_ورود_داده.xlsx", "Excel (*.xlsx)")
        if path:
            export_template(path)
            info(self, "ذخیره شد", path)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "پشتیبان‌گیری", "kardex_backup.db", "Database (*.db)")
        if path:
            self.db.backup(path)
            info(self, "ذخیره شد", f"پشتیبان در مسیر زیر ذخیره شد:\n{path}")

    def open_data_dir(self):
        p = str(self.db.path.parent)
        if sys.platform == "darwin":
            subprocess.Popen(["open", p])
        elif sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", p])
