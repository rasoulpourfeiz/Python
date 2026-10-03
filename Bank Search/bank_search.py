import pandas as pd
import openpyxl
import re

# ==== مسیر فایل ورودی و خروجی ====
input_file = "/Users/rasoulpourfeiz/Desktop/Bank.xlsx"
output_file = "/Users/rasoulpourfeiz/Desktop/Search_Results.xlsx"

# ==== عبارت جستجو ====
query = "730120020000005807601476"  # می‌تواند شامل اعداد فارسی یا انگلیسی باشد

# ==== تابع تبدیل اعداد فارسی به انگلیسی ====
def persian_to_english(s):
    if pd.isna(s):
        return s
    s = str(s)
    persian_nums = "۰۱۲۳۴۵۶۷۸۹"
    english_nums = "0123456789"
    for p, e in zip(persian_nums, english_nums):
        s = s.replace(p, e)
    return s

# ==== تبدیل query به انگلیسی ====
query = persian_to_english(query)

# ==== باز کردن workbook ====
wb = openpyxl.load_workbook(input_file, data_only=True)

# ==== لیستی برای نگهداری شیت‌های matched به همراه نام شیت ====
matched_sheets = []

# ==== حلقه روی همه شیت‌ها ====
for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    data = ws.values
    
    try:
        cols = next(data)
    except StopIteration:
        continue  # شیت خالی است، رد شود

    df = pd.DataFrame(data, columns=cols)

    # ==== تابع بررسی match برای هر ردیف ====
    def row_matches(row):
        for val in row:
            if pd.isna(val):
                continue
            val_str = persian_to_english(str(val))
            if re.search(re.escape(query), val_str, re.IGNORECASE):
                return True
        return False

    # پیدا کردن ردیف‌های match و ایجاد یک کپی واضح
    matched_df = df[df.apply(row_matches, axis=1)].copy()
    
    # اگر داده‌ای پیدا شد، به لیست اضافه کن
    if not matched_df.empty:
        matched_df["Sheet_Name"] = sheet_name  # اضافه کردن نام شیت به عنوان یک ستون
        matched_sheets.append((sheet_name, matched_df))

# ==== اگر حداقل یک شیت با داده پیدا شد، فایل خروجی ایجاد کن ====
if matched_sheets:
    # ایجاد یک ExcelWriter و اضافه کردن هر شیت
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for sheet_name, matched_df in matched_sheets:
            matched_df.to_excel(writer, index=False, sheet_name=sheet_name)
            print(f"✅ نتایج برای شیت '{sheet_name}' ذخیره شد")
    print(f"✅ جستجو کامل شد! نتایج در {output_file} ذخیره شد")
else:
    print(f"❌ هیچ داده‌ای برای '{query}' پیدا نشد")
