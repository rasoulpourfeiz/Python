# راهنمای اسکریپت اتوماسیون کاریا حساب با Playwright

این اسکریپت برای اتوماسیون مراحل **ارسال فاکتور** و **استعلام وضعیت** در سامانه کاریا حساب (new.kariyahesab.com) با استفاده از Playwright نوشته شده است.  
اتصال به مرورگر از طریق CDP انجام می‌شود؛ بنابراین نیازی به اجرای مرورگر جدید توسط Playwright نیست و از تب باز و لاگین‌شدهٔ شما استفاده می‌کند.

---

## پیش‌نیازها

- Python 3.8 یا بالاتر
- نصب پکیج Playwright:

```bash
pip install playwright
یک مرورگر Chromium-based (Chrome/Edge) که با پورت دیباگ باز شده باشد.

لاگین بودن در سامانه کاریا حساب و باز بودن صفحهٔ فاکتور فروش.

اجرای مرورگر با CDP
مرورگر را با دستور زیر اجرا کنید تا پورت 9222 فعال شود:

bash
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug"
یا برای Edge:

bash
msedge.exe --remote-debugging-port=9222 --user-data-dir="C:\edge-debug"
سپس در مرورگر باز شده، وارد سایت https://new.kariyahesab.com/acc شوید و صفحهٔ مربوط به فاکتور فروش را باز بگذارید.

تنظیمات
در ابتدای اسکریپت، بخش تنظیمات قرار دارد. مقادیر مهم:

متغیر	توضیح	مقدار پیشنهادی
CDP_URL	آدرس اتصال به مرورگر	http://127.0.0.1:9222
PAGE_URL_PART	بخشی از URL صفحهٔ هدف	https://new.kariyahesab.com/acc
DO_SEND	فعال‌سازی مرحلهٔ ارسال	True
DO_INQUIRY	فعال‌سازی مرحلهٔ استعلام	True
MAX_SEND	حداکثر تعداد ارسال (برای تست)	None یا عدد مثل 1
SEND_TIMEOUT	حداکثر انتظار برای پایان ارسال هر فاکتور (ثانیه)	90
INQUIRY_SETTLE	حداکثر انتظار برای پاسخ استعلام (ثانیه)	6
INQUIRY_ROUNDS	تعداد دورهای استعلام	2
ROUND_WAIT	فاصله بین دورهای استعلام (ثانیه)	30
PAGE_SETTLE	صبر بعد از تغییر صفحه (ثانیه)	2
DELAY_BETWEEN	مکث بین فاکتورها (ثانیه)	1.0
ROW	سلکتور ردیف‌های جدول	"tr"
نحوه اجرا
پس از تنظیم مقادیر، اسکریپت را اجرا کنید:

bash
python script.py
برای توقف، کلید Ctrl+C را بزنید. اسکریپت پس از پایان فاکتور جاری متوقف می‌شود.

خروجی
یک فایل CSV با نام kariya_log_YYYYMMDD_HHMMSS.csv ساخته می‌شود.

ستون‌های CSV:

ستون	توضیح
invoice	شماره فاکتور
action	نوع عملیات (send یا inquiry)
result	نتیجه (ok, done, pending, error, ...)
detail	توضیحات یا متن خطا
در صورت بروز خطا، اسکرین‌شات‌هایی با نام‌هایی مثل error_send_*.png یا inquiry_other_*.png ذخیره می‌شوند.

ساختار و توابع مهم
ابزارهای کمکی
row_number(row): استخراج شماره فاکتور از یک ردیف جدول.

click_status_button(row, rx): کلیک روی دکمهٔ وضعیت با متن مطابق الگو.

get_modal(page): دریافت مودال فعال.

modal_text(page): خواندن متن مودال.

close_modal(page): بستن مودال.

classify(text): تشخیص وضعیت استعلام (pending، done، other).

next_page(page) / goto_first_page(page): جابجایی بین صفحات.

for_each_page(page, fn): اجرای یک تابع روی همهٔ صفحات.

pick_row(page, rx, skip): انتخاب ردیفی که با الگو match می‌شود و در لیست skip نیست.

مراحل اصلی
send_pass(page, log, state): ارسال فاکتورهای «ارسال نشده».

inquiry_pass(page, log, state): استعلام فاکتورهای «در انتظار» یا «ارسال شده».

main(): مدیریت اتصال، اجرای مراحل و نوشتن گزارش.

نکات مهم
کد فعلی دارای تعریف‌های تکراری برای برخی توابع است (مثل send_pass، click_status_button، close_modal). در پایتون آخرین تعریف هر تابع اعمال می‌شود؛ بنابراین بهتر است نسخهٔ نهایی تمیز و یکپارچه شود.

اگر جدول از div ساخته شده باشد، مقدار ROW را از "tr" به سلکتور مناسب تغییر دهید.

برای تست، MAX_SEND را روی 1 یا 2 بگذارید و بعد از تست آن را None کنید.

اتصال CDP نیازمند باز بودن مرورگر با پورت دیباگ است. اگر مرورگر بسته شود، اسکریپت خطا می‌دهد.

عیب‌یابی
مشکل	راه‌حل
تب کاریا حساب پیدا نشد	مطمئن شوید مرورگر با --remote-debugging-port=9222 باز است و تب مورد نظر در آدرس PAGE_URL_PART قرار دارد.
دکمه‌ها کلیک نمی‌شوند	ممکن است overlay باز باشد. توابع close_modal و clear_overlays برای همین کار تعبیه شده‌اند.
تایم‌اوت در ارسال	مقدار SEND_TIMEOUT را افزایش دهید.
استعلام نامشخص	متن مودال در CSV و اسکرین‌شات ذخیره می‌شود؛ بر اساس آن سلکتورها را اصلاح کنید.
خطای مربوط به Playwright	مطمئن شوید pip install playwright انجام شده است.
نمونه تنظیمات سریع
python
CDP_URL = "http://127.0.0.1:9222"
PAGE_URL_PART = "https://new.kariyahesab.com/acc"

DO_SEND = True
DO_INQUIRY = True
MAX_SEND = None          # برای تست: 1 یا 2

SEND_TIMEOUT = 90
INQUIRY_SETTLE = 6
INQUIRY_ROUNDS = 2
ROUND_WAIT = 30
PAGE_SETTLE = 2
DELAY_BETWEEN = 1.0

ROW = "tr"
توقف اجرا
در حین اجرا می‌توانید Ctrl+C بزنید. اسکریپت با استفاده از threading.Event به نام STOP درخواست توقف را ثبت می‌کند و پس از پایان فاکتور جاری متوقف می‌شود.
