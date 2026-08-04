"""
Salary breakup for Indian payroll (PF excluded), used to auto-fill an
employee's salary structure from a flat monthly gross figure.
"""
from decimal import Decimal, ROUND_HALF_UP

BASIC_PERCENT_OF_GROSS = Decimal("0.45")   # Basic = 45% of Gross
HRA_PERCENT_OF_BASIC = Decimal("0.50")     # HRA = 50% of Basic (metro city)
CONVEYANCE_FLAT = Decimal("1600")          # Fixed monthly conveyance allowance
MEDICAL_FLAT = Decimal("1250")             # Fixed monthly medical allowance

# Maharashtra Professional Tax slabs (monthly gross-based).
# ponytail: single-state slab table, add a company payroll-state setting when
# the product is deployed outside Maharashtra.
PT_SLABS = [
    (Decimal("7500"), Decimal("0")),
    (Decimal("10000"), Decimal("175")),
    (None, Decimal("200")),   # Maharashtra charges 300 in February
]

EARNING_COMPONENTS = ["Basic", "HRA", "Conveyance", "Medical Allowance", "Special Allowance"]
DEDUCTION_COMPONENTS = ["Professional Tax"]


def _round(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_professional_tax(gross_monthly, month=None):
    """Monthly Professional Tax under Maharashtra slabs; 300 in February."""
    for slab_limit, tax in PT_SLABS:
        if slab_limit is None or gross_monthly <= slab_limit:
            if tax == Decimal("200") and month == 2:
                return Decimal("300")
            return tax
    return Decimal("0")


def calculate_salary_breakup(monthly_gross, month=None):
    """
    Splits a flat monthly gross into standard components.
    Special Allowance absorbs the remainder so earnings always sum back
    exactly to gross. Below a certain gross the fixed allowances (and, at
    the extreme, Basic/HRA) get scaled down proportionally so the split
    always sums to gross instead of going negative.
    Returns {component_name: Decimal amount}.
    """
    gross = _round(Decimal(monthly_gross))
    if gross <= 0:
        raise ValueError("Gross salary must be positive.")

    basic = _round(gross * BASIC_PERCENT_OF_GROSS)
    hra = _round(basic * HRA_PERCENT_OF_BASIC)
    remaining = gross - (basic + hra)
    fixed_total = CONVEYANCE_FLAT + MEDICAL_FLAT

    if remaining <= 0:
        # ponytail: gross too low even for Basic+HRA; scale those down to fit,
        # zero out the rest. Ceiling: unrealistic below a few thousand/month.
        scale = gross / (basic + hra)
        basic = _round(basic * scale)
        hra = _round(gross - basic)
        conveyance = Decimal("0.00")
        medical = Decimal("0.00")
        special_allowance = Decimal("0.00")
    elif remaining < fixed_total:
        conveyance = _round(remaining * CONVEYANCE_FLAT / fixed_total)
        medical = _round(remaining - conveyance)
        special_allowance = Decimal("0.00")
    else:
        conveyance = CONVEYANCE_FLAT
        medical = MEDICAL_FLAT
        special_allowance = _round(remaining - fixed_total)

    return {
        "Basic": basic,
        "HRA": hra,
        "Conveyance": conveyance,
        "Medical Allowance": medical,
        "Special Allowance": special_allowance,
        "Professional Tax": calculate_professional_tax(gross, month),
    }


def resolve_employee_components(employee, month=None):
    """
    (earnings, deductions) dicts for an employee: their configured salary
    structure (Salary screen) if set, else the auto breakup from monthly
    gross. Shared by payslip and FY breakup generation.
    """
    lines = employee.salary_lines
    if lines:
        earnings = {l.component.name: l.amount for l in lines if l.component.category == "earning"}
        deductions = {l.component.name: l.amount for l in lines if l.component.category == "deduction"}
        return earnings, deductions
    if employee.monthly_gross:
        breakup = calculate_salary_breakup(employee.monthly_gross, month=month)
        earnings = {k: v for k, v in breakup.items() if k in EARNING_COMPONENTS}
        deductions = {k: v for k, v in breakup.items() if k in DEDUCTION_COMPONENTS}
        return earnings, deductions
    return {}, {}


def financial_year_breakup(employee, fy_start_year):
    """
    Component-wise totals for the Indian financial year (Apr fy_start_year
    to Mar fy_start_year+1). If the employee has a fixed salary structure,
    each component is just x12. If using the auto breakup from gross, PT is
    re-computed per month so the Feb Rs.300 slab is reflected accurately.
    Returns (earnings_total, deductions_total) dicts.
    """
    lines = employee.salary_lines
    if lines or not employee.monthly_gross:
        earnings, deductions = resolve_employee_components(employee)
        return (
            {k: v * 12 for k, v in earnings.items()},
            {k: v * 12 for k, v in deductions.items()},
        )

    fy_months = [(fy_start_year, m) for m in range(4, 13)] + [(fy_start_year + 1, m) for m in range(1, 4)]
    earnings_total, deductions_total = {}, {}
    for _, m in fy_months:
        breakup = calculate_salary_breakup(employee.monthly_gross, month=m)
        for k in EARNING_COMPONENTS:
            earnings_total[k] = earnings_total.get(k, Decimal("0")) + breakup[k]
        for k in DEDUCTION_COMPONENTS:
            deductions_total[k] = deductions_total.get(k, Decimal("0")) + breakup[k]
    return earnings_total, deductions_total


def calculate_lwp_deduction(monthly_gross, unpaid_days, days_in_month):
    """
    Loss-of-Pay deduction for unpaid absence days.
    Per-day rate = gross / calendar days in that month.
    """
    if days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    per_day = Decimal(monthly_gross) / Decimal(days_in_month)
    return _round(per_day * unpaid_days)


def _demo():
    breakup = calculate_salary_breakup(50000, month=7)
    assert breakup["Basic"] == Decimal("22500.00")
    assert breakup["HRA"] == Decimal("11250.00")
    assert sum(v for k, v in breakup.items() if k in EARNING_COMPONENTS) == Decimal("50000.00")
    assert breakup["Professional Tax"] == Decimal("200")
    assert calculate_professional_tax(Decimal("50000"), month=2) == Decimal("300")
    assert calculate_lwp_deduction(31000, unpaid_days=1, days_in_month=31) == Decimal("1000.00")

    low = calculate_salary_breakup(5000)
    assert sum(v for k, v in low.items() if k in EARNING_COMPONENTS) == Decimal("5000.00")
    assert low["Special Allowance"] == Decimal("0.00")

    extreme = calculate_salary_breakup(1000)
    assert sum(v for k, v in extreme.items() if k in EARNING_COMPONENTS) == Decimal("1000.00")
    assert extreme["Conveyance"] < CONVEYANCE_FLAT
    assert extreme["Special Allowance"] == Decimal("0.00")

    print("payroll._demo: ok")


if __name__ == "__main__":
    _demo()
