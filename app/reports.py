import csv
from datetime import date
from io import StringIO

from flask import Blueprint, Response, render_template
from flask_login import login_required

from app.admin import people_required
from app.models import Attendance, Employee, LeaveRequest
from app.workspace import active_company_id


reports_bp = Blueprint("reports", __name__, url_prefix="/admin/reports")


@reports_bp.route("/")
@login_required
@people_required
def index():
    employees = Employee.query.filter_by(is_active=True, company_id=active_company_id()).count()
    pending_leave = LeaveRequest.query.join(LeaveRequest.employee).filter(LeaveRequest.status == "pending", Employee.company_id == active_company_id()).count()
    today_attendance = Attendance.query.join(Attendance.employee).filter(Attendance.date == date.today(), Employee.company_id == active_company_id()).count()
    approved_leave = LeaveRequest.query.join(LeaveRequest.employee).filter(LeaveRequest.status == "approved", Employee.company_id == active_company_id()).count()
    return render_template(
        "reports/index.html",
        employees=employees,
        pending_leave=pending_leave,
        today_attendance=today_attendance,
        approved_leave=approved_leave,
    )


@reports_bp.route("/employees.csv")
@login_required
@people_required
def employees_csv():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Full name", "Email", "Company", "Role", "Designation", "Status", "Joining date"])
    for employee in Employee.query.filter_by(company_id=active_company_id()).order_by(Employee.full_name).all():
        writer.writerow([
            employee.full_name,
            employee.email,
            employee.company.name,
            employee.role,
            employee.designation.title if employee.designation else "",
            "Active" if employee.is_active else "Inactive",
            employee.date_of_joining,
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )
