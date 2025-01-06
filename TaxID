# وارد کردن کتابخانه‌ها
import pandas as pd
from rapidfuzz import process, fuzz  # تغییرات در وارد کردن

from tqdm import tqdm

# مسیر فایل‌ها روی دسکتاپ
file1_path = "/Users/USERNAME/Desktop/Name.xlsx"  # فایل شامل نام کالاها
file2_path = "/Users/USERNAME/Desktop/Cod.xlsx"  # فایل شامل اطلاعات اداره دارایی
output_path = "/Users/USERNAME/Desktop/merged_file.xlsx"  # مسیر ذخیره فایل نهایی

# خواندن فایل‌ها
file1 = pd.read_excel(file1_path)
file2 = pd.read_excel(file2_path)

# چاپ ستون‌های فایل‌ها برای اطمینان
print("ستون‌های فایل Name.xlsx:")
print(file1.columns)

print("\nستون‌های فایل Cod.xlsx:")
print(file2.columns)

# پیش‌پردازش داده‌ها: حذف فاصله‌ها و تبدیل به حروف کوچک
file1['نام_کالا'] = file1['نام_کالا'].str.strip().str.lower()
file2['Descript'] = file2['Descript'].str.strip().str.lower()

# تابع برای یافتن نزدیک‌ترین تطابق
def find_best_match(name, file2_titles):
    """
    پیدا کردن نزدیک‌ترین تطابق برای نام کالا در فایل دوم
    """
    best_match = process.extractOne(name, file2_titles, scorer=fuzz.token_set_ratio)
    if best_match and best_match[1] >= 90:  # شرط اطمینان >= 90%
        return best_match[0]
    else:
        return None

# استخراج لیست عنوان کالاها از فایل دوم
file2_titles = file2['Descript'].tolist()

# اضافه کردن نوار پیشرفت
tqdm.pandas()

# اعمال تطبیق بر روی فایل اول
file1['Matched_Descript'] = file1['نام_کالا'].progress_apply(lambda x: find_best_match(x, file2_titles))

# اضافه کردن اطلاعات تکمیلی از فایل Cod.xlsx
merged_file = file1.merge(file2, left_on='Matched_Descript', right_on='Descript', how='left')

# ذخیره فایل نهایی در مسیر مشخص‌شده
merged_file.to_excel(output_path, index=False)
print(f"فایل نهایی با موفقیت ذخیره شد: {output_path}")
