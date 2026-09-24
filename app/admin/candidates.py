from datetime import date, datetime
import secrets
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_file
from flask_login import login_required
from app.extensions import db
from app.models import Candidate, Employee, LeaveType, LeaveBalance, Designation, Company
from app.admin import people_required
from app.letters import offer_letter
from app.workspace import active_company_id

candidates_bp = Blueprint("candidates", __name__, url_prefix="/admin/candidates")


@candidates_bp.route("/")
@login_required
@people_required
def list_candidates():
    candidates = Candidate.query.filter_by(company_id=active_company_id()).order_by(Candidate.offer_date.desc()).all()
    return render_template("candidates/list.html", candidates=candidates)


@candidates_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_candidate():
    if request.method == "POST":
        company_id = active_company_id()
        candidate = Candidate(
            company_id=company_id,
            full_name=request.form["full_name"].strip(),
            email=_to_email_or_none(request.form.get("email")),
            designation_id=_to_int_or_none(request.form.get("designation_id")),
            proposed_salary=Decimal(request.form.get("proposed_salary") or 0),
            offer_date=_to_date_or_today(request.form.get("offer_date")),
        )
        db.session.add(candidate)
        db.session.commit()
        flash(f"Candidate '{candidate.full_name}' added.", "success")
        return redirect(url_for("candidates.list_candidates"))

    return render_template(
        "candidates/form.html", candidate=None,
        designations=_active_designations(), companies=_active_companies()
    )


@candidates_bp.route("/<int:candidate_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_candidate(candidate_id):
    candidate = _candidate_or_404(candidate_id)

    if request.method == "POST":
        candidate.company_id = active_company_id()
        candidate.full_name = request.form["full_name"].strip()
        candidate.email = _to_email_or_none(request.form.get("email"))
        candidate.designation_id = _to_int_or_none(request.form.get("designation_id"))
        candidate.proposed_salary = Decimal(request.form.get("proposed_salary") or 0)
        candidate.offer_date = _to_date_or_today(request.form.get("offer_date"))
        candidate.status = request.form.get("status", candidate.status)
        db.session.commit()
        flash(f"Candidate '{candidate.full_name}' updated.", "success")
        return redirect(url_for("candidates.list_candidates"))

    return render_template(
        "candidates/form.html", candidate=candidate,
        designations=_active_designations(), companies=_active_companies()
    )


@candidates_bp.route("/<int:candidate_id>/offer-letter")
@login_required
@people_required
def download_offer_letter(candidate_id):
    candidate = _candidate_or_404(candidate_id)
    pdf = offer_letter(candidate)
    return send_file(
        pdf, mimetype="application/pdf", as_attachment=True,
        download_name=f"offer-letter-{candidate.full_name.replace(' ', '-')}.pdf"
    )


@candidates_bp.route("/<int:candidate_id>/mark-joined", methods=["POST"])
@login_required
@people_required
def mark_joined(candidate_id):
    candidate = _candidate_or_404(candidate_id)
    if candidate.status == "joined":
        flash("Candidate has already joined.", "error")
        return redirect(url_for("candidates.list_candidates"))

    email = candidate.email
    if email and Employee.query.filter_by(email=email, company_id=candidate.company_id).first():
        flash(f"An employee with email '{email}' already exists at this company.", "error")
        return redirect(url_for("candidates.list_candidates"))

    joining_date = _to_date_or_today(request.form.get("joining_date"))
    emp = Employee(
        company_id=candidate.company_id,
        full_name=candidate.full_name,
        username=_unique_username(candidate.company_id, candidate.full_name, email),
        email=email,
        role="employee",
        designation_id=candidate.designation_id,
        date_of_joining=joining_date,
        monthly_gross=candidate.proposed_salary,
    )
    emp.set_password(request.form.get("password") or secrets.token_urlsafe(12))
    db.session.add(emp)
    db.session.flush()

    for lt in LeaveType.query.filter_by(is_active=True, company_id=emp.company_id).all():
        db.session.add(LeaveBalance(
            employee_id=emp.id,
            leave_type_id=lt.id,
            year=date.today().year,
            opening_balance=lt.annual_quota if lt.accrual_type == "yearly_upfront" else 0,
        ))

    candidate.status = "joined"
    candidate.joining_date = joining_date
    candidate.employee_id = emp.id
    db.session.commit()
    flash(f"'{candidate.full_name}' converted to employee. Set or reset their password before sharing access.", "success")
    return redirect(url_for("employees.edit_employee", employee_id=emp.id))


@candidates_bp.route("/<int:candidate_id>/reject", methods=["POST"])
@login_required
@people_required
def reject_candidate(candidate_id):
    candidate = _candidate_or_404(candidate_id)
    candidate.status = "rejected"
    db.session.commit()
    flash(f"Candidate '{candidate.full_name}' marked as rejected.", "success")
    return redirect(url_for("candidates.list_candidates"))


def _active_designations():
    return Designation.query.filter_by(is_active=True).order_by(Designation.title).all()


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()


def _candidate_or_404(candidate_id):
    return Candidate.query.filter_by(id=candidate_id, company_id=active_company_id()).first_or_404()


def _to_email_or_none(value):
    value = (value or "").strip().lower()
    return value or None


def _unique_username(company_id, full_name, email):
    base = ((email or "").split("@")[0] or full_name or "employee").strip().lower()
    base = "".join(ch for ch in base if ch.isalnum() or ch in "._-") or "employee"
    username = base
    suffix = 1
    while Employee.query.filter(db.func.lower(Employee.username) == username.lower(), Employee.company_id == company_id).first():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def _to_int_or_none(value):
    if value in (None, ""):
        return None
    return int(value)


def _to_date_or_today(value):
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()
