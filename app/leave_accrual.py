from datetime import date

from app.extensions import db
from app.models import Employee, LeaveBalance, LeaveType


def run_accrual(year=None, month=None):
    """Apply monthly accruals and create the next year's opening balances.

    The target accrued amount is recalculated from the month, making reruns safe.
    """
    today = date.today()
    year = year or today.year
    month = month or today.month
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    changed = 0
    for employee in Employee.query.filter_by(is_active=True).all():
        leave_types = LeaveType.query.filter_by(
            company_id=employee.company_id, is_active=True
        ).all()
        for leave_type in leave_types:
            balance = LeaveBalance.query.filter_by(
                employee_id=employee.id, leave_type_id=leave_type.id, year=year
            ).first()
            if not balance:
                previous = LeaveBalance.query.filter_by(
                    employee_id=employee.id, leave_type_id=leave_type.id, year=year - 1
                ).first()
                carried = 0
                if previous and leave_type.carry_forward:
                    carried = previous.available
                    if leave_type.max_carry_forward is not None:
                        carried = min(carried, leave_type.max_carry_forward)
                balance = LeaveBalance(
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=year,
                    opening_balance=leave_type.annual_quota if leave_type.accrual_type == "yearly_upfront" else 0,
                    carried_forward=max(carried, 0),
                )
                db.session.add(balance)

            if leave_type.accrual_type == "monthly":
                balance.accrued = round(float(leave_type.annual_quota) * month / 12, 2)
                balance.last_accrued_month = month
            changed += 1

    db.session.commit()
    return changed
