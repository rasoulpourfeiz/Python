"""سیستم محاسبه سود سرمایه‌گذاری (برنامه‌ی دسکتاپی)

  python app.py                  اجرای برنامه
  python app.py remind           چاپ و اعلان سررسیدهای امروز/فردا/گذشته (برای زمان‌بند سیستم)
  python app.py import فایل.xlsm  ورود اطلاعات از فایل اکسل قبلی (بدون باز کردن برنامه)
"""
import platform
import subprocess
import sys
from datetime import date

import core
import jalali as J


def notify(title, msg):
    """اعلان دسکتاپ (مک/ویندوز/لینوکس)؛ در صورت خطا بی‌صدا رد می‌شود."""
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            esc = lambda s: s.replace("\\", "\\\\").replace('"', "'")
            subprocess.run(["osascript", "-e", f'display notification "{esc(msg)}" with title "{esc(title)}"'], timeout=10)
        elif sysname == "Windows":
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;"
                  "$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  f"$n.ShowBalloonTip(15000,'{title}','{msg}',[System.Windows.Forms.ToolTipIcon]::Info);"
                  "Start-Sleep 15;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
        else:
            subprocess.run(["notify-send", title, msg], timeout=10)
    except Exception:
        pass


def remind():
    con = core.connect()
    today = date.today()
    rep = core.reports(con, today)
    parts, lines = [], [f"تاریخ امروز: {J.fmt(today)}"]
    for key, label in (("overdue", "سررسید گذشته"), ("today", "سررسید امروز"), ("tomorrow", "سررسید فردا")):
        rows = rep[key]
        if rows:
            parts.append(f"{label}: {len(rows)} مورد")
            lines.append(f"\n{label} ({len(rows)} مورد):")
            lines += [f"  {r['first_name']} {r['last_name']} — {r['due']} — {r['interest_due']:,} ریال" for r in rows]
    if not parts:
        print(lines[0] + "\nسررسیدی وجود ندارد.")
        return
    print("\n".join(lines))
    notify("یادآور سود سرمایه‌گذاری", " | ".join(parts))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "gui"
    if cmd == "remind":
        remind()
    elif cmd == "import" and len(sys.argv) > 2:
        r = core.import_excel(core.connect(), sys.argv[2])
        print(f"سرمایه‌گذار: {r['investors']} | تراکنش: {r['transactions']} | پرداخت سود: {r['payments']}")
        for w in r["warnings"]:
            print(" ⚠", w)
    else:
        try:
            import tkinter  # noqa
        except ImportError:
            sys.exit("Tkinter نصب نیست. ویندوز/مک: پایتون را از python.org نصب کنید. "
                     "مک با Homebrew: brew install python-tk")
        import gui
        gui.run()
