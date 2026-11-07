"""ابزارهای متن، عدد و تاریخ شمسی (بدون وابستگی بیرونی)."""
from __future__ import annotations

import datetime as _dt
import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه",
    "\u200c": " ", "\u00a0": " ", "\u200f": "", "\u200e": "",
})
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def norm_digits(s) -> str:
    return str(s).translate(_DIGIT_MAP)


def norm_text(s) -> str:
    """یکسان‌سازی ی/ک عربی، ارقام، نیم‌فاصله و فاصله‌های اضافی (برای مقایسه)."""
    if s is None:
        return ""
    s = norm_digits(s).translate(_CHAR_MAP)
    return re.sub(r"\s+", " ", s).strip().lower()


def clean_display(s) -> str:
    """پاک‌سازی نمایشی: فاصله‌های ابتدا/انتها و ی/ک عربی."""
    if s is None:
        return ""
    s = str(s).translate(str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"}))
    return re.sub(r"[ \t]+", " ", s).strip()


def norm_code(v) -> str:
    """کد کالا همیشه به صورت متن یکسان: 17.0 → '17'."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return norm_digits(str(v)).strip()


def parse_number(s) -> float | None:
    """عدد را از متن (با کاما، ارقام فارسی) می‌خواند؛ در صورت خطا None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = norm_digits(s).replace(",", "").replace("٬", "").replace("٫", ".").strip()
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fmt_num(x, dec: int = 0) -> str:
    if x is None or x == "":
        return ""
    try:
        return f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return str(x)


def mround(x: float, m: float) -> float:
    """معادل MROUND اکسل (گرد کردن به نزدیک‌ترین مضرب)."""
    if not m:
        return x
    import math
    return math.floor(x / m + 0.5) * m


# ---------------- تقویم شمسی ----------------
def g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def j2g(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + 78 + jd
            + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186))
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    sal = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal[gm]:
        gd -= sal[gm]
        gm += 1
    return gy, gm, gd


def _j_days_in_month(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    gy, gm, gd = j2g(jy, 12, 30)
    return 30 if g2j(gy, gm, gd) == (jy, 12, 30) else 29


def norm_date(v) -> str | None:
    """تاریخ شمسی معتبر را به 'YYYY/MM/DD' برمی‌گرداند؛ نامعتبر → None.
    ورودی می‌تواند متن (۱۴۰۵/۷/۲۶، 1405-07-26، 14050726)، datetime میلادی یا عدد باشد."""
    if v is None or v == "":
        return None
    if isinstance(v, (_dt.datetime, _dt.date)):
        jy, jm, jd = g2j(v.year, v.month, v.day)
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    s = norm_digits(v).strip()
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    m = re.fullmatch(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", s)
    if not m:
        m2 = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
        if not m2:
            return None
        m = m2
    y, mo, d = (int(x) for x in m.groups())
    if y > 1700:  # تاریخ میلادی متنی
        try:
            jy, jm, jd = g2j(y, mo, d)
        except Exception:
            return None
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    if not (1 <= mo <= 12) or d < 1 or d > _j_days_in_month(y, mo):
        return None
    return f"{y:04d}/{mo:02d}/{d:02d}"


def date_key(s: str) -> int | None:
    n = norm_date(s)
    return int(n.replace("/", "")) if n else None
