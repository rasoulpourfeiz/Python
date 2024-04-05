def calculate_loan_installments():
    # ورود اطلاعات از کاربر
    loan_amount = float(input("لطفا مبلغ وام را وارد کنید (ریال): "))
    interest_rate = float(input("لطفا نرخ بهره وام را وارد کنید (درصد): "))
    num_installments = int(input("لطفا تعداد اقساط را وارد کنید: "))

    # محاسبه مبلغ اقساط
    monthly_interest_rate = interest_rate / 100 / 12
    monthly_installment = (loan_amount * monthly_interest_rate) / (1 - (1 + monthly_interest_rate) ** -num_installments)

    # محاسبه مبلغ اصل وام و مبلغ بهره
    total_loan_amount = monthly_installment * num_installments
    total_interest_amount = total_loan_amount - loan_amount

    # نمایش نتایج با جدا کردن اعداد به صورت ۳ رقمی
    print(f"مبلغ اصل و بهره وام: {total_loan_amount:,.0f} ریال")
    print(f"مبلغ بهره: {total_interest_amount:,.0f} ریال")

# فراخوانی تابع
calculate_loan_installments()
