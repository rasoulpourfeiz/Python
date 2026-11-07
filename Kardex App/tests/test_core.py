import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import engine, importer, maintenance
from core.allocation import PlanRow, allocate, allocate_dated
from core.db import Database
from core.engine import Settings, Txn
from core.textutil import g2j, j2g, norm_date

LEGACY = os.environ.get("KARDEX_LEGACY_XLSM", "")
MAJID = os.environ.get("KARDEX_MAJID_XLSX", "")


class TextTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(norm_date("۱۴۰۵/۷/۲۶ "), "1405/07/26")
        self.assertEqual(g2j(2026, 10, 18), (1405, 7, 26))
        self.assertEqual(j2g(1405, 7, 26), (2026, 10, 18))
        self.assertEqual(norm_date("1403/12/30"), "1403/12/30")   # کبیسه
        self.assertIsNone(norm_date("1404/12/30"))
        self.assertIsNone(norm_date("1405/13/01"))
        self.assertIsNone(norm_date("abc"))


class EngineTests(unittest.TestCase):
    ITEMS = [("1", "الف"), ("2", "ب")]

    def test_moving_average_and_order(self):
        tx = [
            Txn("1405/01/02", "فروش", "1", 40, 1_200_000, id=3),
            Txn("1405/01/01", "اول دوره", "1", 100, 1_000_000, id=1),
            Txn("1405/01/02", "خرید", "1", 100, 1_100_000, id=2),
        ]
        res = engine.compute(tx, self.ITEMS, Settings())
        s = res.summary[0]
        self.assertAlmostEqual(s.avg, 1_050_000)
        self.assertEqual(s.qty, 160)
        # خرید هم‌روز قبل از فروش حساب می‌شود
        self.assertEqual([r.txn.id for r in res.cardex_for("1")], [1, 2, 3])
        self.assertEqual(s.price, 1_076_500 // 500 * 500 + (500 if 1_076_500 % 500 >= 250 else 0))

    def test_flags(self):
        tx = [
            Txn("1405/01/01", "خرید", "1", 10, 1000, id=1),
            Txn("1405/01/02", "فروش", "1", 15, 1100, id=2),      # موجودی منفی
            Txn("1405/01/03", "خرید", "1", 10, 2000, id=3),      # انحراف
            Txn("1405/13/03", "خرید", "2", 10, 2000, id=4),      # تاریخ خراب
            Txn("1405/01/03", "خرید", "9", 10, 2000, id=5),      # کالای ناشناخته
        ]
        res = engine.compute(tx, self.ITEMS, Settings())
        st = {r.txn.id: r.status for r in res.rows}
        self.assertEqual(st[2], engine.ST_NEG)
        self.assertEqual(st[4], engine.ST_DATE)
        self.assertEqual(st[5], engine.ST_ITEM)
        self.assertFalse(res.all_ok)

    def test_low_margin_sale(self):
        tx = [Txn("1405/01/01", "خرید", "1", 10, 1000, id=1),
              Txn("1405/01/02", "فروش", "1", 1, 1010, id=2)]
        res = engine.compute(tx, self.ITEMS, Settings())
        self.assertEqual(res.rows[1].status, engine.ST_LOW)


class RealWorldTests(unittest.TestCase):
    ITEMS = [("1", "الف")]

    def test_zero_fee_purchase_is_valid_and_lowers_average(self):
        tx = [Txn("1405/01/01", "خرید", "1", 10, 1000, id=1), Txn("1405/01/02", "خرید", "1", 10, 0, id=2)]
        res = engine.compute(tx, self.ITEMS, Settings())
        self.assertNotIn(engine.ST_VALUE, [r.status for r in res.rows])
        self.assertAlmostEqual(res.summary[0].avg, 500)
        self.assertEqual(res.summary[0].qty, 20)

    def test_negative_fee_and_zero_qty_are_invalid(self):
        tx = [Txn("1405/01/01", "خرید", "1", 10, -5, id=1), Txn("1405/01/01", "خرید", "1", 0, 5, id=2)]
        res = engine.compute(tx, self.ITEMS, Settings())
        self.assertEqual([r.status for r in res.rows], [engine.ST_VALUE, engine.ST_VALUE])

    def test_float_noise_does_not_create_negative_stock(self):
        tx = [Txn("1405/01/01", "خرید", "1", 0.1, 1000, id=1), Txn("1405/01/01", "خرید", "1", 0.2, 1000, id=2),
              Txn("1405/01/02", "فروش", "1", 0.3, 1100, id=3)]
        res = engine.compute(tx, self.ITEMS, Settings())
        self.assertEqual(res.summary[0].qty, 0)
        self.assertEqual(res.summary[0].status, "موجودی صفر")
        self.assertNotIn(engine.ST_NEG, [r.status for r in res.rows])


class VatTests(unittest.TestCase):
    ITEMS = [("1", "بدون مالیات"), ("2", "ده درصد"), ("3", "شانزده درصد")]
    VAT = {"1": 0.0, "2": 0.10, "3": 0.16}

    def _res(self):
        tx = [Txn("1405/01/01", "خرید", c, 1000, 1_000_000, id=i) for i, c in enumerate("123", 1)]
        return tx, engine.compute(tx, self.ITEMS, Settings(), self.VAT)

    def test_summary_carries_item_vat(self):
        _tx, res = self._res()
        self.assertEqual([s.vat for s in res.summary], [0.0, 0.10, 0.16])

    def test_allocation_uses_each_items_own_rate(self):
        tx, res = self._res()
        price = res.summary[0].price                            # هر سه کالا یک قیمت دارند
        for code, rate in self.VAT.items():
            only = [(c, n) for c, n in self.ITEMS if c == code]
            r1 = engine.compute([t for t in tx if t.code == code], only, Settings(), self.VAT)
            out = allocate_dated([PlanRow("1405/01/05", "x", 10 * price * (1 + rate))],
                                 [t for t in tx if t.code == code], only, Settings(), self.VAT)
            self.assertEqual(sum(l.qty for l in out), 10)
            self.assertAlmostEqual(out[0].tax, 10 * price * rate)
            self.assertAlmostEqual(out[0].gross, 10 * price * (1 + rate))
        # مسیر غیرتاریخی هم همین نرخ‌ها را می‌گیرد
        out2 = allocate([PlanRow("1405/01/05", "x", 10 * price * 1.16)], [res.summary[2]], Settings())
        self.assertEqual((out2[0].qty, round(out2[0].tax)), (10, round(10 * price * 0.16)))

    def test_old_database_is_migrated(self):
        import sqlite3
        path = tempfile.mktemp(suffix=".db")
        con = sqlite3.connect(path)
        con.executescript("""CREATE TABLE companies(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, settings TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE items(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(company_id, code));
            CREATE TABLE txns(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, date TEXT NOT NULL, type TEXT NOT NULL, party TEXT NOT NULL DEFAULT '', code TEXT NOT NULL DEFAULT '', raw_name TEXT NOT NULL DEFAULT '', qty REAL NOT NULL, fee REAL NOT NULL);
            CREATE TABLE plan(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, date TEXT NOT NULL DEFAULT '', buyer TEXT NOT NULL DEFAULT '', amount REAL NOT NULL DEFAULT 0);
            INSERT INTO companies(id,name) VALUES(1,'قدیمی'); INSERT INTO items(company_id,code,name) VALUES(1,'5','کالا');""")
        con.commit()
        con.close()
        db = Database(path)
        self.assertEqual(db.items_full(1), [("5", "کالا", None)])
        self.assertEqual(db.vat_map(1, 0.10), {"5": 0.10})


class OfficialInvoiceTests(unittest.TestCase):
    ITEMS = [("1", "الف"), ("2", "ب")]
    VAT = {"1": 0.10, "2": 0.16}

    def _tx(self):
        return [Txn("1405/01/01", "خرید", "1", 100, 1_000_000, id=1), Txn("1405/01/01", "خرید", "2", 100, 1_000_000, id=2)]

    def test_official_line_is_exact_and_not_repriced(self):
        plan = [PlanRow("1405/01/05", "مشتری", 0.0, "1", 37, 1_234_567)]
        out = allocate_dated(plan, self._tx(), self.ITEMS, Settings(), self.VAT)
        l = out[0]
        self.assertEqual((l.status, l.qty, l.price), ("رسمی", 37, 1_234_567))       # بدون گرد کردن و قیمت‌گذاری مجدد
        self.assertAlmostEqual(l.tax, 37 * 1_234_567 * 0.10)

    def test_fee_derived_from_final_amount_with_item_vat(self):
        total = 20 * 1_500_000 * 1.16
        out = allocate_dated([PlanRow("1405/01/05", "x", total, "2", 20, None)], self._tx(), self.ITEMS, Settings(), self.VAT)
        self.assertAlmostEqual(out[0].price, 1_500_000)
        self.assertAlmostEqual(out[0].gross, total)
        self.assertAlmostEqual(out[0].diff, 0, places=4)

    def test_official_reserves_stock_before_auto_rows(self):
        tx = [Txn("1405/01/01", "خرید", "1", 100, 1_000_000, id=1)]
        items = [("1", "الف")]
        price = engine.compute(tx, items, Settings()).summary[0].price
        plan = [PlanRow("1405/01/02", "عادی", 100 * price * 1.1),                  # اول در لیست ولی رسمی باید اولویت داشته باشد
                PlanRow("1405/01/03", "رسمی", 0.0, "1", 80, 1_100_000)]
        for dated in (True, False):
            if dated:
                out = allocate_dated(plan, tx, items, Settings(), {})
            else:
                out = allocate(plan, engine.compute(tx, items, Settings()).summary, Settings())
            off = [l for l in out if l.status.startswith("رسمی")]
            auto = [l for l in out if not l.status.startswith("رسمی")]
            self.assertEqual((len(off), off[0].qty, off[0].status), (1, 80, "رسمی"))
            self.assertEqual(sum(l.qty for l in auto), 20)                          # فقط باقیمانده به ردیف عادی می‌رسد

    def test_insufficient_stock_is_flagged_but_kept(self):
        out = allocate_dated([PlanRow("1405/01/05", "x", 0.0, "1", 500, 1_100_000)], self._tx(), self.ITEMS, Settings(), self.VAT)
        self.assertEqual((out[0].qty, out[0].status), (500, "رسمی — موجودی ناکافی"))

    def test_plan_roundtrip_and_migration(self):
        db = Database(tempfile.mktemp(suffix=".db"))
        cid = db.add_company("ش")
        db.save_plan(cid, [("1405/01/05", "x", 0.0, "الف", 12.5, 1000.0), ("1405/01/06", "y", 5000.0, "", None, None)])
        self.assertEqual(db.plan(cid), [("1405/01/05", "x", 0.0, "الف", 12.5, 1000.0),
                                        ("1405/01/06", "y", 5000.0, "", None, None)])
        import sqlite3
        path = tempfile.mktemp(suffix=".db")
        con = sqlite3.connect(path)
        con.executescript("""CREATE TABLE companies(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, settings TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE items(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(company_id, code));
            CREATE TABLE txns(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, date TEXT NOT NULL, type TEXT NOT NULL, party TEXT NOT NULL DEFAULT '', code TEXT NOT NULL DEFAULT '', raw_name TEXT NOT NULL DEFAULT '', qty REAL NOT NULL, fee REAL NOT NULL);
            CREATE TABLE plan(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, date TEXT NOT NULL DEFAULT '', buyer TEXT NOT NULL DEFAULT '', amount REAL NOT NULL DEFAULT 0);
            INSERT INTO companies(id,name) VALUES(1,'قدیمی'); INSERT INTO plan(company_id,date,buyer,amount) VALUES(1,'1405/01/01','خ',100);""")
        con.commit()
        con.close()
        old = Database(path)
        self.assertEqual(old.plan(1), [("1405/01/01", "خ", 100.0, "", None, None)])


class UndoTests(unittest.TestCase):
    def _db(self):
        db = Database(tempfile.mktemp(suffix=".db"))
        cid = db.add_company("ش")
        db.add_item(cid, "1", "الف", 0.16)
        db.add_item(cid, "2", "ب")
        db.add_txns(cid, [Txn("1405/01/01", "اول دوره", "1", 100, 1000), Txn("1405/01/02", "خرید", "2", 5, 20),
                          Txn("1405/01/03", "فروش", "1", 10, 1500)])
        db.save_plan(cid, [("1405/02/01", "x", 500.0, "", None, None)])
        db.undo.clear()
        return db, cid

    def _state(self, db, cid):
        return (db.items_full(cid), [(t.id, t.date, t.type, t.code, t.qty, t.fee) for t in db.txns(cid)],
                db.plan(cid), db.get_settings(cid), db.companies())

    def test_undo_redo_txn_delete_restores_ids_and_order(self):
        db, cid = self._db()
        before = self._state(db, cid)
        ids = [t.id for t in db.txns(cid)][:2]
        db.delete_txns(ids)
        self.assertEqual(len(db.txns(cid)), 1)
        self.assertEqual(db.undo.undo_label, "حذف 2 تراکنش")
        db.undo.undo()
        self.assertEqual(self._state(db, cid), before)            # شناسه‌ها و ترتیب دقیقاً برگشت
        db.undo.redo()
        self.assertEqual(len(db.txns(cid)), 1)

    def test_scopes_are_independent(self):
        db, cid = self._db()
        db.save_plan(cid, [("1405/02/02", "y", 900.0, "", None, None)])      # تغییر طرح
        db.add_txn(cid, Txn("1405/01/09", "خرید", "1", 1, 1))               # تغییر تراکنش
        db.undo.undo()                                                       # فقط تراکنش برگردد
        self.assertEqual(len(db.txns(cid)), 3)
        self.assertEqual(db.plan(cid)[0][1], "y")
        db.undo.undo()
        self.assertEqual(db.plan(cid)[0][1], "x")

    def test_item_code_change_is_undone_with_txns(self):
        db, cid = self._db()
        before = self._state(db, cid)
        db.update_item(cid, "1", "11", "الف", 0.16)
        self.assertIn("11", {t.code for t in db.txns(cid)})
        db.undo.undo()
        self.assertEqual(self._state(db, cid), before)

    def test_import_is_a_single_undo_step(self):
        db, cid = self._db()
        before = self._state(db, cid)
        rows = [["1405/03/01", "خرید", "", "1", "الف", 5, 1000], ["1405/03/02", "خرید", "", "2", "ب", 6, 2000]]
        sh = importer.SheetInfo("خرید", "txns", 0, {"date": 0, "type": 1, "party": 2, "code": 3, "name": 4, "qty": 5, "fee": 6}, rows)
        isheet = importer.SheetInfo("کدینگ", "items", 0, {"code": 0, "name": 1, "vat": 2}, [["9", "جدید", 10]])
        importer.import_into(db, cid, [isheet, sh], replace=True)
        self.assertEqual(len(db.undo.undo_stack), 1)
        db.undo.undo()
        self.assertEqual(self._state(db, cid), before)

    def test_delete_and_create_company(self):
        db, cid = self._db()
        before = self._state(db, cid)
        db.delete_company(cid)
        self.assertEqual(db.companies(), [])
        db.undo.undo()
        self.assertEqual(self._state(db, cid), before)             # کالا، تراکنش، طرح و تنظیمات برگشت
        c2 = db.add_company("دوم")
        db.undo.undo()                                             # ساخت شرکت دوم لغو
        self.assertNotIn(c2, [c for c, _ in db.companies()])
        db.undo.redo()
        self.assertIn(c2, [c for c, _ in db.companies()])

    def test_rename_settings_and_new_action_clears_redo(self):
        db, cid = self._db()
        db.rename_company(cid, "نام نو")
        db.save_settings(cid, Settings(markup=0.04))
        db.undo.undo()
        self.assertEqual(db.get_settings(cid).markup, Settings().markup)
        db.undo.undo()
        self.assertEqual(db.companies(), [(cid, "ش")])
        self.assertTrue(db.undo.redo_stack)
        db.add_txn(cid, Txn("1405/01/10", "خرید", "1", 1, 1))
        self.assertFalse(db.undo.redo_stack)                       # عمل جدید، Redo را پاک می‌کند

    def test_maintenance_clear_is_one_undo_step(self):
        db, cid = self._db()
        before = self._state(db, cid)
        maintenance.clear(db, cid, maintenance.ClearOptions(items=True))
        self.assertEqual((len(db.txns(cid)), len(db.items(cid))), (0, 0))
        self.assertEqual(len(db.undo.undo_stack), 1)
        db.undo.undo()
        self.assertEqual(self._state(db, cid), before)

    def test_stack_is_trimmed_by_size(self):
        db, cid = self._db()
        db.undo.max_entries = 3
        for i in range(6):
            db.add_txn(cid, Txn("1405/01/10", "خرید", "1", 1, 1))
        self.assertEqual(len(db.undo.undo_stack), 3)


class AllocationTests(unittest.TestCase):
    def test_stock_is_deducted_between_rows(self):
        tx = [Txn("1405/01/01", "خرید", "1", 100, 1_000_000, id=1)]
        res = engine.compute(tx, [("1", "الف")], Settings())
        price = res.summary[0].price          # 1,025,000
        plan = [PlanRow("1405/01/05", "x", 60 * price * 1.1),
                PlanRow("1405/01/05", "y", 60 * price * 1.1)]
        out = allocate(plan, res.summary, Settings())
        self.assertEqual(sum(l.qty for l in out), 100)          # بیشتر از موجودی تخصیص نمی‌یابد
        self.assertEqual({l.status for l in out if l.plan_index == 2}, {"جزئی"})

    def test_split_between_items(self):
        tx = [Txn("1405/01/01", "خرید", "1", 10, 1_000_000, id=1),
              Txn("1405/01/01", "خرید", "2", 10, 1_000_000, id=2)]
        res = engine.compute(tx, [("1", "الف"), ("2", "ب")], Settings())
        price = res.summary[0].price
        out = allocate([PlanRow("1405/01/05", "x", 15 * price * 1.1)], res.summary, Settings())
        self.assertEqual(sum(l.qty for l in out), 15)
        self.assertEqual(out[-1].status, "کامل")


class DatedAllocationTests(unittest.TestCase):
    ITEMS = [("1", "الف")]

    def _tx(self):
        return [Txn("1405/01/01", "خرید", "1", 100, 1_000_000, id=1),
                Txn("1405/01/10", "خرید", "1", 100, 2_000_000, id=2)]

    def test_uses_average_of_sale_date(self):
        st = Settings()
        plan = [PlanRow("1405/01/05", "x", 10 * 1_025_000 * 1.1),     # قبل از خرید دوم
                PlanRow("1405/01/10", "y", 10 * 1_564_500 * 1.1)]    # بعد از خرید دوم
        out = allocate_dated(plan, self._tx(), self.ITEMS, st)
        self.assertEqual(out[0].avg, 1_000_000)
        self.assertEqual(out[0].price, 1_025_000)
        # بعد از فروش ۱۰ عدد اول، موجودی ۹۰ تا با ۱٫۰ م؛ خرید ۱۰۰ تای ۲ م → میانگین ۱٬۵۲۶٬۳۱۵٫۷۹
        self.assertAlmostEqual(out[1].avg, 1_526_315.789, places=2)
        self.assertEqual(out[1].price, 1_564_500)

    def test_cannot_sell_before_purchase(self):
        out = allocate_dated([PlanRow("1405/01/05", "x", 150 * 1_025_000 * 1.1)], self._tx(), self.ITEMS, Settings())
        self.assertEqual(sum(l.qty for l in out), 100)      # خرید دوم هنوز نیامده
        self.assertEqual(out[-1].status, "جزئی")

    def test_respects_later_sales_and_plan_order(self):
        tx = self._tx() + [Txn("1405/01/08", "فروش", "1", 95, 1_100_000, id=3)]
        # فروش واقعی ۹۵ تایی در 01/08 → در 01/05 فقط ۵ عدد قابل فروش است
        out = allocate_dated([PlanRow("1405/01/05", "x", 50 * 1_025_000 * 1.1)], tx, self.ITEMS, Settings())
        self.assertEqual(sum(l.qty for l in out), 5)

    def test_result_has_no_control_flags(self):
        st = Settings()
        plan = [PlanRow("1405/01/05", "x", 30 * 1_025_000 * 1.1), PlanRow("1405/01/12", "y", 60 * 1_564_500 * 1.1)]
        out = allocate_dated(plan, self._tx(), self.ITEMS, st)
        sales = [Txn(l.date, "فروش", l.code, l.qty, l.price, id=100 + i) for i, l in enumerate(out)]
        res = engine.compute(self._tx() + sales, self.ITEMS, st)
        # خود فروش‌های تخصیص‌یافته نباید منفی یا کم‌سود شوند
        self.assertEqual([r.status for r in res.rows if r.status and r.txn.type == "فروش"], [])


class MaintenanceTests(unittest.TestCase):
    def _db(self):
        db = Database(tempfile.mktemp(suffix=".db"))
        cid = db.add_company("ش")
        db.add_item(cid, "1", "الف")
        db.add_item(cid, "2", "ب")
        db.add_txns(cid, [Txn("1405/01/01", "اول دوره", "1", 100, 1_000_000), Txn("1405/01/02", "خرید", "1", 50, 1_300_000),
                          Txn("1405/01/03", "فروش", "1", 30, 1_300_000), Txn("1405/01/04", "خرید", "2", 10, 500_000),
                          Txn("1405/02/05", "خرید", "1", 20, 1_500_000), Txn("1405/02/06", "فروش", "1", 40, 1_500_000)])
        db.save_plan(cid, [("1405/02/10", "x", 1000.0)])
        return db, cid

    def _summary(self, db, cid):
        r = engine.compute(db.txns(cid), db.items(cid), db.get_settings(cid))
        return {s.code: (s.qty, round(s.avg, 6)) for s in r.summary if s.n_txn}

    def test_carry_over_keeps_balance_and_average(self):
        db, cid = self._db()
        before = self._summary(db, cid)
        rep = maintenance.clear(db, cid, maintenance.ClearOptions(until="1405/01/31", carry=True))
        self.assertEqual(rep.deleted, 4)
        self.assertEqual(rep.carried, 2)
        self.assertEqual(len(db.txns(cid)), 2 + 2)             # دو تراکنش اردیبهشت + دو اول دوره
        self.assertEqual(self._summary(db, cid), before)       # موجودی و میانگین بدون تغییر
        self.assertEqual(db.plan(cid), [])
        self.assertTrue(Path(rep.backup).exists())

    def test_delete_all_keep_items(self):
        db, cid = self._db()
        rep = maintenance.clear(db, cid, maintenance.ClearOptions(plan=False))
        self.assertEqual((rep.deleted, len(db.txns(cid)), len(db.items(cid))), (6, 0, 2))
        self.assertEqual(len(db.plan(cid)), 1)

    def test_delete_everything_and_validation(self):
        db, cid = self._db()
        maintenance.clear(db, cid, maintenance.ClearOptions(items=True))
        self.assertEqual((len(db.txns(cid)), len(db.items(cid))), (0, 0))
        for bad in (maintenance.ClearOptions(carry=True), maintenance.ClearOptions(until="1405/13/01"),
                    maintenance.ClearOptions(until="1405/01/01", items=True)):
            self.assertTrue(maintenance.validate(bad))

    def test_duplicate_import_detection(self):
        db, cid = self._db()
        rows = [["1405/01/03", "فروش", "", "1", "الف", 30, 1_300_000],
                ["1405/01/03", "فروش", "", "1", "الف", 30, 1_300_000],      # دو فروش یکسان
                ["1405/05/05", "خرید", "", "2", "ب", 5, 400_000]]
        sh = importer.SheetInfo("فروش", "txns", 0, {"date": 0, "type": 1, "party": 2, "code": 3, "name": 4,
                                                    "qty": 5, "fee": 6}, rows)
        total, dup = importer.count_duplicates(db, cid, [sh])
        self.assertEqual((total, dup), (3, 1))     # فقط یکی از دو فروش یکسان قبلاً ثبت شده

    def test_restore_roundtrip(self):
        db, cid = self._db()
        b = db.auto_backup("t")
        maintenance.clear(db, cid, maintenance.ClearOptions(items=True))
        db.restore(b)
        self.assertEqual(len(db.txns(cid)), 6)
        with self.assertRaises(ValueError):
            bad = Path(tempfile.mktemp(suffix=".db"))
            bad.write_text("not a db")
            db.restore(bad)


@unittest.skipUnless(MAJID and Path(MAJID).exists(), "فایل نمونه‌ی مجید در دسترس نیست")
class MajidVatTests(unittest.TestCase):
    def test_item_vat_imported_and_tax_matches_excel(self):
        warnings.simplefilter("ignore")
        db = Database(tempfile.mktemp(suffix=".db"))
        cid = db.add_company("m")
        rep = importer.import_into(db, cid, [s for s in importer.read_sheets(MAJID) if s.default_checked])
        self.assertGreater(rep.vat_items, 900)
        vm = db.vat_map(cid, 0.10)
        self.assertEqual({round(v, 2) for v in vm.values()}, {0.0, 0.10, 0.16})
        sales = sum(t.qty * t.fee * vm.get(t.code, 0.10) for t in db.txns(cid) if t.type == "فروش")
        self.assertAlmostEqual(sales, 36_954_712_847, delta=2)       # مجموع ستون «مالیات و عوارض» اکسل


@unittest.skipUnless(LEGACY and Path(LEGACY).exists(), "فایل اکسل قدیمی در دسترس نیست")
class LegacyWorkbookTests(unittest.TestCase):
    def test_matches_excel_summary(self):
        warnings.simplefilter("ignore")
        db = Database(tempfile.mktemp(suffix=".db"))
        cid = db.add_company("t")
        sheets = [s for s in importer.read_sheets(LEGACY) if s.default_checked]
        rep = importer.import_into(db, cid, sheets)
        self.assertEqual(rep.txns_added, 102)
        res = engine.compute(db.txns(cid), db.items(cid), db.get_settings(cid))
        self.assertTrue(res.all_ok)
        self.assertEqual(round(res.total_value), 1520846676)
        self.assertEqual(importer.read_file_settings(LEGACY),
                         {"markup": 0.025, "dev_threshold": 0.05, "min_margin": 0.02})
        got = {s.code: (s.qty, s.price) for s in res.summary if s.n_txn}
        self.assertEqual(got["17"], (0, 1082500))
        self.assertEqual(got["18"], (611, 1120000))
        self.assertEqual(got["23"], (29, 1493000))
        self.assertEqual(got["40"], (742, 1120000))


if __name__ == "__main__":
    unittest.main()
