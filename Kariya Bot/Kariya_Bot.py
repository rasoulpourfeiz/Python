pip install playwright!
# ============================ تنظیمات ============================
CDP_URL = "http://127.0.0.1:9222"
PAGE_URL_PART = "https://new.kariyahesab.com/acc"

DO_SEND = True             # مرحله‌ی ارسال
DO_INQUIRY = True          # مرحله‌ی استعلام
MAX_SEND = None               # برای تست: 1 یا 2  |  بعد از تست: None (بدون محدودیت)

SEND_TIMEOUT = 90          # حداکثر انتظار (ثانیه) برای تمام شدن ارسال هر فاکتور
INQUIRY_SETTLE = 6         # حداکثر انتظار (ثانیه) برای جواب هر استعلام
INQUIRY_ROUNDS = 2         # چند دور استعلام برای فاکتورهای بدون جواب
ROUND_WAIT = 30            # فاصله بین دورهای استعلام (ثانیه)
PAGE_SETTLE = 2            # صبر بعد از عوض شدن صفحه‌ی جدول (ثانیه)
DELAY_BETWEEN = 1.0        # مکث کوتاه بین فاکتورها (ثانیه)

ROW = "tr"                 # اگر جدول از div ساخته شده بود این را عوض کنید
# ================================================================
import csv
import re
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

STOP = threading.Event()   # با STOP.set() می‌توانید اجرا را متوقف کنید

Z = r"[\s\u200c]*"  # فاصله یا نیم‌فاصله
RE_UNSENT = re.compile(rf"ارسال{Z}نشده")
RE_PENDING = re.compile(rf"در{Z}انتظار|ارسال{Z}شده")
RE_DONE = re.compile(rf"ثبت{Z}در{Z}سامانه")
RE_CONFIRM_TEXT = re.compile(r"سامانه\s*م.{1,2}دیان\s*فرستاده\s*شود")
RE_CONFIRM_BTN = re.compile(r"^\s*ت\S{0,2}ی+د\s*$")
RE_INVOICE_NO = re.compile(r"^[0-9۰-۹]{8,14}$")


# --------------------------- ابزارهای کمکی ---------------------------
def row_number(row):
    try:
        for txt in row.locator("td").all_inner_texts():
            t = txt.strip()
            if RE_INVOICE_NO.match(t):
                return t
    except Exception:
        pass
    return None


def click_status_button(row, rx):
    cell = row.locator("td").filter(has_text=rx).first
    btn = cell.locator("button")
    if btn.count():
        btn.first.click()
    else:
        cell.get_by_text(rx).first.click()


def get_modal(page):
    return (
        page.locator("div")
        .filter(has=page.get_by_role("button", name="تغییر وضعیت", exact=True))
        .filter(has_text="شماره مالیاتی")
        .last
    )


def modal_text(page):
    try:
        return get_modal(page).inner_text(timeout=2000)
    except Exception:
        return ""


def close_modal(page):
    try:
        page.get_by_role("button", name="بستن", exact=True).first.click(timeout=3000)
    except Exception:
        page.keyboard.press("Escape")
    time.sleep(0.5)


def classify(text):
    if "هنوز جوابی" in text:
        return "pending"
    if RE_DONE.search(text):
        return "done"
    return "other"


def next_page(page):
    btn = page.get_by_role("button", name="بعدی", exact=True)
    if btn.count() == 0 or not btn.first.is_enabled():
        return False
    btn.first.click()
    time.sleep(PAGE_SETTLE)
    return True


def goto_first_page(page):
    while True:
        btn = page.get_by_role("button", name="قبلی", exact=True)
        if btn.count() == 0 or not btn.first.is_enabled():
            return
        btn.first.click()
        time.sleep(PAGE_SETTLE)


def for_each_page(page, fn):
    goto_first_page(page)
    page_no = 1
    while True:
        print(f"\n--- صفحه {page_no} ---")
        if fn(page) == "stop" or STOP.is_set():
            return
        if not next_page(page):
            return
        page_no += 1


def pick_row(page, rx, skip):
    rows = page.locator(ROW).filter(has_text=rx)
    for i in range(rows.count()):
        r = rows.nth(i)
        n = row_number(r) or f"row{i}"
        if n not in skip:
            return r, n
    return None, None


# --------------------------- مرحله‌ی ارسال ---------------------------
def send_pass(page, log, state):
    failed = set()
    while True:
        if STOP.is_set():
            return "stop"
        if MAX_SEND is not None and state["sent"] >= MAX_SEND:
            return "stop"
        row, num = pick_row(page, RE_UNSENT, failed)
        if row is None:
            return
        rows = page.locator(ROW).filter(has_text=RE_UNSENT)
        before = rows.count()
        try:
            click_status_button(row, RE_UNSENT)
            page.get_by_text(RE_CONFIRM_TEXT).wait_for(timeout=10000)
            page.get_by_role("button", name=RE_CONFIRM_BTN).last.click()

            deadline = time.time() + SEND_TIMEOUT
            while time.time() < deadline and rows.count() >= before:
                time.sleep(0.5)
            if rows.count() >= before:
                raise TimeoutError("وضعیت ردیف بعد از تأیید تغییر نکرد")

            state["sent"] += 1
            print(f"[ارسال] {num} ✔")
            log.writerow([num, "send", "ok", ""])
        except Exception as e:
            failed.add(num)
            print(f"[ارسال] {num} ✘ {e}")
            log.writerow([num, "send", "error", str(e)])
            try:
                page.screenshot(path=f"error_send_{num}.png")
            except Exception:
                pass
            page.keyboard.press("Escape")
        time.sleep(DELAY_BETWEEN)


# --------------------------- مرحله‌ی استعلام ---------------------------
def inquiry_pass(page, log, state):
    seen = set()
    while True:
        if STOP.is_set():
            return "stop"
        row, num = pick_row(page, RE_PENDING, seen)
        if row is None:
            return
        seen.add(num)
        try:
            click_status_button(row, RE_PENDING)
            get_modal(page).wait_for(state="visible", timeout=10000)
            page.get_by_role("button", name="استعلام وضعیت", exact=True).click()

            deadline = time.time() + INQUIRY_SETTLE
            text = modal_text(page)
            while time.time() < deadline and classify(text) == "pending":
                time.sleep(0.5)
                text = modal_text(page)

            status = classify(text)
            clean = " | ".join(x.strip() for x in text.splitlines() if x.strip())[:400]
            if status == "done":
                state["done"] += 1
                warn = "هشدار" in text
                print(f"[استعلام] {num} ✔ ثبت شد" + (" (با هشدار)" if warn else ""))
                log.writerow([num, "inquiry", "done_warning" if warn else "done", clean])
            elif status == "pending":
                state["pending"] += 1
                print(f"[استعلام] {num} … هنوز در انتظار")
                log.writerow([num, "inquiry", "pending", ""])
            else:
                state["other"] += 1
                print(f"[استعلام] {num} ⚠ وضعیت نامشخص/رد شده: {clean}")
                log.writerow([num, "inquiry", "other", clean])
                page.screenshot(path=f"inquiry_other_{num}.png")
        except Exception as e:
            state["other"] += 1
            print(f"[استعلام] {num} ✘ {e}")
            log.writerow([num, "inquiry", "error", str(e)])
            try:
                page.screenshot(path=f"error_inquiry_{num}.png")
            except Exception:
                pass
        finally:
            close_modal(page)
        time.sleep(DELAY_BETWEEN)


# ------------------------------- main -------------------------------
def main():
    fname = f"kariya_log_{datetime.now():%Y%m%d_%H%M%S}.csv"
    state = {"sent": 0, "done": 0, "pending": 0, "other": 0}

    with sync_playwright() as p, open(fname, "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["invoice", "action", "result", "detail"])

        browser = p.chromium.connect_over_cdp(CDP_URL)
        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if PAGE_URL_PART in pg.url:
                    page = pg
        if page is None:
            print("تب کاریا حساب پیدا نشد. اول لاگین کنید و صفحه‌ی «فاکتور فروش» را باز بگذارید.")
            return

        page.set_default_timeout(15000)
        page.bring_to_front()

        if DO_SEND:
            print("===== مرحله‌ی ارسال =====")
            for_each_page(page, lambda pg: send_pass(pg, log, state))

        if DO_INQUIRY and not STOP.is_set():
            for rnd in range(1, INQUIRY_ROUNDS + 1):
                print(f"\n===== مرحله‌ی استعلام (دور {rnd}) =====")
                state["pending"] = 0
                for_each_page(page, lambda pg: inquiry_pass(pg, log, state))
                if state["pending"] == 0 or STOP.is_set():
                    break
                if rnd < INQUIRY_ROUNDS:
                    print(f"{state['pending']} فاکتور هنوز در انتظار است؛ {ROUND_WAIT} ثانیه صبر…")
                    time.sleep(ROUND_WAIT)

        print("\n===== خلاصه =====")
        print(f"ارسال‌شده: {state['sent']} | ثبت‌شده: {state['done']} | "
              f"هنوز در انتظار: {state['pending']} | مشکل‌دار: {state['other']}")
        print(f"گزارش کامل: {fname}")
SEND_BTN = 'button[aria-label^="ارسال فاکتور"]'


def overlay_visible(page):
    ov = page.locator("div.overlay[role='presentation']")
    for i in range(ov.count()):
        if ov.nth(i).is_visible():
            return ov.nth(i)
    return None


def clear_overlays(page):
    for _ in range(3):
        ov = overlay_visible(page)
        if ov is None:
            return
        try:
            print("  ⚠ overlay:", ov.evaluate("e => e.outerHTML.slice(0, 200)"))
        except Exception:
            pass
        page.keyboard.press("Escape")
        time.sleep(0.5)
        ov = overlay_visible(page)
        if ov is not None:
            try:
                ov.click(position={"x": 5, "y": 5}, timeout=2000)
            except Exception:
                pass
            time.sleep(0.5)


def safe_click(page, locator):
    if page is not None:
        clear_overlays(page)
    try:
        locator.click(timeout=5000)
    except Exception:
        locator.evaluate("e => e.click()")   # کلیک مستقیم، بدون گیر کردن به overlay


def click_status_button(row, rx):
    cell = row.locator("td").filter(has_text=rx).first
    btn = cell.locator("button")
    target = btn.first if btn.count() else cell.get_by_text(rx).first
    safe_click(getattr(row, "page", None), target)


def send_pass(page, log, state):
    failed = set()
    while True:
        if STOP.is_set():
            return "stop"
        if MAX_SEND is not None and state["sent"] >= MAX_SEND:
            return "stop"

        btns = page.locator(SEND_BTN)
        target = label = num = None
        for i in range(btns.count()):
            b = btns.nth(i)
            lab = b.get_attribute("aria-label") or ""
            n = lab.replace("ارسال فاکتور", "").strip() or f"btn{i}"
            if n not in failed:
                target, label, num = b, lab, n
                break
        if target is None:
            return

        try:
            safe_click(page, target)
            page.get_by_text(RE_CONFIRM_TEXT).wait_for(timeout=10000)
            page.get_by_role("button", name=RE_CONFIRM_BTN).last.click()

            same = page.locator(f'button[aria-label="{label}"]')
            deadline = time.time() + SEND_TIMEOUT
            while time.time() < deadline and same.count() > 0:
                time.sleep(0.5)
            if same.count() > 0:
                raise TimeoutError("دکمه‌ی ارسال بعد از تأیید همچنان وجود دارد")

            state["sent"] += 1
            print(f"[ارسال] {num} ✔")
            log.writerow([num, "send", "ok", ""])
        except Exception as e:
            failed.add(num)
            print(f"[ارسال] {num} ✘ {str(e)[:200]}")
            log.writerow([num, "send", "error", str(e)[:200]])
            try:
                page.screenshot(path=f"error_send_{num}.png")
            except Exception:
                pass
            page.keyboard.press("Escape")
        time.sleep(DELAY_BETWEEN)
def overlay_visible(page):
    ov = page.locator(".personnel-overlay")
    for i in range(ov.count()):
        if ov.nth(i).is_visible():
            return ov.nth(i)
    return None


def close_modal(page):
    """پنجره‌ی سامانه مؤدیان را می‌بندد (با دکمه‌ی «بستن»)."""
    for _ in range(4):
        if overlay_visible(page) is None:
            return True
        ov = page.locator(".personnel-overlay")
        try:
            ov.get_by_role("button", name="بستن", exact=True).first.click(timeout=2000)
        except Exception:
            try:
                page.keyboard.press("Escape")
                ov.locator("button").first.evaluate("e => e.click()")
            except Exception:
                pass
        time.sleep(0.6)
    return overlay_visible(page) is None


def wait_and_close_modal(page, wait=4):
    """بعد از ارسال منتظر باز شدن پنجره می‌ماند، متنش را برمی‌گرداند و می‌بندد."""
    end = time.time() + wait
    text = ""
    while time.time() < end:
        ov = overlay_visible(page)
        if ov is not None:
            try:
                text = ov.inner_text(timeout=2000)
            except Exception:
                pass
            break
        time.sleep(0.3)
    close_modal(page)
    return " | ".join(x.strip() for x in text.splitlines() if x.strip())[:300]


def get_modal(page):
    return page.locator(".personnel-overlay").first


def modal_text(page):
    try:
        return get_modal(page).inner_text(timeout=2000)
    except Exception:
        return ""


def safe_click(page, locator):
    close_modal(page)
    try:
        locator.click(timeout=5000)
    except Exception:
        locator.evaluate("e => e.click()")


def click_status_button(row, rx):
    cell = row.locator("td").filter(has_text=rx).first
    btn = cell.locator("button")
    target = btn.first if btn.count() else cell.get_by_text(rx).first
    safe_click(row.page, target)


def next_page(page):
    close_modal(page)
    btn = page.get_by_role("button", name="بعدی", exact=True)
    if btn.count() == 0 or not btn.first.is_enabled():
        return False
    safe_click(page, btn.first)
    time.sleep(PAGE_SETTLE)
    return True


def goto_first_page(page):
    while True:
        close_modal(page)
        btn = page.get_by_role("button", name="قبلی", exact=True)
        if btn.count() == 0 or not btn.first.is_enabled():
            return
        safe_click(page, btn.first)
        time.sleep(PAGE_SETTLE)


SEND_BTN = 'button[aria-label^="ارسال فاکتور"]'


def send_pass(page, log, state):
    failed = set()
    while True:
        if STOP.is_set():
            return "stop"
        if MAX_SEND is not None and state["sent"] >= MAX_SEND:
            return "stop"

        close_modal(page)
        btns = page.locator(SEND_BTN)
        target = label = num = None
        for i in range(btns.count()):
            b = btns.nth(i)
            lab = b.get_attribute("aria-label") or ""
            n = lab.replace("ارسال فاکتور", "").strip() or f"btn{i}"
            if n not in failed:
                target, label, num = b, lab, n
                break
        if target is None:
            return

        try:
            safe_click(page, target)
            page.get_by_text(RE_CONFIRM_TEXT).wait_for(timeout=10000)
            page.get_by_role("button", name=RE_CONFIRM_BTN).last.click()

            same = page.locator(f'button[aria-label="{label}"]')
            deadline = time.time() + SEND_TIMEOUT
            while time.time() < deadline and same.count() > 0:
                time.sleep(0.5)
            if same.count() > 0:
                raise TimeoutError("دکمه‌ی ارسال بعد از تأیید همچنان وجود دارد")

            info = wait_and_close_modal(page)
            state["sent"] += 1
            print(f"[ارسال] {num} ✔")
            log.writerow([num, "send", "ok", info])
        except Exception as e:
            failed.add(num)
            print(f"[ارسال] {num} ✘ {str(e)[:200]}")
            log.writerow([num, "send", "error", str(e)[:200]])
            try:
                page.screenshot(path=f"error_send_{num}.png")
            except Exception:
                pass
            close_modal(page)
        time.sleep(DELAY_BETWEEN)
STOP.clear()
t = threading.Thread(target=main, daemon=True)
t.start()
try:
    t.join()
except KeyboardInterrupt:
    STOP.set()
    print("درخواست توقف ثبت شد؛ بعد از پایان فاکتور جاری متوقف می‌شود…")
    t.join()
