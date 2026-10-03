# 🐍 پروژه‌های پایتون من / My Python Projects

<div align="center">

![Python](https://img.shields.io/badge/Python-3.7%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Projects](https://img.shields.io/badge/Projects-Multiple-4B8BBE?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-success?style=for-the-badge)

**مجموعه‌ای از پروژه‌های پایتون، هر کدام در پوشهٔ اختصاصی خود با README مستقل**  
**A collection of Python projects, each in its own folder with an independent README**

</div>

---

## 📖 دربارهٔ این مخزن / About This Repository

<div dir="rtl">

این مخزن یک **Monorepo** است که در آن تمام پروژه‌های پایتون من به‌صورت **فولدر بندی‌شده** نگهداری می‌شوند. هر پوشه یک پروژهٔ کاملاً مستقل است که شامل کد منبع، فایل `README` اختصاصی، و در صورت نیاز فایل‌های تنظیمات، نمونه داده، و اسکریپت‌های اجرایی می‌باشد.

هدف این ساختار:

- 🔹 **جداسازی تمیز** پروژه‌ها از یکدیگر
- 🔹 **مستندسازی مستقل** هر پروژه با README مخصوص خود
- 🔹 **نصب و اجرای ساده** هر پروژه بدون نیاز به پیکربندی کل مخزن
- 🔹 **قابلیت توسعهٔ آسان** و افزودن پروژه‌های جدید در آینده

</div>

This repository is a **monorepo** where all my Python projects are kept in **separate folders**. Each folder is a fully independent project containing source code, its own `README`, and — when needed — configuration files, sample data, and execution scripts.

---

## 🗂️ ساختار مخزن / Repository Structure

```text
python-projects/
│
├── project-1/
│   ├── README.md            # مستندات اختصاصی پروژه
│   ├── main.py              # نقطهٔ ورود برنامه
│   ├── requirements.txt     # وابستگی‌های پروژه
│   ├── src/                 # کد منبع (اختیاری)
│   ├── data/                # نمونه داده یا فایل‌های ورودی
│   └── tests/               # تست‌ها (اختیاری)
│
├── project-2/
│   ├── README.md
│   ├── main.py
│   ├── requirements.txt
│   └── ...
│
├── project-3/
│   ├── README.md
│   ├── main.py
│   ├── requirements.txt
│   └── ...
│
├── LICENSE                  # مجوز کلی مخزن
├── .gitignore               # فایل‌های نادیده گرفته‌شده
└── README.md                # همین فایل (فهرست کلی)
```

> 📌 هر پوشه کاملاً **Self-Contained** است؛ یعنی برای اجرای یک پروژه، نیازی به نصب یا مطالعهٔ بقیهٔ پوشه‌ها ندارید.

---

## 🚀 شروع سریع / Quick Start

<div dir="rtl">

### ۱) کلون کردن مخزن

</div>

```bash
git clone https://github.com/username/python-projects.git
cd python-projects
```

<div dir="rtl">

### ۲) انتخاب پروژه

وارد پوشهٔ پروژهٔ مورد نظر شوید:

</div>

```bash
cd project-folder-name
```

<div dir="rtl">

### ۳) ساخت محیط مجازی (توصیه می‌شود)

</div>

```bash
# ویندوز
python -m venv venv
venv\Scripts\activate

# لینوکس / مک
python3 -m venv venv
source venv/bin/activate
```

<div dir="rtl">

### ۴) نصب وابستگی‌ها

</div>

```bash
pip install -r requirements.txt
```

<div dir="rtl">

### ۵) اجرای پروژه

طبق دستورالعمل موجود در `README` همان پوشه عمل کنید. معمولاً:

</div>

```bash
python main.py
```

---

## 🧰 پیش‌نیازهای کلی / General Prerequisites

| مورد | حداقل نسخه | توضیح |
|---|---|---|
| Python | 3.7+ | زبان اصلی پروژه‌ها |
| pip | آخرین نسخه | مدیریت پکیج‌ها |
| venv | همراه پایتون | محیط مجازی |
| Git | آخرین نسخه | برای کلون و مدیریت نسخه |
| OS | Windows / Linux / macOS | بسته به پروژه ممکن است محدودیت وجود داشته باشد |

> ⚠️ برخی پروژه‌ها ممکن است فقط روی **ویندوز** اجرا شوند (مثلاً آن‌هایی که با `pygetwindow` یا شبیه‌سازی کلید کار می‌کنند). این موضوع در `README` هر پروژه ذکر شده است.

---

## 📋 فهرست پروژه‌ها / Projects Index

<div dir="rtl">

در جدول زیر می‌توانید فهرست پروژه‌ها را ببینید. (این جدول را می‌توانید به‌روزرسانی کنید.)

</div>

| # | پوشه | توضیح کوتاه | وضعیت | README |
|:-:|---|---|:-:|---|
| 1 | `project-1/` | توضیح کوتاه پروژهٔ اول | ✅ فعال | [مشاهده](./project-1/README.md) |
| 2 | `project-2/` | توضیح کوتاه پروژهٔ دوم | ✅ فعال | [مشاهده](./project-2/README.md) |
| 3 | `project-3/` | توضیح کوتاه پروژهٔ سوم | 🚧 در حال توسعه | [مشاهده](./project-3/README.md) |
| … | … | … | … | … |

**راهنمای وضعیت‌ها:**

- ✅ **فعال** — پروژهٔ کامل و قابل استفاده
- 🚧 **در حال توسعه** — بخش‌هایی هنوز تکمیل نشده
- 🧪 **آزمایشی** — برای اهداف تستی یا نمونه
- ⛔ **متوقف‌شده** — دیگر توسعه داده نمی‌شود

---

## 🏗️ ساختار استاندارد هر پروژه / Standard Project Layout

<div dir="rtl">

هر پروژه در این مخزن سعی می‌کند از یک ساختار استاندارد پیروی کند:

</div>

```text
project-name/
│
├── README.md              # توضیحات کامل پروژه
├── requirements.txt       # وابستگی‌ها
├── main.py                # نقطهٔ ورود اصلی
├── config/                # فایل‌های تنظیمات
├── src/                   # ماژول‌های اصلی کد
├── data/                  # داده‌های نمونه یا ورودی
├── output/                # خروجی‌ها (لاگ، CSV، اکسل و ...)
├── tests/                 # تست‌ها
└── .gitignore             # فایل‌های نادیده گرفته‌شده
```

---

## 🛠️ تکنولوژی‌ها و کتابخانه‌ها / Technologies & Libraries

<div dir="rtl">

پروژه‌های این مخزن ممکن است از کتابخانه‌ها و ابزارهای زیر استفاده کنند:

</div>

| دسته‌بندی | کتابخانه‌ها |
|---|---|
| **اتوماسیون مرورگر** | `playwright`, `selenium` |
| **اتوماسیون سیستم** | `pynput`, `pygetwindow`, `pyautogui` |
| **کار با اکسل** | `openpyxl`, `pandas` |
| **تطبیق فازی متن** | `rapidfuzz`, `fuzzywuzzy`, `difflib` |
| **رابط گرافیکی** | `tkinter`, `customtkinter`, `PyQt` |
| **وب و API** | `requests`, `fastapi`, `flask` |
| **داده و تحلیل** | `numpy`, `matplotlib`, `seaborn` |
| **ابزار توسعه** | `tqdm`, `colorama`, `python-dotenv` |

> 📌 هر پروژه فقط زیرمجموعهٔ مورد نیاز خود را در `requirements.txt` خود اعلام می‌کند.

---

## 📝 قواعد کدنویسی / Coding Conventions

<div dir="rtl">

برای حفظ خوانایی و کیفیت کد، موارد زیر رعایت می‌شود:

- **PEP 8** برای سبک کدنویسی پایتون
- **Type Hints** در توابع کلیدی (در حد امکان)
- **Docstring** برای ماژول‌ها و توابع مهم
- **نام‌گذاری معنادار** برای متغیرها و توابع
- **جدا کردن تنظیمات** از منطق اصلی برنامه
- **مدیریت خطا** با `try/except` و لاگ مناسب

</div>

---

## 🤝 مشارکت / Contributing

<div dir="rtl">

از هر نوع مشارکت استقبال می‌شود! برای مشارکت:

1. یک **Fork** از مخزن بگیرید
2. یک **Branch** جدید بسازید:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. تغییرات خود را **Commit** کنید:
   ```bash
   git commit -m "Add: توضیح کوتاه تغییر"
   ```
4. به Branch خود **Push** کنید:
   ```bash
   git push origin feature/your-feature-name
   ```
5. یک **Pull Request** باز کنید

</div>

**راهنمای پیام کامیت / Commit Message Convention:**

| پیشوند | کاربرد |
|---|---|
| `Add:` | افزودن ویژگی یا فایل جدید |
| `Fix:` | رفع باگ |
| `Update:` | به‌روزرسانی کد یا مستندات |
| `Remove:` | حذف کد یا فایل |
| `Refactor:` | بازنویسی کد بدون تغییر رفتار |
| `Docs:` | تغییرات مستندات |

---

## 🐛 گزارش مشکلات / Reporting Issues

<div dir="rtl">

اگر با مشکلی مواجه شدید یا پیشنهادی داشتید:

1. ابتدا بخش **Issues** مخزن را جستجو کنید تا مطمئن شوید مشکل تکراری نیست
2. یک **Issue جدید** باز کنید و موارد زیر را ذکر کنید:
   - نام پروژه (پوشه)
   - سیستم‌عامل و نسخهٔ پایتون
   - مراحل بازتولید مشکل
   - متن کامل خطا (در صورت وجود)
   - اسکرین‌شات (در صورت نیاز)

</div>

---

## 📜 مجوز / License

<div dir="rtl">

این مخزن و تمام پروژه‌های داخل آن تحت مجوز **MIT License** منتشر شده‌اند، مگر در پوشه‌ای خلاف آن صریحاً ذکر شده باشد.

برای مشاهدهٔ متن کامل مجوز، فایل [`LICENSE`](./LICENSE) را ببینید.

</div>

This repository and all projects within it are released under the **MIT License**, unless explicitly stated otherwise in a specific folder.

---

## ⭐ حمایت / Support

<div dir="rtl">

اگر این پروژه‌ها برایتان مفید بودند:

- ⭐ به مخزن **Star** بدهید
- 🍴 آن را **Fork** کنید
- 📢 به دیگران معرفی کنید
- 🐛 در بهبود آن مشارکت کنید

</div>

---

## 📬 تماس / Contact

<div align="center">

| راه ارتباطی | آدرس |
|---|---|
| **GitHub** | [@username](https://github.com/username) |
| **Email** | [your-email@example.com](mailto:your-email@example.com) |
| **LinkedIn** | [linkedin.com/in/username](https://linkedin.com/in/username) |

</div>

---

<div align="center">

**ساخته شده با ❤️ و ☕ توسط [نام شما]**

![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Maintained](https://img.shields.io/badge/Maintained-Yes-success?style=flat-square)

</div>
