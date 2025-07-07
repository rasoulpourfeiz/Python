# Product Name Matching Tool / ابزار تطبیق نام کالاها
[![Python Version](https://img.shields.io/badge/Python-3.7%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

ابزاری برای تطبیق هوشمند نام کالاها بین دو فایل اکسل با استفاده از الگوریتم‌های فازی  
A tool for intelligent product name matching between two Excel files using fuzzy algorithms

---

## Features / ویژگی‌ها
### فارسی
- تطبیق هوشمند نام‌ها با وجود تفاوت‌های املایی و ساختاری
- استفاده از الگوریتم پیشرفته فازی (token_set_ratio)
- پیش‌پردازش خودکار داده‌ها (حذف فاصله‌ها و تبدیل به حروف کوچک)
- نمایش نوار پیشرفت برای روند تطبیق
- قابلیت تنظیم آستانه تشابه (پیش‌فرض ۹۰٪)
- ادغام خودکار داده‌های تطبیق یافته
- پشتیبانی از فایل‌های Excel (xlsx)

### English
- Intelligent name matching despite spelling and structural differences
- Advanced fuzzy algorithm (token_set_ratio)
- Automatic data preprocessing (trimming whitespace and lowercasing)
- Progress bar visualization
- Configurable similarity threshold (default 90%)
- Automatic merging of matched data
- Excel file support (xlsx)

---

## Prerequisites / پیش‌نیازها
```bash
pip install pandas rapidfuzz tqdm openpyxl
Installation / نصب
کد پایتون را در یک فایل ذخیره کنید (مثلاً product_matcher.py)

کتابخانه‌های مورد نیاز را نصب کنید

مسیر فایل‌های ورودی و خروجی را در کد تنظیم کنید

Usage / نحوه استفاده
فارسی
دو فایل اکسل آماده کنید:

فایل اول (Name.xlsx): شامل ستون نام_کالا

فایل دوم (Cod.xlsx): شامل ستون Descript

مسیر فایل‌ها را در کد تنظیم کنید:
file1_path = "/مسیر/فایل/Name.xlsx"
file2_path = "/مسیر/فایل/Cod.xlsx"
output_path = "/مسیر/خروجی/merged_file.xlsx"
اسکریپت را اجرا کنید:
python product_matcher.py
English
Prepare two Excel files:

File 1 (Name.xlsx): Contains نام_کالا column

File 2 (Cod.xlsx): Contains Descript column

Set file paths in the code:
file1_path = "/path/to/Name.xlsx"
file2_path = "/path/to/Cod.xlsx"
output_path = "/output/path/merged_file.xlsx"
Run the script:
python product_matcher.py
Configurable Parameters / پارامترهای قابل تنظیم
# تغییر آستانه تشابه (پیش‌فرض: 90%)
if best_match and best_match[1] >= 95:  # تغییر به 95%

# تغییر الگوریتم تطبیق (پیش‌فرض: token_set_ratio)
best_match = process.extractOne(name, file2_titles, scorer=fuzz.ratio)
Output Example / نمونه خروجی
فایل خروجی (merged_file.xlsx) شامل تمامی داده‌های فایل اول به همراه ستون‌های تطبیق یافته از فایل دوم خواهد بود.

نام_کالا (فایل اول)	Matched_Descript	سایر ستون‌های فایل Cod.xlsx
شیر پرچرب 1 لیتری	شیر پرچرب 1000ml	...
پنیر پیتزا	پنیر پیتزایی	...
Customization / سفارشی‌سازی
فارسی
تغییر آستانه تشابه:
خط ۳۶ کد: مقدار ۹۰ را به درصد دلخواه تغییر دهید

تغییر الگوریتم تطبیق:
خط ۳۲ کد: fuzz.token_set_ratio را به یکی از گزینه‌های زیر تغییر دهید:

fuzz.ratio: مقایسه ساده

fuzz.partial_ratio: مقایسه بخشی

fuzz.token_sort_ratio: بدون توجه به ترتیب کلمات

افزایش سرعت اجرا:
برای داده‌های حجیم، پیش‌پردازش داده‌ها را بهبود بخشید

English
Adjust similarity threshold:
Line 36: Change the value 90 to your desired percentage

Change matching algorithm:
Line 32: Replace fuzz.token_set_ratio with:

fuzz.ratio: Basic comparison

fuzz.partial_ratio: Partial matching

fuzz.token_sort_ratio: Ignores word order

Improve performance:
For large datasets, optimize the preprocessing steps

Important Notes / نکات مهم
فرمت فایل‌های ورودی باید .xlsx باشد

نام ستون‌ها باید دقیقاً مطابق کد باشد:

فایل اول: نام_کالا

فایل دوم: Descript

سیستم مورد نیاز:

حداقل ۴GB RAM برای فایل‌های متوسط

زمان اجرا به حجم داده‌ها بستگی دارد

License / مجوز
این پروژه تحت مجوز MIT License منتشر شده است.
