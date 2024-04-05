def calculate_interest(principal, rate):
    # محاسبه سود روزانه
    daily_interest = principal * rate / 365
    # محاسبه سود ماهانه
    monthly_interest = daily_interest * 30
    # محاسبه سود سالانه
    annual_interest = daily_interest * 365

    # نمایش اعداد با سه رقم جداشونده
    formatted_daily_interest = f"{daily_interest:,.2f}"
    formatted_monthly_interest = f"{monthly_interest:,.2f}"
    formatted_annual_interest = f"{annual_interest:,.2f}"

    return formatted_daily_interest, formatted_monthly_interest, formatted_annual_interest

# ورودی‌ها
principal_amount = float(input("لطفا مبلغ سپرده بانکی را وارد کنید (ریال): "))
interest_rate = float(input("لطفا نرخ سود را وارد کنید (درصد): ")) / 100

daily, monthly, annual = calculate_interest(principal_amount, interest_rate)

print(f"سود روزانه: {daily} ریال")
print(f"سود ماهانه: {monthly} ریال")
print(f"سود سالانه: {annual} ریال")
