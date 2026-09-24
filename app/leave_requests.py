import calendar
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Holiday, LeaveRequest, LeaveType, LeaveBalance
from app.admin import approver_required
from app.activity import notify, record_audit
from app.workspace import active_company_id

# Submitting/viewing your own requests is open to any logged-in employee;
# the approval queue is admin-only.
leave_requests_bp = Blueprint("leave_requests", __name__, url_prefix="/leave-requests")


def _business_days(start, end, holidays=None):
    holidays = holidays or set()
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:  # Mon-Fri, excluding holidays
            days += 1
        d += timedelta(days=1)
    return days


def _company_leave_requests():
    query = LeaveRequest.query.join(LeaveRequest.employee)
    if current_user.is_admin():
        query = query.filter(LeaveRequest.employee.has(company_id=active_company_id()))
    else:
        query = query.filter(LeaveRequest.employee_id == current_user.id)
    return query


@leave_requests_bp.route("/")
@login_required
def list_my_requests():
    requests_ = LeaveRequest.query.filter_by(employee_id=current_user.id) \
        .order_by(LeaveRequest.applied_on.desc()).all()
    balances = LeaveBalance.query.filter_by(
        employee_id=current_user.id, year=date.today().year
    ).all()
    return render_template("leave_requests/list.html", requests=requests_, balances=balances)


@leave_requests_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_request():
    leave_types = LeaveType.query.filter_by(
        is_active=True, company_id=current_user.company_id
    ).order_by(LeaveType.name).all()

    if request.method == "POST":
        leave_type_id = int(request.form["leave_type_id"])
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        reason = request.form.get("reason", "").strip()

        leave_type = LeaveType.query.get_or_404(leave_type_id)
        if leave_type.company_id != current_user.company_id:
            flash("Invalid leave type.", "error")
            return render_template("leave_requests/form.html", leave_types=leave_types)

        if end_date < start_date:
            flash("End date must be on or after the start date.", "error")
            return render_template("leave_requests/form.html", leave_types=leave_types)

        holiday_dates = {
            holiday.date for holiday in Holiday.query.filter(
                Holiday.company_id == current_user.company_id,
                Holiday.date >= start_date,
                Holiday.date <= end_date,
            ).all()
        }
        days_count = _business_days(start_date, end_date, holiday_dates)
        if days_count <= 0:
            flash("That range has no working days — weekends and company holidays are excluded.", "error")
            return render_template("leave_requests/form.html", leave_types=leave_types)

        overlapping = LeaveRequest.query.filter(
            LeaveRequest.employee_id == current_user.id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        ).first()
        if overlapping:
            flash("This range overlaps one of your existing pending or approved requests.", "error")
            return render_template("leave_requests/form.html", leave_types=leave_types)

        notice_days = (start_date - date.today()).days
        if notice_days < leave_type.min_days_notice:
            flash(
                f"'{leave_type.name}' requires at least {leave_type.min_days_notice} "
                f"day(s) notice.", "error"
            )
            return render_template("leave_requests/form.html", leave_types=leave_types)

        balance = LeaveBalance.query.filter_by(
            employee_id=current_user.id, leave_type_id=leave_type.id, year=start_date.year
        ).first()
        available = balance.available if balance else 0
        if not leave_type.allow_negative_balance and days_count > available:
            flash(
                f"Insufficient balance: {available} day(s) available for "
                f"'{leave_type.name}', {days_count} requested.", "error"
            )
            return render_template("leave_requests/form.html", leave_types=leave_types)

        lr = LeaveRequest(
            employee_id=current_user.id,
            leave_type_id=leave_type.id,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason,
        )

        if not leave_type.requires_approval:
            lr.status = "approved"
            lr.approved_by = current_user.id
            if balance:
                balance.used += days_count
        record_audit(current_user, "create", "leave_request", None, f"Requested {days_count} day(s) of {leave_type.name}")
        db.session.add(lr)
        db.session.commit()
        flash(
            f"Leave request submitted{' and auto-approved' if lr.status == 'approved' else ''}.",
            "success"
        )
        return redirect(url_for("leave_requests.list_my_requests"))

    return render_template("leave_requests/form.html", leave_types=leave_types)


@leave_requests_bp.route("/admin")
@login_required
@approver_required
def admin_queue():
    requests_ = _company_leave_requests().order_by(LeaveRequest.applied_on.desc()).all()
    return render_template("leave_requests/admin_queue.html", requests=requests_)


@leave_requests_bp.route("/<int:request_id>/approve", methods=["POST"])
@login_required
@approver_required
def approve_request(request_id):
    lr = LeaveRequest.query.get_or_404(request_id)
    if lr.employee.company_id != active_company_id():
        return redirect(url_for("leave_requests.admin_queue"))
    if lr.status != "pending":
        flash("This request has already been actioned.", "error")
        return redirect(url_for("leave_requests.admin_queue"))

    balance = LeaveBalance.query.filter_by(
        employee_id=lr.employee_id, leave_type_id=lr.leave_type_id, year=lr.start_date.year
    ).first()
    if balance:
        balance.used += lr.days_count

    lr.status = "approved"
    lr.approved_by = current_user.id
    notify(lr.employee_id, "Leave approved", f"Your {lr.leave_type.name} request from {lr.start_date} to {lr.end_date} was approved.", "/leave-requests/")
    record_audit(current_user, "approve", "leave_request", lr.id, f"Approved leave for {lr.employee.full_name}")
    db.session.commit()
    flash(f"Approved leave request for '{lr.employee.full_name}'.", "success")
    return redirect(url_for("leave_requests.admin_queue"))


@leave_requests_bp.route("/<int:request_id>/reject", methods=["POST"])
@login_required
@approver_required
def reject_request(request_id):
    lr = LeaveRequest.query.get_or_404(request_id)
    if lr.employee.company_id != active_company_id():
        return redirect(url_for("leave_requests.admin_queue"))
    if lr.status != "pending":
        flash("This request has already been actioned.", "error")
        return redirect(url_for("leave_requests.admin_queue"))

    lr.status = "rejected"
    lr.approved_by = current_user.id
    notify(lr.employee_id, "Leave rejected", f"Your {lr.leave_type.name} request from {lr.start_date} to {lr.end_date} was rejected.", "/leave-requests/")
    record_audit(current_user, "reject", "leave_request", lr.id, f"Rejected leave for {lr.employee.full_name}")
    db.session.commit()
    flash(f"Rejected leave request for '{lr.employee.full_name}'.", "success")
    return redirect(url_for("leave_requests.admin_queue"))


@leave_requests_bp.route("/calendar")
@login_required
def calendar_view():
    today = date.today()
    try:
        month = int(request.args.get("month", today.month))
        year = int(request.args.get("year", today.year))
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        month, year = today.month, today.year

    first_day = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    holidays = Holiday.query.filter(
        Holiday.company_id == current_user.company_id,
        Holiday.date >= first_day,
        Holiday.date <= date(year, month, days_in_month),
    ).all()
    requests_ = _company_leave_requests().filter(
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.start_date <= date(year, month, days_in_month),
        LeaveRequest.end_date >= first_day,
    ).all()
    holiday_map = {holiday.date.day: holiday for holiday in holidays}
    request_map = {}
    for leave_request in requests_:
        start = max(leave_request.start_date, first_day)
        end = min(leave_request.end_date, date(year, month, days_in_month))
        current = start
        while current <= end:
            request_map.setdefault(current.day, []).append(leave_request)
            current += timedelta(days=1)

    weeks = []
    week = [None] * first_day.weekday()
    for day_number in range(1, days_in_month + 1):
        week.append({
            "date": date(year, month, day_number),
            "holiday": holiday_map.get(day_number),
            "requests": request_map.get(day_number, []),
        })
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week.extend([None] * (7 - len(week)))
        weeks.append(week)

    previous = first_day - timedelta(days=1)
    next_month = date(year, month, days_in_month) + timedelta(days=1)
    return render_template(
        "leave_requests/calendar.html",
        weeks=weeks,
        month_label=first_day.strftime("%B %Y"),
        today=today,
        previous_month=previous.strftime("%Y-%m"),
        next_month=next_month.strftime("%Y-%m"),
    )
