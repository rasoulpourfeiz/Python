# -*- coding: utf-8 -*-
# Kariya Hesab -> Moadian auto send + inquiry (Playwright, Windows 10)
#
# Flow:
#   1) Scan pages from the first (newest) page and collect un-sent invoices.
#      Scanning STOPS as soon as STOP_AFTER_EMPTY_PAGES consecutive pages have no
#      un-sent invoice (older pages are all "sent", so they are never checked).
#   2) Sort the collected invoices by number (smallest/oldest first).
#   3) For each invoice: SEND it -> INQUIRE that same invoice -> next invoice.
#   4) Optional extra inquiry rounds ONLY for invoices of this run still pending.

import argparse
import csv
import os
import re
import sys
import time
import traceback
import unicodedata
from datetime import datetime

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================ SETTINGS ============================
CDP_URL = "http://127.0.0.1:9222"
URL_PART = "kariyahesab.com"

DO_SEND = True
DO_INQUIRY = True
MAX_SEND = None            # None = all (can be set from the .bat with --max N)

STOP_AFTER_EMPTY_PAGES = 2 # stop scanning after this many consecutive pages with NO un-sent invoice
MAX_PAGES = 300            # hard safety limit for page walking (anti infinite loop)

SEND_TIMEOUT = 90          # seconds to wait for each send to finish
AFTER_SEND_WAIT = 5        # seconds to wait AFTER a successful send, before opening its inquiry
INQUIRY_SETTLE = 10        # seconds to wait for each inquiry answer
INQUIRY_ROUNDS = 2         # inquiry rounds for invoices still pending
ROUND_WAIT = 45            # seconds between inquiry rounds
PAGE_WAIT_MAX = 12         # max seconds to wait for the table to change after clicking next/prev
PAGE_SETTLE = 2.0          # extra seconds after the table changed (let buttons render)
DELAY_BETWEEN = 4.0        # pause between invoices (increase if Moadian still errors out)
# ================================================================

Z = r"[\s\u200c]*"
RE_PENDING = re.compile(rf"در{Z}انتظار|ارسال{Z}شده")
RE_DONE = re.compile(rf"ثبت{Z}در{Z}سامانه")
RE_CONFIRM_TEXT = re.compile(r"سامانه\s*م.{1,2}دیان\s*فرستاده\s*شود")
RE_CONFIRM_BTN = re.compile(r"^\s*ت\S{0,2}ی+د\s*$")
SEND_BTN = 'button[aria-label^="ارسال فاکتور"]'

_FA2EN_JS = r"""const fa2en = (s) => s.replace(/[\u06F0-\u06F9\u0660-\u0669]/g,
                                 d => String(d.charCodeAt(0) & 0xF));"""

# Index of the <tr> whose invoice-number cell ends with `wanted` (ASCII digits).
JS_FIND_ROW_BY_NUMBER = r"""
(wanted) => {
  """ + _FA2EN_JS + r"""
  const trs = document.querySelectorAll('tr');
  for (let i = 0; i < trs.length; i++) {
    const tds = trs[i].querySelectorAll('td');
    for (const td of tds) {
      const t = fa2en(td.textContent.trim());
      if (/^[0-9]{8,14}$/.test(t) && t.endsWith(wanted)) return i;
    }
  }
  return -1;
}
"""

# "Signature" of the current table page = list of invoice numbers shown.
# Used to know whether next/prev really changed the page (loop guard).
JS_PAGE_SIG = r"""
() => {
  """ + _FA2EN_JS + r"""
  const out = [];
  document.querySelectorAll('tr').forEach(tr => {
    for (const td of tr.querySelectorAll('td')) {
      const t = fa2en(td.textContent.trim());
      if (/^[0-9]{8,14}$/.test(t)) { out.push(t); break; }
    }
  });
  return out.join(',');
}
"""


def say(msg):
    print(msg)
    sys.stdout.flush()


def a(s):
    """Convert any Unicode digits (Persian/Arabic) to ASCII digits."""
    out = []
    for c in (s or ""):
        if c.isdigit():
            try:
                out.append(str(unicodedata.digit(c)))
                continue
            except ValueError:
                pass
        out.append(c)
    return "".join(out)


def num_key(n):
    d = re.sub(r"[^0-9]", "", a(n))
    return int(d) if d else 10 ** 18


# --------------------------- overlay ("سامانه مؤدیان" popup) ---------------------------
def overlay(page):
    ov = page.locator(".personnel-overlay")
    for i in range(ov.count()):
        if ov.nth(i).is_visible():
            return ov.nth(i)
    return None


def overlay_text(page):
    ov = overlay(page)
    if ov is None:
        return None
    try:
        return ov.inner_text(timeout=2000)
    except Exception:
        return ""


def close_overlay(page):
    for _ in range(4):
        ov = overlay(page)
        if ov is None:
            return True
        try:
            ov.get_by_role("button", name="بستن", exact=True).first.click(timeout=2000)
        except Exception:
            try:
                page.keyboard.press("Escape")
                ov.locator("button").first.evaluate("e => e.click()")
            except Exception:
                pass
        time.sleep(0.6)
    return overlay(page) is None


def wait_and_close_overlay(page, wait=4):
    text = ""
    end = time.time() + wait
    while time.time() < end:
        t = overlay_text(page)
        if t is not None:
            text = t
            break
        time.sleep(0.3)
    close_overlay(page)
    return " | ".join(x.strip() for x in text.splitlines() if x.strip())[:300]


def safe_click(page, locator):
    close_overlay(page)
    try:
        locator.click(timeout=5000)
    except Exception:
        locator.evaluate("e => e.click()")


def wait_for_refresh(page, timeout=15):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except Exception:
        pass
    time.sleep(0.5)


def classify(text):
    if "هنوز جوابی" in text:
        return "pending"
    if RE_DONE.search(text):
        return "done"
    return "other"


# --------------------------- paging (with loop guard) ---------------------------
def page_sig(page):
    try:
        return page.evaluate(JS_PAGE_SIG)
    except Exception:
        return ""


def turn_page(page, name):
    """
    Click the 'next'/'previous' button. Returns True ONLY if the table content
    really changed. If the button is missing/disabled, or the click did not change
    the table (we are at a boundary), returns False -> callers never loop forever.
    """
    close_overlay(page)
    btn = page.get_by_role("button", name=name, exact=True)
    if btn.count() == 0 or not btn.first.is_enabled():
        return False
    before = page_sig(page)
    safe_click(page, btn.first)
    end = time.time() + PAGE_WAIT_MAX
    while time.time() < end:
        time.sleep(0.4)
        if page_sig(page) != before:
            time.sleep(PAGE_SETTLE)
            return True
    return False


def next_page(page):
    return turn_page(page, "بعدی")


def prev_page(page):
    return turn_page(page, "قبلی")


def goto_first_page(page):
    for _ in range(MAX_PAGES):
        if not prev_page(page):
            return


def find_row_index(page, wanted):
    return page.evaluate(JS_FIND_ROW_BY_NUMBER, a(wanted))


def goto_page_of_invoice(page, wanted, limit):
    """
    Make the page holding invoice `wanted` the visible one.
    1) fast path: it is already on the current page
    2) otherwise go to page 1 and walk forward, but NEVER beyond `limit` pages
       (older pages are not scanned at all).
    """
    wanted = a(wanted)
    if find_row_index(page, wanted) >= 0:
        return True
    goto_first_page(page)
    pos = 1
    while True:
        if find_row_index(page, wanted) >= 0:
            return True
        if pos >= limit or pos >= MAX_PAGES:
            return False
        if not next_page(page):
            return False
        pos += 1


def locate_row(page, n, limit):
    if not goto_page_of_invoice(page, n, limit):
        return None
    idx = find_row_index(page, n)
    if idx is None or idx < 0:
        return None
    return page.locator("tr").nth(idx)


def click_status_button(row, rx):
    cell = row.locator("td").filter(has_text=rx).first
    btn = cell.locator("button")
    target = btn.first if btn.count() else cell.get_by_text(rx).first
    safe_click(row.page, target)


def screenshot(page, name):
    try:
        page.screenshot(path=name)
    except Exception:
        pass


# ------------------------------ send one invoice ------------------------------
def send_one(page, log, st, target, label, num):
    """Click the send button, confirm, and wait for it to disappear. Returns True on success."""
    try:
        safe_click(page, target)
        page.get_by_text(RE_CONFIRM_TEXT).wait_for(timeout=10000)
        page.get_by_role("button", name=RE_CONFIRM_BTN).last.click()

        same = page.locator('button[aria-label="%s"]' % label)
        deadline = time.time() + SEND_TIMEOUT
        while time.time() < deadline and same.count() > 0:
            time.sleep(0.5)
        if same.count() > 0:
            raise TimeoutError("send button still present after confirm")

        info = wait_and_close_overlay(page)
        st["sent"] += 1
        say("[SEND] %s OK" % a(num))
        log.writerow([a(num), "send", "ok", info])
        return True
    except Exception as e:
        say("[SEND] %s FAILED: %s" % (a(num), str(e)[:150]))
        log.writerow([a(num), "send", "error", str(e)[:200]])
        screenshot(page, "error_send_%s.png" % a(num))
        close_overlay(page)
        return False


# ------------------------------ inquire one invoice ------------------------------
def inquire_one(page, log, st, row, num):
    """Open the status popup for this row, click 'استعلام وضعیت', read the result."""
    try:
        click_status_button(row, RE_PENDING)
        end = time.time() + 10
        while time.time() < end and overlay(page) is None:
            time.sleep(0.3)
        if overlay(page) is None:
            raise TimeoutError("status window did not open")

        if not page.evaluate(
            """() => {
                const ov = [...document.querySelectorAll('.personnel-overlay')]
                    .find(o => o.getBoundingClientRect().width > 0);
                if (!ov) return false;
                const b = [...ov.querySelectorAll('button')]
                    .find(x => x.textContent.trim() === 'استعلام وضعیت');
                if (!b) return false;
                b.click(); return true;
            }"""
        ):
            raise TimeoutError("inquiry button not found")

        text = overlay_text(page) or ""
        deadline = time.time() + INQUIRY_SETTLE
        while time.time() < deadline and classify(text) == "pending":
            time.sleep(0.5)
            text = overlay_text(page) or ""

        status = classify(text)
        clean = " | ".join(x.strip() for x in text.splitlines() if x.strip())[:400]
        if status == "done":
            st["done"] += 1
            warn = "هشدار" in text
            say("[INQUIRY] %s DONE%s" % (a(num), " (with warning)" if warn else ""))
            log.writerow([a(num), "inquiry", "done_warning" if warn else "done", clean])
        elif status == "pending":
            st["pending"] += 1
            say("[INQUIRY] %s still pending" % a(num))
            log.writerow([a(num), "inquiry", "pending", ""])
        else:
            st["other"] += 1
            say("[INQUIRY] %s UNKNOWN/REJECTED (see CSV)" % a(num))
            log.writerow([a(num), "inquiry", "other", clean])
            screenshot(page, "inquiry_other_%s.png" % a(num))
        return status
    except Exception as e:
        st["other"] += 1
        say("[INQUIRY] %s FAILED: %s" % (a(num), str(e)[:150]))
        log.writerow([a(num), "inquiry", "error", str(e)[:200]])
        screenshot(page, "error_inquiry_%s.png" % a(num))
        return "other"
    finally:
        close_overlay(page)


# -------------------- collect un-sent invoices (limited scan) --------------------
def collect_unsent_numbers(page):
    """
    Walk pages from page 1 (newest). Stop when STOP_AFTER_EMPTY_PAGES consecutive
    pages contain no un-sent invoice. Returns (list_of_numbers, pages_scanned).
    """
    numbers = []
    seen = set()
    goto_first_page(page)
    page_no = 1
    empty_streak = 0
    while True:
        close_overlay(page)
        btns = page.locator(SEND_BTN)
        cnt = btns.count()
        for i in range(cnt):
            lab = btns.nth(i).get_attribute("aria-label") or ""
            n = a(lab.replace("ارسال فاکتور", "").strip())
            if n and n not in seen:
                seen.add(n)
                numbers.append(n)
        say("  page %d: %d un-sent button(s)" % (page_no, cnt))

        empty_streak = empty_streak + 1 if cnt == 0 else 0
        if empty_streak >= STOP_AFTER_EMPTY_PAGES:
            say("  %d consecutive pages without un-sent invoices -> stop scanning."
                % STOP_AFTER_EMPTY_PAGES)
            break
        if page_no >= MAX_PAGES:
            say("  reached MAX_PAGES, stop scanning.")
            break
        if not next_page(page):
            say("  last page reached.")
            break
        page_no += 1
    return numbers, page_no


def send_all_in_order(page, log, st):
    """
    Smallest invoice number first. For EACH invoice:
        1) send it
        2) wait for the table to refresh
        3) inquire that same invoice
        4) only then move to the next invoice
    Returns the list of invoice numbers whose inquiry is still 'pending'
    plus the page limit used for locating rows.
    """
    say("Scanning for un-sent invoices ...")
    unsent, scanned = collect_unsent_numbers(page)
    limit = scanned + 1            # small slack in case a new invoice shifts rows
    pending_nums = []
    if not unsent:
        say("No un-sent invoices found.")
        return pending_nums, limit
    unsent.sort(key=num_key)

    say("\nFound %d un-sent invoice(s) in %d page(s). Processing order (smallest first):"
        % (len(unsent), scanned))
    head = unsent[:10]
    for n in head:
        say("  %s" % n)
    if len(unsent) > len(head):
        say("  ... (+%d more)" % (len(unsent) - len(head)))

    for n in unsent:
        if MAX_SEND is not None and st["sent"] >= MAX_SEND:
            say("Reached --max limit (%d). Stopping send phase." % MAX_SEND)
            break

        say("\n=== invoice %s ===" % n)
        close_overlay(page)

        # ---- 1) SEND ----
        row = locate_row(page, n, limit)
        if row is None:
            say("[SEND] %s not found in the scanned pages, skipping" % n)
            log.writerow([n, "send", "skip", "not in table"])
            continue

        btn = row.locator(SEND_BTN)
        if btn.count() == 0:
            say("[SEND] %s already sent, skipping send" % n)
            log.writerow([n, "send", "skip", "already sent"])
        else:
            label = btn.first.get_attribute("aria-label") or ""
            if not send_one(page, log, st, btn.first, label, n):
                time.sleep(DELAY_BETWEEN)
                continue
            say("waiting for refresh before checking %s ..." % n)
            wait_for_refresh(page)
            time.sleep(AFTER_SEND_WAIT)

        # ---- 2) INQUIRY of the same invoice ----
        if DO_INQUIRY:
            row = locate_row(page, n, limit)
            if row is None:
                say("[INQUIRY] %s row not found for inquiry" % n)
                log.writerow([n, "inquiry", "error", "row not found"])
            elif inquire_one(page, log, st, row, n) == "pending":
                pending_nums.append(n)

        # ---- 3) next invoice ----
        time.sleep(DELAY_BETWEEN)
    return pending_nums, limit


# ------------------------- extra rounds ONLY for this run's pending invoices -------------------------
def inquiry_round(page, log, st, nums, limit):
    still = []
    for n in nums:
        close_overlay(page)
        row = locate_row(page, n, limit)
        if row is None:
            say("[INQUIRY] %s row not found" % n)
            log.writerow([n, "inquiry", "error", "row not found"])
            continue
        if inquire_one(page, log, st, row, n) == "pending":
            still.append(n)
        time.sleep(DELAY_BETWEEN)
    return still


# --------------------------------- main ---------------------------------
def main():
    print(">>> kariya bot starting ...", flush=True)
    global MAX_SEND
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="max invoices to send (test)")
    args = ap.parse_args()
    if args.max:
        MAX_SEND = args.max

    here = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(here, "kariya_log_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    st = {"sent": 0, "done": 0, "pending": 0, "other": 0}

    with sync_playwright() as p, open(fname, "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["invoice", "action", "result", "detail"])

        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            say("Could not connect to Chrome on %s: %s" % (CDP_URL, e))
            say("Make sure the bot's Chrome window (opened by the .bat) is still open,")
            say("and that Chrome was started with --remote-debugging-port=9222 AND a")
            say('separate --user-data-dir (required since Chrome 136), e.g. --user-data-dir="C:\\kariya_profile"')
            say("Test: open http://127.0.0.1:9222/json/version in a browser tab.")
            return 1

        page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if URL_PART in pg.url:
                    page = pg
        if page is None:
            say("Kariya tab not found. Log in and open the Sales Invoices page first.")
            return 1

        page.set_default_timeout(15000)
        page.bring_to_front()

        try:
            pending_nums, limit = [], 1
            if DO_SEND:
                say("===== SEND + INQUIRY (smallest invoice first, one by one) =====")
                pending_nums, limit = send_all_in_order(page, log, st)

            if DO_INQUIRY:
                for rnd in range(2, INQUIRY_ROUNDS + 1):
                    if not pending_nums:
                        break
                    say("\n===== EXTRA INQUIRY ROUND %d (%d still pending) ====="
                        % (rnd, len(pending_nums)))
                    say("waiting %d s before re-checking..." % ROUND_WAIT)
                    time.sleep(ROUND_WAIT)
                    st["pending"] = 0
                    pending_nums = inquiry_round(page, log, st, pending_nums, limit)
        except KeyboardInterrupt:
            say("\nStopped by user.")

    say("\n===== SUMMARY =====")
    say("sent: %d | registered: %d | still pending: %d | problems: %d"
        % (st["sent"], st["done"], st["pending"], st["other"]))
    say("full report: %s" % fname)
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException:
        print("\n" + "=" * 60)
        print("UNEXPECTED ERROR - full traceback below:")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
    finally:
        try:
            input("\nPress Enter to close this window ...")
        except Exception:
            pass
    sys.exit(rc)
