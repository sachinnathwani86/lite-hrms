from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models import Attendance, Employee, Holiday, LeaveRequest
from app.workspace import active_company_id


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
@login_required
def home():
    if current_user.is_admin():
        company_id = active_company_id()
        employees = Employee.query.filter_by(is_active=True, company_id=company_id).all()
        leave_query = LeaveRequest.query.join(LeaveRequest.employee).filter(Employee.company_id == company_id)
        holiday_query = Holiday.query.filter_by(company_id=company_id)
    else:
        employees = [current_user]
        leave_query = LeaveRequest.query.filter_by(employee_id=current_user.id)
        holiday_query = Holiday.query.filter_by(company_id=current_user.company_id)

    today = date.today()
    attendance_ids = {
        row.employee_id for row in Attendance.query.filter_by(date=today).all()
    }
    pending_count = leave_query.filter(LeaveRequest.status == "pending").count()
    upcoming_holidays = holiday_query.filter(Holiday.date >= today).order_by(Holiday.date).limit(5).all()
    recent_requests = leave_query.order_by(LeaveRequest.applied_on.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        employee_count=len(employees),
        attendance_count=len(attendance_ids.intersection({employee.id for employee in employees})),
        pending_count=pending_count,
        upcoming_holidays=upcoming_holidays,
        recent_requests=recent_requests,
        today=today,
        company_name=current_user.company.name,
        is_admin=current_user.is_admin(),
    )
