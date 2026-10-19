"""رابط دسکتاپی (Tkinter) — روی ویندوز و مک بدون نصب چیز اضافه اجرا می‌شود."""
import platform
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

import core
import jalali as J

IS_MAC = platform.system() == "Darwin"
FONT = ("Arial", 12) if IS_MAC else ("Tahoma", 10)
BIG = (FONT[0], FONT[1] + 8, "bold")
BAD, WARN = "#c0392b", "#b7791f"
CAT = {"overdue": "سررسید گذشته", "today": "سررسید امروز", "tomorrow": "سررسید فردا"}


def money(n):
    return f"{n:,}" if isinstance(n, int) else ("" if n is None else n)


def guard(fn):
    """خطاهای ورودی (ValueError) را به‌صورت پیام نشان می‌دهد؛ برنامه نمی‌بندد."""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ValueError as e:
            messagebox.showerror("خطا", str(e))
        except Exception as e:  # noqa
            messagebox.showerror("خطای غیرمنتظره", f"{type(e).__name__}: {e}")
    return wrapper


class Table:
    """جدول راست‌چین: ستون اول سمت راست نمایش داده می‌شود. cols=[(key, عنوان, عرض, 'm'=مبلغ)]"""

    def __init__(self, parent, cols, height=10):
        self.frame = ttk.Frame(parent)
        self.keys = [c[0] for c in cols]
        self.kind = {c[0]: (c[3] if len(c) > 3 else "") for c in cols}
        self.tree = ttk.Treeview(self.frame, columns=self.keys, show="headings", height=height,
                                 displaycolumns=list(reversed(self.keys)), selectmode="browse")
        for c in cols:
            self.tree.heading(c[0], text=c[1], anchor="e")
            self.tree.column(c[0], width=c[2], anchor="e", stretch=True)
        sb = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        self.tree.pack(side="right", fill="both", expand=True)
        self.tree.tag_configure("bad", foreground=BAD)
        self.tree.tag_configure("warn", foreground=WARN)
        self.rows = []

    def load(self, rows, tag_fn=None):
        self.tree.delete(*self.tree.get_children())
        self.rows = rows
        for i, r in enumerate(rows):
            vals = [money(r.get(k)) if self.kind[k] == "m" else ("" if r.get(k) is None else str(r.get(k)))
                    for k in self.keys]
            self.tree.insert("", "end", iid=str(i), values=vals, tags=(tag_fn(r),) if tag_fn else ())

    def selected(self):
        sel = self.tree.selection()
        return self.rows[int(sel[0])] if sel else None


def field(parent, row, text, widget, col=0, span=1):
    """برچسب سمت راست، ورودی سمت چپِ آن (چیدمان راست‌به‌چپ)."""
    ttk.Label(parent, text=text).grid(row=row, column=col * 2 + 1, sticky="e", padx=4, pady=3)
    widget.grid(row=row, column=col * 2, sticky="we", padx=4, pady=3, columnspan=span)


def status_tag(r):
    t = r.get("status_text") or ""
    return "bad" if "گذشته" in t else "warn" if ("امروز" in t or "فردا" in t) else ""


REP_COLS = [("national_id", "شناسه", 90), ("first_name", "نام", 90), ("last_name", "نام خانوادگی", 110),
            ("bank", "بانک", 70), ("account", "شماره حساب", 110), ("sheba", "شماره شبا", 170),
            ("due", "سررسید", 85), ("interest_due", "سود قابل پرداخت (ریال)", 150, "m"),
            ("unpaid_periods", "دوره پرداخت‌نشده", 100)]


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("سیستم محاسبه سود سرمایه‌گذاری")
        self.root.geometry("1150x680")
        ttk.Style().configure(".", font=FONT)
        ttk.Style().configure("Treeview", font=FONT, rowheight=26)
        ttk.Style().configure("Treeview.Heading", font=(FONT[0], FONT[1], "bold"))
        self.con = core.connect()
        self.today_label = ttk.Label(self.root, text="", font=FONT)
        self.today_label.pack(anchor="e", padx=12, pady=(6, 0))
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.refreshers = []
        for title, builder in (("داشبورد و یادآور", self.tab_dashboard), ("سرمایه‌گذاران", self.tab_investors),
                               ("واریز و برداشت", self.tab_transactions), ("پرداخت سود", self.tab_payments),
                               ("جدول محاسبه سود", self.tab_summary), ("گزارش‌ها", self.tab_reports),
                               ("تنظیمات", self.tab_settings)):
            f = ttk.Frame(self.nb, padding=10)
            self.nb.add(f, text=title)
            self.refreshers.append(builder(f))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_current())
        self.last_day = date.today()
        self.refresh_current()
        self.root.after(600, self.startup_reminder)
        self.root.after(30 * 60 * 1000, self.tick)

    # ───────── کمک‌ها ─────────
    def refresh_current(self):
        self.today_label.config(text="امروز: " + J.fmt(date.today()))
        self.refreshers[self.nb.index(self.nb.select())]()

    def inv_map(self, with_all=False):
        """{'نام (شناسه)': شناسه}"""
        m = {"همه سرمایه‌گذاران": ""} if with_all else {}
        for r in core.list_investors(self.con):
            m[f"{r['first_name']} {r['last_name']} ({r['national_id']})"] = r["national_id"]
        return m

    def reminder_text(self):
        rep = core.reports(self.con)
        lines = [f"{CAT[k]}: {len(rep[k])} مورد — {money(sum(r['interest_due'] for r in rep[k]))} ریال"
                 for k in ("overdue", "today", "tomorrow") if rep[k]]
        return "\n".join(lines)

    def startup_reminder(self):
        txt = self.reminder_text()
        if txt:
            self.nb.select(0)
            messagebox.showinfo("یادآور سررسید", f"تاریخ امروز: {J.fmt(date.today())}\n\n{txt}")

    def tick(self):
        """هر ۳۰ دقیقه؛ اگر روز عوض شده باشد دوباره یادآوری می‌کند."""
        if date.today() != self.last_day:
            self.last_day = date.today()
            self.refresh_current()
            self.startup_reminder()
        self.root.after(30 * 60 * 1000, self.tick)

    # ───────── داشبورد ─────────
    def tab_dashboard(self, f):
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.kpi = {}
        for key, label in (("overdue", "سررسید گذشته"), ("today", "سررسید امروز"), ("tomorrow", "سررسید فردا"),
                           ("capital", "سرمایه کل (ریال)")):
            box = ttk.LabelFrame(top, text=label, padding=8)
            box.pack(side="right", expand=True, fill="x", padx=4)
            lbl = ttk.Label(box, text="0", font=BIG)
            lbl.pack()
            sub = ttk.Label(box, text="")
            sub.pack()
            self.kpi[key] = (lbl, sub)
        self.dash_tables = {}
        for key in ("overdue", "today", "tomorrow"):
            box = ttk.LabelFrame(f, text=CAT[key], padding=4)
            box.pack(fill="both", expand=True, pady=4)
            t = Table(box, REP_COLS, height=4)
            t.frame.pack(fill="both", expand=True)
            self.dash_tables[key] = t

        def refresh():
            rep = core.reports(self.con)
            for key in ("overdue", "today", "tomorrow"):
                rows = rep[key]
                self.dash_tables[key].load(rows, (lambda r: "bad") if key == "overdue" else None)
                self.kpi[key][0].config(text=str(len(rows)), foreground=BAD if (rows and key == "overdue") else "")
                self.kpi[key][1].config(text=money(sum(r["interest_due"] for r in rows)) + " ریال")
            st = core.all_states(self.con)
            self.kpi["capital"][0].config(text=money(sum(s["capital"] for s in st if s["active"])))
            self.kpi["capital"][1].config(text=f"{len(st)} سرمایه‌گذار")
        return refresh

    # ───────── سرمایه‌گذاران ─────────
    def tab_investors(self, f):
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ سرمایه‌گذار جدید", command=lambda: self.investor_form(None)).pack(side="right")
        ttk.Button(bar, text="ویرایش انتخاب‌شده", command=lambda: self.investor_form(t.selected())).pack(side="right", padx=6)
        ttk.Label(bar, text="(روی ردیف دوبار کلیک کنید. حذف ندارد؛ برای توقف سود وضعیت را «غیرفعال» کنید.)").pack(side="right", padx=6)
        t = Table(f, [("national_id", "کد ملی", 120), ("first_name", "نام", 120), ("last_name", "نام خانوادگی", 150),
                      ("contract_no", "شماره قرارداد", 100), ("mobile", "موبایل", 120), ("status", "وضعیت", 80)], height=20)
        t.frame.pack(fill="both", expand=True)
        t.tree.bind("<Double-1>", lambda e: self.investor_form(t.selected()))
        return lambda: t.load(core.list_investors(self.con))

    @guard
    def investor_form(self, row):
        inv = core.get_investor(self.con, row["national_id"]) if row else \
            {"status": core.ACTIVE, "banks": [{}, {}, {}, {}]}
        win = tk.Toplevel(self.root)
        win.title("ویرایش سرمایه‌گذار" if row else "سرمایه‌گذار جدید")
        win.transient(self.root)
        win.grab_set()
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        spec = [("national_id", "کد ملی / شناسه *"), ("contract_no", "شماره قرارداد"), ("contract_date", "تاریخ قرارداد (1405/03/10)"),
                ("first_name", "نام *"), ("last_name", "نام خانوادگی *"), ("father_name", "نام پدر"),
                ("birth_date", "تاریخ تولد (1370/01/01)"), ("mobile", "موبایل"), ("phone", "تلفن ثابت"),
                ("province", "استان"), ("city", "شهر"), ("status", "وضعیت")]
        vars_, widgets = {}, {}
        for i, (k, label) in enumerate(spec):
            v = tk.StringVar(value=inv.get(k) or "")
            vars_[k] = v
            if k == "status":
                w = ttk.Combobox(body, textvariable=v, values=[core.ACTIVE, core.INACTIVE], state="readonly", width=18)
            else:
                w = ttk.Entry(body, textvariable=v, width=22, justify="left" if k in ("national_id", "contract_no", "contract_date", "birth_date", "mobile", "phone") else "right")
            widgets[k] = w
            field(body, i // 3, label, w, col=i % 3)
        if row:
            widgets["national_id"].config(state="readonly")
        for k, label, r in (("address", "آدرس", 4), ("notes", "توضیحات", 5)):
            vars_[k] = tk.StringVar(value=inv.get(k) or "")
            field(body, r, label, ttk.Entry(body, textvariable=vars_[k], justify="right"), col=0, span=5)
        ttk.Label(body, text="حساب‌های بانکی", font=(FONT[0], FONT[1], "bold")).grid(row=6, column=0, columnspan=6, sticky="e", pady=(10, 2))
        bank_vars = []
        for i in range(4):
            bv = {}
            fr = ttk.Frame(body)
            fr.grid(row=7 + i, column=0, columnspan=6, sticky="we", pady=2)
            for k, label, w in (("sheba", "شبا", 26), ("card", "کارت", 18), ("account", "حساب", 16), ("bank", "بانک", 10)):
                bv[k] = tk.StringVar(value=inv["banks"][i].get(k, ""))
                ttk.Entry(fr, textvariable=bv[k], width=w, justify="left" if k != "bank" else "right").pack(side="left", padx=2)
                ttk.Label(fr, text=f"{label} {i + 1}").pack(side="left")
            bank_vars.append(bv)

        @guard
        def save():
            core.upsert_investor(self.con, {k: v.get() for k, v in vars_.items()},
                                 [{k: v.get() for k, v in bv.items()} for bv in bank_vars])
            win.destroy()
            self.refresh_current()
        btns = ttk.Frame(body)
        btns.grid(row=12, column=0, columnspan=6, pady=(12, 0))
        ttk.Button(btns, text="ذخیره", command=save).pack(side="left", padx=6)
        ttk.Button(btns, text="انصراف", command=win.destroy).pack(side="left")

    # ───────── تراکنش‌ها ─────────
    def tab_transactions(self, f):
        form = ttk.LabelFrame(f, text="ثبت واریز / برداشت", padding=8)
        form.pack(fill="x")
        inv, date_v, type_v, amt_v, note_v = (tk.StringVar() for _ in range(5))
        type_v.set(core.DEPOSIT)
        cb = ttk.Combobox(form, textvariable=inv, state="readonly", width=30)
        field(form, 0, "سرمایه‌گذار", cb, col=0)
        field(form, 0, "تاریخ (شمسی)", ttk.Entry(form, textvariable=date_v, width=14, justify="left"), col=1)
        ttk.Button(form, text="امروز", width=6, command=lambda: date_v.set(J.fmt(date.today()))).grid(row=0, column=4, padx=2)
        field(form, 1, "نوع", ttk.Combobox(form, textvariable=type_v, values=[core.DEPOSIT, core.WITHDRAW], state="readonly", width=12), col=0)
        field(form, 1, "مبلغ (ریال)", ttk.Entry(form, textvariable=amt_v, width=20, justify="left"), col=1)
        field(form, 1, "توضیحات", ttk.Entry(form, textvariable=note_v, width=24, justify="right"), col=2)
        flt = tk.StringVar()
        fb = ttk.Frame(f)
        fb.pack(fill="x", pady=6)
        ttk.Button(fb, text="حذف تراکنش انتخاب‌شده", command=lambda: delete()).pack(side="left")
        fcb = ttk.Combobox(fb, textvariable=flt, state="readonly", width=34)
        fcb.pack(side="right")
        ttk.Label(fb, text="فیلتر:").pack(side="right", padx=4)
        t = Table(f, [("date_j", "تاریخ", 90), ("first_name", "نام", 100), ("last_name", "نام خانوادگی", 120),
                      ("tx_type", "نوع", 70), ("amount", "مبلغ (ریال)", 140, "m"), ("notes", "توضیحات", 250)], height=16)
        t.frame.pack(fill="both", expand=True)
        maps = {}

        def refresh():
            maps["f"] = self.inv_map(True)
            maps["i"] = self.inv_map()
            fcb["values"], cb["values"] = list(maps["f"]), list(maps["i"])
            if not flt.get():
                flt.set("همه سرمایه‌گذاران")
            if not inv.get() and maps["i"]:
                inv.set(next(iter(maps["i"])))
            t.load(core.list_tx(self.con, maps["f"].get(flt.get()) or None))

        @guard
        def add():
            core.add_tx(self.con, maps["i"].get(inv.get()), date_v.get(), type_v.get(), amt_v.get(), note_v.get())
            amt_v.set("")
            note_v.set("")
            refresh()

        @guard
        def delete():
            r = t.selected()
            if r and messagebox.askyesno("حذف", "این تراکنش حذف شود؟"):
                core.delete_tx(self.con, r["id"])
                refresh()
        ttk.Button(form, text="ثبت", command=add).grid(row=1, column=5, padx=6)
        fcb.bind("<<ComboboxSelected>>", lambda e: refresh())
        return refresh

    # ───────── پرداخت سود ─────────
    def tab_payments(self, f):
        form = ttk.LabelFrame(f, text="ثبت پرداخت سود", padding=8)
        form.pack(fill="x")
        inv, date_v, amt_v, note_v, info = (tk.StringVar() for _ in range(5))
        cb = ttk.Combobox(form, textvariable=inv, state="readonly", width=34)
        field(form, 0, "سرمایه‌گذار", cb, col=0)
        date_entry = ttk.Entry(form, textvariable=date_v, width=14, justify="left")
        field(form, 0, "تاریخ واقعی پرداخت", date_entry, col=1)
        ttk.Label(form, textvariable=info, foreground=WARN).grid(row=1, column=0, columnspan=6, sticky="e", pady=4)
        field(form, 2, "مبلغ سود (ریال)", ttk.Entry(form, textvariable=amt_v, width=20, justify="left"), col=0)
        field(form, 2, "توضیحات", ttk.Entry(form, textvariable=note_v, width=28, justify="right"), col=1)
        ttk.Label(f, text="دوره و مبلغ خودکار از «اولین تاریخ سرمایه‌گذاری» محاسبه می‌شود؛ مبلغ را در صورت نیاز می‌توانید دستی تغییر دهید.").pack(anchor="e", pady=4)
        t = Table(f, [("pay_j", "تاریخ پرداخت", 95), ("first_name", "نام", 90), ("last_name", "نام خانوادگی", 110),
                      ("from_j", "از تاریخ", 90), ("to_j", "تا تاریخ (سررسید)", 110), ("amount", "مبلغ پرداختی (ریال)", 140, "m"),
                      ("notes", "توضیحات", 200)], height=13)
        maps = {}

        def calc(*_):
            try:
                s = core.suggest_payment(self.con, maps["i"].get(inv.get()), date_v.get())
                info.set(f"دوره {s['period_no']}: از {s['from']} تا {s['to']} ({s['days']} روز)")
                amt_v.set(money(s["amount"]))
            except ValueError as e:
                info.set(str(e))
                amt_v.set("")

        def refresh():
            maps["i"] = self.inv_map()
            cb["values"] = list(maps["i"])
            if not inv.get() and maps["i"]:
                inv.set(next(iter(maps["i"])))
            if not date_v.get():
                date_v.set(J.fmt(date.today()))
            calc()
            t.load(core.list_payments(self.con))

        @guard
        def save():
            core.add_payment(self.con, maps["i"].get(inv.get()), date_v.get(), amt_v.get(), note_v.get())
            note_v.set("")
            refresh()

        @guard
        def delete():
            r = t.selected()
            if r and messagebox.askyesno("حذف", "این پرداخت حذف شود؟ (دوره دوباره پرداخت‌نشده می‌شود)"):
                core.delete_payment(self.con, r["id"])
                refresh()
        ttk.Button(form, text="ثبت پرداخت", command=save).grid(row=2, column=5, padx=6)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="حذف پرداخت انتخاب‌شده (فقط آخرین پرداخت هر نفر)", command=delete).pack(side="left", pady=4)
        t.frame.pack(fill="both", expand=True)
        cb.bind("<<ComboboxSelected>>", calc)
        date_entry.bind("<KeyRelease>", calc)
        return refresh

    # ───────── جدول محاسبه ─────────
    def tab_summary(self, f):
        t = Table(f, [("national_id", "کد ملی", 100), ("first_name", "نام", 90), ("last_name", "نام خانوادگی", 110),
                      ("status", "وضعیت", 60), ("first_date", "اولین واریز", 85), ("capital", "سرمایه فعلی", 130, "m"),
                      ("last_pay", "پرداخت‌شده تا", 90), ("due_j", "سررسید بعدی", 90), ("accrued_today", "سود تا امروز", 110, "m"),
                      ("interest_due", "سود دوره (در سررسید)", 130, "m"), ("status_text", "وضعیت امروز", 190)], height=22)
        t.frame.pack(fill="both", expand=True)
        ttk.Label(f, text="«سود دوره» سود کامل دوره‌ی جاری تا روز سررسید است و با گذشتن سررسید زیاد نمی‌شود.").pack(anchor="e")
        return lambda: t.load(core.all_states(self.con), status_tag)

    # ───────── گزارش‌ها ─────────
    def tab_reports(self, f):
        which = tk.StringVar(value="today")
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        t = Table(f, REP_COLS, height=20)
        total = ttk.Label(f, text="", font=(FONT[0], FONT[1], "bold"))

        def refresh():
            rows = core.reports(self.con)[which.get()]
            t.load(rows)
            total.config(text=f"جمع: {money(sum(r['interest_due'] for r in rows))} ریال — {len(rows)} مورد")

        @guard
        def export():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                                initialfile=f"گزارش-{CAT[which.get()]}.xlsx")
            if path:
                with open(path, "wb") as fh:
                    fh.write(core.export_report(self.con, which.get()))
                messagebox.showinfo("ذخیره شد", path)
        ttk.Button(bar, text="خروجی اکسل", command=export).pack(side="left")
        for k in ("tomorrow", "today", "overdue"):
            ttk.Radiobutton(bar, text=CAT[k], value=k, variable=which, command=refresh).pack(side="right", padx=8)
        t.frame.pack(fill="both", expand=True)
        total.pack(anchor="e", pady=4)
        return refresh

    # ───────── تنظیمات ─────────
    def tab_settings(self, f):
        box = ttk.LabelFrame(f, text="تنظیمات محاسبه سود", padding=10)
        box.pack(fill="x")
        rate, basis, rnd = (tk.StringVar() for _ in range(3))
        field(box, 0, "نرخ سود ماهانه (0.08 یا 8)", ttk.Entry(box, textvariable=rate, width=12, justify="left"), col=0)
        field(box, 0, "مبنای روزهای ماه", ttk.Entry(box, textvariable=basis, width=8, justify="left"), col=1)
        field(box, 0, "گردکننده (ریال)", ttk.Entry(box, textvariable=rnd, width=10, justify="left"), col=2)

        @guard
        def save():
            core.save_settings(self.con, {"monthly_rate": rate.get(), "day_basis": basis.get(), "rounding": rnd.get()})
            messagebox.showinfo("تنظیمات", "ذخیره شد")
            refresh()
        ttk.Button(box, text="ذخیره", command=save).grid(row=0, column=6, padx=8)
        ttk.Label(f, text="سود هر روز = موجودی آن روز × نرخ ماهانه ÷ مبنای روز؛ مجموع دوره به نزدیک‌ترین مضرب گردکننده گرد می‌شود.").pack(anchor="e", pady=4)

        imp = ttk.LabelFrame(f, text="ورود اطلاعات از فایل اکسل قبلی (یک‌بار برای شروع)", padding=10)
        imp.pack(fill="x", pady=8)

        @guard
        def do_import():
            path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xlsm")])
            if not path:
                return
            r = core.import_excel(self.con, path)
            msg = f"سرمایه‌گذار: {r['investors']} | تراکنش: {r['transactions']} | پرداخت: {r['payments']}"
            if r["warnings"]:
                msg += "\n\n" + "\n".join(r["warnings"][:15])
            messagebox.showinfo("ورود اطلاعات", msg)
            self.refresh_current()
        ttk.Button(imp, text="انتخاب فایل و ورود اطلاعات", command=do_import).pack(side="right")
        ttk.Label(imp, text="ورود دوباره‌ی همان فایل، تراکنش‌ها را تکراری ثبت می‌کند.").pack(side="right", padx=10)

        bk = ttk.LabelFrame(f, text="پشتیبان‌گیری", padding=10)
        bk.pack(fill="x")

        @guard
        def backup():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                                initialfile=f"پشتیبان-{date.today()}.xlsx")
            if path:
                with open(path, "wb") as fh:
                    fh.write(core.export_backup(self.con))
                messagebox.showinfo("ذخیره شد", path)
        ttk.Button(bk, text="ذخیره پشتیبان اکسل", command=backup).pack(side="right")
        ttk.Label(bk, text=f"فایل اصلی داده‌ها: {core.DB_PATH} — برای پشتیبان‌گیری کامل همین فایل را کپی کنید.").pack(side="right", padx=10)

        def refresh():
            s = core.get_settings(self.con)
            rate.set(s["monthly_rate"])
            basis.set(s["day_basis"])
            rnd.set(s["rounding"])
        return refresh

    def run(self):
        self.root.mainloop()


def run():
    App().run()
