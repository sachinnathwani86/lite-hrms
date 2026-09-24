import calendar
import csv
from datetime import date
from io import StringIO

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app.admin import people_required
from app.models import Attendance, Employee, LeaveRequest, PayrollRun
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
    writer.writerow(["User ID", "Full name", "Email", "Company", "Role", "Designation", "Status", "Joining date"])
    for employee in Employee.query.filter_by(company_id=active_company_id()).order_by(Employee.full_name).all():
        writer.writerow([
            employee.username,
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


@reports_bp.route("/attendance.csv")
@login_required
@people_required
def attendance_csv():
    today = date.today()
    try:
        month = int(request.args.get("month", today.month))
        year = int(request.args.get("year", today.year))
        if month < 1 or month > 12:
            raise ValueError
    except (TypeError, ValueError):
        month, year = today.month, today.year

    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    rows = Attendance.query.join(Attendance.employee).filter(
        Employee.company_id == active_company_id(),
        Attendance.date >= start,
        Attendance.date <= end,
    ).order_by(Attendance.date, Employee.full_name).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Employee", "Date", "Status", "Check In", "Check Out", "Hours"])
    for row in rows:
        writer.writerow([
            row.employee.username,
            row.employee.full_name,
            row.date,
            row.status,
            row.check_in.strftime("%H:%M") if row.check_in else "",
            row.check_out.strftime("%H:%M") if row.check_out else "",
            row.worked_hours if row.worked_hours is not None else "",
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance-{year}-{month:02d}.csv"},
    )


@reports_bp.route("/payroll.csv")
@login_required
@people_required
def payroll_csv():
    runs = PayrollRun.query.join(PayrollRun.employee).filter(
        Employee.company_id == active_company_id()
    ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Employee", "Period", "Gross", "Deductions", "Net pay", "Status"])
    for run in runs:
        writer.writerow([
            run.employee.username,
            run.employee.full_name,
            f"{run.month:02d}/{run.year}",
            run.gross,
            run.deductions,
            run.net_pay,
            run.status,
        ])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=payroll.csv"},
    )
