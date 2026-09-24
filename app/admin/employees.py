import os
import uuid
import calendar
import csv
import io
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, current_app, send_file
)
from flask_login import login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import (
    Employee, LeaveType, LeaveBalance, Designation, SalaryComponent, EmployeeSalary, Company,
    PayrollRun, Attendance, LeaveRequest, EmployeeChecklistItem
)
from app.admin import people_required
from app.activity import record_audit
from app.payroll import calculate_salary_breakup, calculate_lwp_deduction, resolve_employee_components, build_payslip_data, EARNING_COMPONENTS, DEDUCTION_COMPONENTS
from app.letters import appointment_letter, termination_letter, relieving_letter, payslip, fy_breakup_letter
from app.workspace import active_company_id, ensure_active_company

employees_bp = Blueprint("employees", __name__, url_prefix="/admin/employees")

ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@employees_bp.route("/")
@login_required
@people_required
def list_employees():
    page = max(request.args.get("page", 1, type=int), 1)
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "active")
    query = Employee.query.filter_by(company_id=active_company_id())
    if search:
        query = query.filter(or_(Employee.full_name.ilike(f"%{search}%"), Employee.username.ilike(f"%{search}%"), Employee.email.ilike(f"%{search}%")))
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)
    employees = query.order_by(Employee.full_name).paginate(page=page, per_page=25, error_out=False)
    return render_template("employees/list.html", employees=employees, search=search, status=status)


@employees_bp.route("/import", methods=["GET", "POST"])
@login_required
@people_required
def import_employees():
    if request.method == "POST":
        upload = request.files.get("employee_csv")
        if not upload or not upload.filename.lower().endswith(".csv"):
            flash("Upload a CSV file.", "error")
            return render_template("employees/import.html")

        try:
            rows = csv.DictReader(io.TextIOWrapper(upload.stream, encoding="utf-8-sig"))
            required = {"full_name", "username"}
            if not rows.fieldnames or not required.issubset(set(rows.fieldnames)):
                raise ValueError("CSV must include full_name and username columns.")
            created = 0
            skipped = []
            for line_number, row in enumerate(rows, start=2):
                full_name = (row.get("full_name") or "").strip()
                username = (row.get("username") or "").strip()
                email = (row.get("email") or "").strip().lower() or None
                if not full_name or not username:
                    skipped.append(f"row {line_number}: missing required value")
                    continue
                company = Company.query.get(active_company_id())
                if Employee.query.filter(db.func.lower(Employee.username) == username.lower(), Employee.company_id == company.id).first():
                    skipped.append(f"row {line_number}: duplicate user ID")
                    continue
                if email and Employee.query.filter_by(email=email, company_id=company.id).first():
                    skipped.append(f"row {line_number}: duplicate email")
                    continue
                designation_id = int(row["designation_id"]) if row.get("designation_id") else None
                if designation_id:
                    designation = Designation.query.get(designation_id)
                    if not designation or designation.company_id != company.id:
                        skipped.append(f"row {line_number}: designation does not belong to company")
                        continue
                employee = Employee(
                    company_id=company.id,
                    full_name=full_name,
                    username=username,
                    email=email,
                    role=(row.get("role") or "employee").strip(),
                    designation_id=designation_id,
                    date_of_joining=datetime.strptime(row["date_of_joining"], "%Y-%m-%d").date() if row.get("date_of_joining") else date.today(),
                    monthly_gross=Decimal(row.get("monthly_gross") or 0),
                )
                if employee.role not in {"employee", "manager", "hr_manager", "admin"}:
                    skipped.append(f"row {line_number}: invalid role")
                    continue
                employee.set_password(row.get("password") or secrets.token_urlsafe(12))
                db.session.add(employee)
                db.session.flush()
                for leave_type in LeaveType.query.filter_by(company_id=company.id, is_active=True).all():
                    db.session.add(LeaveBalance(
                        employee_id=employee.id,
                        leave_type_id=leave_type.id,
                        year=date.today().year,
                        opening_balance=leave_type.annual_quota if leave_type.accrual_type == "yearly_upfront" else 0,
                    ))
                record_audit(current_user, "import", "employee", employee.id, "Imported from CSV")
                created += 1
            db.session.commit()
            flash(f"Imported {created} employee(s). Skipped {len(skipped)} row(s).", "success")
            if skipped:
                flash("; ".join(skipped[:5]), "error")
            return redirect(url_for("employees.list_employees"))
        except (UnicodeDecodeError, ValueError, InvalidOperation) as error:
            db.session.rollback()
            flash(f"Import failed: {error}", "error")
    return render_template("employees/import.html")


@employees_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_employee():
    if request.method == "POST":
        company_id = active_company_id()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        if not username:
            flash("A user ID is required.", "error")
            return render_template(
                "employees/form.html", employee=None,
                designations=_active_designations(), companies=_active_companies()
            )
        if Employee.query.filter(db.func.lower(Employee.username) == username.lower(), Employee.company_id == company_id).first():
            flash(f"An employee with user ID '{username}' already exists at this company.", "error")
            return render_template(
                "employees/form.html", employee=None,
                designations=_active_designations(), companies=_active_companies()
            )
        if email and Employee.query.filter_by(email=email, company_id=company_id).first():
            flash(f"An employee with email '{email}' already exists at this company.", "error")
            return render_template(
                "employees/form.html", employee=None,
                designations=_active_designations(), companies=_active_companies()
            )

        designation_id = _to_int_or_none(request.form.get("designation_id"))
        if not _designation_matches_company(designation_id, company_id):
            flash("Designation must belong to the selected company.", "error")
            return render_template(
                "employees/form.html", employee=None,
                designations=_active_designations(), companies=_active_companies()
            )

        emp = Employee(
            company_id=company_id,
            full_name=request.form["full_name"].strip(),
            username=username,
            email=email,
            role=request.form.get("role", "employee"),
            designation_id=designation_id,
            date_of_joining=_to_date_or_today(request.form.get("date_of_joining")),
            monthly_gross=request.form.get("monthly_gross", 0),
        )
        emp.set_password(request.form["password"])
        db.session.add(emp)
        db.session.flush()  # assign emp.id before creating leave balances / saving photo

        photo_error = _handle_photo_upload(request, emp)
        if photo_error:
            db.session.rollback()
            flash(photo_error, "error")
            return render_template(
                "employees/form.html", employee=None,
                designations=_active_designations(), companies=_active_companies()
            )

        for lt in LeaveType.query.filter_by(is_active=True, company_id=emp.company_id).all():
            db.session.add(LeaveBalance(
                employee_id=emp.id,
                leave_type_id=lt.id,
                year=date.today().year,
                opening_balance=lt.annual_quota if lt.accrual_type == "yearly_upfront" else 0,
            ))

        db.session.commit()
        flash(f"Employee '{emp.full_name}' created.", "success")
        return redirect(url_for("employees.list_employees"))

    return render_template(
        "employees/form.html", employee=None,
        designations=_active_designations(), companies=_active_companies()
    )


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_employee(employee_id):
    emp = _employee_or_404(employee_id)

    if request.method == "POST":
        company_id = active_company_id()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        if not username:
            flash("A user ID is required.", "error")
            return render_template(
                "employees/form.html", employee=emp,
                designations=_active_designations(), companies=_active_companies()
            )
        existing_username = Employee.query.filter(db.func.lower(Employee.username) == username.lower(), Employee.company_id == company_id).first()
        if existing_username and existing_username.id != emp.id:
            flash(f"An employee with user ID '{username}' already exists at this company.", "error")
            return render_template(
                "employees/form.html", employee=emp,
                designations=_active_designations(), companies=_active_companies()
            )
        if email:
            existing_email = Employee.query.filter_by(email=email, company_id=company_id).first()
            if existing_email and existing_email.id != emp.id:
                flash(f"An employee with email '{email}' already exists at this company.", "error")
                return render_template(
                    "employees/form.html", employee=emp,
                    designations=_active_designations(), companies=_active_companies()
                )

        designation_id = _to_int_or_none(request.form.get("designation_id"))
        if not _designation_matches_company(designation_id, company_id):
            flash("Designation must belong to the selected company.", "error")
            return render_template(
                "employees/form.html", employee=emp,
                designations=_active_designations(), companies=_active_companies()
            )

        emp.company_id = company_id
        emp.full_name = request.form["full_name"].strip()
        emp.username = username
        emp.email = email
        emp.role = request.form.get("role", "employee")
        emp.designation_id = designation_id
        emp.date_of_joining = _to_date_or_today(request.form.get("date_of_joining"))
        emp.monthly_gross = request.form.get("monthly_gross", 0)
        emp.is_active = bool(request.form.get("is_active"))

        if request.form.get("remove_photo") and emp.photo_filename:
            _delete_photo(emp.photo_filename)
            emp.photo_filename = None

        photo_error = _handle_photo_upload(request, emp)
        if photo_error:
            db.session.rollback()
            flash(photo_error, "error")
            return render_template(
                "employees/form.html", employee=emp,
                designations=_active_designations(), companies=_active_companies()
            )

        db.session.commit()
        flash(f"Employee '{emp.full_name}' updated.", "success")
        return redirect(url_for("employees.list_employees"))

    return render_template(
        "employees/form.html", employee=emp,
        designations=_active_designations(), companies=_active_companies()
    )


@employees_bp.route("/<int:employee_id>/salary", methods=["GET", "POST"])
@login_required
@people_required
def edit_salary(employee_id):
    emp = _employee_or_404(employee_id)
    # earnings first, then deductions
    components = SalaryComponent.query.filter_by(company_id=emp.company_id).order_by(
        SalaryComponent.category.desc(), SalaryComponent.name
    ).all()

    if request.method == "POST":
        lines = {line.component_id: line for line in emp.salary_lines}
        try:
            for comp in components:
                raw = request.form.get(f"amount_{comp.id}", "").strip()
                amount = Decimal(raw) if raw else None
                if amount is not None and amount < 0:
                    raise InvalidOperation
                line = lines.get(comp.id)
                if amount is None:
                    # blank input = component does not apply to this employee
                    if line:
                        db.session.delete(line)
                elif line:
                    line.amount = amount
                else:
                    db.session.add(EmployeeSalary(
                        employee_id=emp.id, component_id=comp.id, amount=amount
                    ))
        except InvalidOperation:
            db.session.rollback()
            flash("Amounts must be valid non-negative numbers.", "error")
            return redirect(url_for("employees.edit_salary", employee_id=emp.id))

        db.session.commit()
        flash(f"Salary structure for '{emp.full_name}' saved.", "success")
        return redirect(url_for("employees.edit_salary", employee_id=emp.id))

    amounts = {line.component_id: line.amount for line in emp.salary_lines}
    total_earnings = sum(a for c, a in amounts.items() if _cat(components, c) == "earning")
    total_deductions = sum(a for c, a in amounts.items() if _cat(components, c) == "deduction")
    return render_template(
        "employees/salary.html",
        employee=emp,
        components=components,
        amounts=amounts,
        total_earnings=total_earnings,
        total_deductions=total_deductions,
    )


@employees_bp.route("/<int:employee_id>/salary/autofill", methods=["POST"])
@login_required
@people_required
def autofill_salary(employee_id):
    emp = _employee_or_404(employee_id)
    if not emp.monthly_gross:
        flash("Set a monthly gross on the employee's profile before auto-filling.", "error")
        return redirect(url_for("employees.edit_salary", employee_id=emp.id))

    try:
        breakup = calculate_salary_breakup(emp.monthly_gross, month=date.today().month)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("employees.edit_salary", employee_id=emp.id))

    lines = {line.component_id: line for line in emp.salary_lines}
    for name, amount in breakup.items():
        category = "earning" if name in EARNING_COMPONENTS else "deduction"
        comp = SalaryComponent.query.filter_by(company_id=emp.company_id, name=name).first()
        if not comp:
            comp = SalaryComponent(company_id=emp.company_id, name=name, category=category)
            db.session.add(comp)
            db.session.flush()
        line = lines.get(comp.id)
        if line:
            line.amount = amount
        else:
            db.session.add(EmployeeSalary(employee_id=emp.id, component_id=comp.id, amount=amount))

    db.session.commit()
    flash(f"Salary structure auto-filled from gross ({emp.monthly_gross}).", "success")
    return redirect(url_for("employees.edit_salary", employee_id=emp.id))


@employees_bp.route("/<int:employee_id>/relieve", methods=["GET", "POST"])
@login_required
@people_required
def relieve_employee(employee_id):
    emp = _employee_or_404(employee_id)

    if request.method == "POST":
        emp.relieving_date = _to_date_or_today(request.form.get("relieving_date"))
        emp.termination_reason = request.form.get("termination_reason", "").strip()
        emp.is_active = False
        db.session.commit()
        flash(f"'{emp.full_name}' relieved. Termination and relieving letters are ready to download.", "success")
        return redirect(url_for("employees.list_employees"))

    return render_template("employees/relieve.html", employee=emp)


@employees_bp.route("/<int:employee_id>/appointment-letter")
@login_required
@people_required
def download_appointment_letter(employee_id):
    emp = _employee_or_404(employee_id)
    pdf = appointment_letter(emp)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"appointment-letter-{emp.full_name.replace(' ', '-')}.pdf"
    )


@employees_bp.route("/<int:employee_id>/termination-letter")
@login_required
@people_required
def download_termination_letter(employee_id):
    emp = _employee_or_404(employee_id)
    if not emp.relieving_date:
        flash("Relieve this employee first to set a last working day.", "error")
        return redirect(url_for("employees.list_employees"))
    pdf = termination_letter(emp)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"termination-letter-{emp.full_name.replace(' ', '-')}.pdf"
    )


@employees_bp.route("/<int:employee_id>/relieving-letter")
@login_required
@people_required
def download_relieving_letter(employee_id):
    emp = _employee_or_404(employee_id)
    if not emp.relieving_date:
        flash("Relieve this employee first to set a last working day.", "error")
        return redirect(url_for("employees.list_employees"))
    pdf = relieving_letter(emp)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"relieving-letter-{emp.full_name.replace(' ', '-')}.pdf"
    )


@employees_bp.route("/<int:employee_id>/payslip", methods=["GET", "POST"])
@login_required
@people_required
def download_payslip(employee_id):
    emp = _employee_or_404(employee_id)

    if request.method == "POST":
        month = int(request.form["month"])
        year = int(request.form["year"])

        earnings, deductions = resolve_employee_components(emp, month=month)
        if not earnings and not deductions:
            flash("Set a monthly gross or salary structure before generating a payslip.", "error")
            return redirect(url_for("employees.download_payslip", employee_id=emp.id))

        earnings, deductions, gross, deductions_total, net_pay, unpaid_days = build_payslip_data(emp, month, year)

        # ponytail: no attendance/LWP data exists yet, so deductions here only
        # reflect configured salary-structure deduction components (e.g. PT).
        run = PayrollRun.query.filter_by(employee_id=emp.id, month=month, year=year).first()
        if not run:
            run = PayrollRun(employee_id=emp.id, month=month, year=year)
            db.session.add(run)
        run.gross = gross
        run.deductions = deductions_total
        run.net_pay = net_pay
        run.status = "draft"
        run.approved_by = None
        db.session.commit()

        pdf = payslip(emp, month, year, earnings, deductions, gross, deductions_total, net_pay, lop_days=unpaid_days)
        return send_file(
            pdf, mimetype="application/pdf", as_attachment=True,
            download_name=f"payslip-{emp.full_name.replace(' ', '-')}-{year}-{month:02d}.pdf"
        )

    return render_template("employees/payslip_form.html", employee=emp, today=date.today())


@employees_bp.route("/<int:employee_id>/fy-breakup")
@login_required
@people_required
def download_fy_breakup(employee_id):
    emp = _employee_or_404(employee_id)
    today = date.today()
    default_fy_start = today.year if today.month >= 4 else today.year - 1
    fy_start_year = int(request.args.get("fy", default_fy_start))

    earnings, deductions = resolve_employee_components(emp)
    if not earnings and not deductions:
        flash("Set a monthly gross or salary structure before generating an FY breakup.", "error")
        return redirect(url_for("employees.list_employees"))

    pdf = fy_breakup_letter(emp, fy_start_year)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"fy-breakup-{emp.full_name.replace(' ', '-')}-{fy_start_year}-{fy_start_year + 1}.pdf"
    )


def _cat(components, component_id):
    return next((c.category for c in components if c.id == component_id), "earning")


@employees_bp.route("/<int:employee_id>/checklist", methods=["GET", "POST"])
@login_required
@people_required
def checklist(employee_id):
    employee = _employee_or_404(employee_id)
    if request.method == "POST":
        due_date = request.form.get("due_date")
        item = EmployeeChecklistItem(
            employee_id=employee.id,
            title=request.form.get("title", "").strip(),
            category=request.form.get("category", "onboarding"),
            due_date=datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None,
        )
        db.session.add(item)
        db.session.commit()
        flash("Checklist item added.", "success")
        return redirect(url_for("employees.checklist", employee_id=employee.id))
    items = EmployeeChecklistItem.query.filter_by(employee_id=employee.id).order_by(
        EmployeeChecklistItem.completed, EmployeeChecklistItem.due_date
    ).all()
    return render_template("employees/checklist.html", employee=employee, items=items)


@employees_bp.route("/<int:employee_id>/checklist/<int:item_id>/toggle", methods=["POST"])
@login_required
@people_required
def toggle_checklist(employee_id, item_id):
    item = EmployeeChecklistItem.query.filter_by(id=item_id, employee_id=employee_id).first_or_404()
    item.completed = not item.completed
    db.session.commit()
    return redirect(url_for("employees.checklist", employee_id=employee_id))


def _active_designations():
    return Designation.query.filter_by(is_active=True).order_by(Designation.title).all()


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()


def _employee_or_404(employee_id):
    return Employee.query.filter_by(id=employee_id, company_id=active_company_id()).first_or_404()


def _designation_matches_company(designation_id, company_id):
    if designation_id is None:
        return True
    designation = Designation.query.get(designation_id)
    return designation is not None and designation.company_id == company_id


def _to_int_or_none(value):
    if value in (None, ""):
        return None
    return int(value)


def _to_date_or_today(value):
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _handle_photo_upload(req, emp):
    """Save an uploaded photo for emp. Returns an error message, or None on success/no-op."""
    photo = req.files.get("photo")
    if not photo or not photo.filename:
        return None

    ext = os.path.splitext(secure_filename(photo.filename))[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        return "Photo must be a PNG, JPG, WebP or GIF image."

    if emp.photo_filename:
        _delete_photo(emp.photo_filename)

    filename = f"emp_{emp.id}_{uuid.uuid4().hex[:8]}{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "photos")
    os.makedirs(folder, exist_ok=True)
    photo.save(os.path.join(folder, filename))
    emp.photo_filename = filename
    return None


def _delete_photo(filename):
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], "photos", filename)
    if os.path.exists(path):
        os.remove(path)
