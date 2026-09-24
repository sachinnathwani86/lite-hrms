import calendar
import math
from datetime import date, datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Attendance, Employee
from app.admin import approver_required
from app.workspace import active_company_id

# Marking/viewing your own attendance is open to any logged-in employee;
# the monthly grid across everyone is admin-only.
attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")

GEOFENCE_RADIUS_M = 100
STATUS_CODES = {"present": "P", "absent": "A", "half_day": "H", "on_leave": "L"}


def _distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@attendance_bp.route("/")
@login_required
def my_attendance():
    today = date.today()
    today_row = Attendance.query.filter_by(employee_id=current_user.id, date=today).first()
    month_rows = Attendance.query.filter(
        Attendance.employee_id == current_user.id,
        db.extract("year", Attendance.date) == today.year,
        db.extract("month", Attendance.date) == today.month,
    ).order_by(Attendance.date.desc()).all()
    office_set = bool(current_user.company.office_latitude and current_user.company.office_longitude)
    return render_template(
        "attendance/list.html", today_row=today_row, month_rows=month_rows, office_set=office_set
    )


@attendance_bp.route("/mark", methods=["POST"])
@login_required
def mark_present():
    today = date.today()
    if Attendance.query.filter_by(employee_id=current_user.id, date=today).first():
        flash("You've already marked attendance today.", "error")
        return redirect(url_for("attendance.my_attendance"))

    lat = request.form.get("latitude")
    lon = request.form.get("longitude")
    company = current_user.company

    distance = None
    if company.office_latitude is not None and company.office_longitude is not None:
        if not lat or not lon:
            flash("Location is required to mark attendance for this company.", "error")
            return redirect(url_for("attendance.my_attendance"))
        distance = _distance_m(float(lat), float(lon), company.office_latitude, company.office_longitude)
        if distance > GEOFENCE_RADIUS_M:
            flash(
                f"You're {distance:,.0f}m from the office — must be within "
                f"{GEOFENCE_RADIUS_M}m to mark attendance.", "error"
            )
            return redirect(url_for("attendance.my_attendance"))

    db.session.add(Attendance(
        employee_id=current_user.id,
        date=today,
        status="present",
        check_in=datetime.now().time(),
        check_in_latitude=float(lat) if lat else None,
        check_in_longitude=float(lon) if lon else None,
        check_in_distance_m=distance,
    ))
    db.session.commit()
    flash("Attendance marked for today.", "success")
    return redirect(url_for("attendance.my_attendance"))


@attendance_bp.route("/checkout", methods=["POST"])
@login_required
def mark_checkout():
    today = date.today()
    row = Attendance.query.filter_by(employee_id=current_user.id, date=today).first()
    if not row or not row.check_in:
        flash("Mark your attendance first, then check out.", "error")
        return redirect(url_for("attendance.my_attendance"))
    if row.check_out:
        flash("You've already checked out today.", "error")
        return redirect(url_for("attendance.my_attendance"))
    row.check_out = datetime.now().time()
    db.session.commit()
    flash("Checked out for today.", "success")
    return redirect(url_for("attendance.my_attendance"))


@attendance_bp.route("/admin")
@login_required
@approver_required
def admin_grid():
    month = int(request.args.get("month", date.today().month))
    year = int(request.args.get("year", date.today().year))
    days_in_month = calendar.monthrange(year, month)[1]

    employees = Employee.query.filter_by(is_active=True, company_id=active_company_id()).order_by(Employee.full_name).all()
    employee_ids = [employee.id for employee in employees]
    rows = Attendance.query.filter(
        Attendance.employee_id.in_(employee_ids or [-1]),
        db.extract("year", Attendance.date) == year,
        db.extract("month", Attendance.date) == month,
    ).all()
    grid = {(r.employee_id, r.date.day): STATUS_CODES.get(r.status, "?") for r in rows}

    return render_template(
        "attendance/admin_grid.html", employees=employees, days=range(1, days_in_month + 1),
        grid=grid, month=month, year=year
    )
