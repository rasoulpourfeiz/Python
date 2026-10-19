"""تبدیل تاریخ شمسی/میلادی — همان الگوریتم ۳۳ ساله‌ای که در فایل اکسل شما استفاده شده است."""
import re
from datetime import date, datetime, timedelta

_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"


def to_en_digits(s):
    s = str(s)
    for i, (a, b) in enumerate(zip(_FA, _AR)):
        s = s.replace(a, str(i)).replace(b, str(i))
    return s


def _leap_days(L):
    return (L // 33) * 8 + ((L % 33) + 3) // 4


def is_leap(jy):
    L = jy + 1595
    return _leap_days(L + 1) - _leap_days(L) == 1


def month_length(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap(jy) else 29


def to_gregorian(jy, jm, jd):
    L = jy + 1595
    days = (-355668 + 365 * L + _leap_days(L) + jd
            + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186))
    gy = 400 * (days // 146097)
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
    return date(gy, 1, 1) + timedelta(days=days)


def to_jalali(d):
    if isinstance(d, datetime):
        d = d.date()
    jy = d.year - 621
    start = to_gregorian(jy, 1, 1)
    if d < start:
        jy -= 1
        start = to_gregorian(jy, 1, 1)
    elif d >= to_gregorian(jy + 1, 1, 1):
        jy += 1
        start = to_gregorian(jy, 1, 1)
    doy = (d - start).days
    if doy < 186:
        return jy, doy // 31 + 1, doy % 31 + 1
    doy -= 186
    return jy, doy // 30 + 7, doy % 30 + 1


def fmt(d):
    """date -> '1405/03/14' (خالی اگر None)"""
    if not d:
        return ""
    jy, jm, jd = to_jalali(d)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def parse(s):
    """'1405/03/14' (ارقام فارسی هم مجاز) یا تاریخ میلادی -> date"""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    t = to_en_digits(s).strip()
    m = re.fullmatch(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", t)
    if not m:
        raise ValueError(f"تاریخ نامعتبر است: «{t}» (فرمت درست: 1405/03/14)")
    y, mo, d = map(int, m.groups())
    if y >= 1700:  # میلادی
        return date(y, mo, d)
    if not (1 <= mo <= 12 and 1 <= d <= month_length(y, mo)):
        raise ValueError(f"تاریخ نامعتبر است: «{t}»")
    return to_gregorian(y, mo, d)


def add_one_month(d):
    """یک ماه شمسی بعد؛ اگر روز در ماه مقصد نبود، به آخرین روز آن ماه محدود می‌شود."""
    jy, jm, jd = to_jalali(d)
    jy, jm = (jy + 1, 1) if jm == 12 else (jy, jm + 1)
    return to_gregorian(jy, jm, min(jd, month_length(jy, jm)))


def add_months(d, k):
    """k ماه شمسی بعد از d؛ همیشه نسبت به روزِ خودِ d (اگر روز در ماه مقصد نبود، آخرین روز ماه)."""
    jy, jm, jd = to_jalali(d)
    t = jm - 1 + k
    jy, jm = jy + t // 12, t % 12 + 1
    return to_gregorian(jy, jm, min(jd, month_length(jy, jm)))
