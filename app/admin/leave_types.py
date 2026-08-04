from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from app.extensions import db
from app.models import LeaveType, Company
from app.admin import people_required
from app.workspace import active_company_id

leave_types_bp = Blueprint("leave_types", __name__, url_prefix="/admin/leave-types")


@leave_types_bp.route("/")
@login_required
@people_required
def list_leave_types():
    types = LeaveType.query.filter_by(company_id=active_company_id()).order_by(LeaveType.name).all()
    return render_template("leave_types/list.html", types=types)


@leave_types_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_leave_type():
    if request.method == "POST":
        name = request.form["name"].strip()
        company_id = active_company_id()
        if LeaveType.query.filter_by(name=name, company_id=company_id).first():
            flash(f"A leave type named '{name}' already exists at this company.", "error")
            return render_template("leave_types/form.html", leave_type=None, companies=_active_companies())

        lt = LeaveType(
            name=name,
            company_id=company_id,
            annual_quota=float(request.form.get("annual_quota", 0)),
            accrual_type=request.form.get("accrual_type", "yearly_upfront"),
            carry_forward=bool(request.form.get("carry_forward")),
            max_carry_forward=_to_float_or_none(request.form.get("max_carry_forward")),
            requires_approval=bool(request.form.get("requires_approval")),
            min_days_notice=int(request.form.get("min_days_notice", 0)),
            allow_negative_balance=bool(request.form.get("allow_negative_balance")),
        )
        db.session.add(lt)
        db.session.commit()
        flash(f"Leave type '{lt.name}' created.", "success")
        return redirect(url_for("leave_types.list_leave_types"))

    return render_template("leave_types/form.html", leave_type=None, companies=_active_companies())


@leave_types_bp.route("/<int:leave_type_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_leave_type(leave_type_id):
    lt = LeaveType.query.get_or_404(leave_type_id)

    if request.method == "POST":
        name = request.form["name"].strip()
        company_id = active_company_id()
        existing = LeaveType.query.filter_by(name=name, company_id=company_id).first()
        if existing and existing.id != lt.id:
            flash(f"A leave type named '{name}' already exists at this company.", "error")
            return render_template("leave_types/form.html", leave_type=lt, companies=_active_companies())

        lt.name = name
        lt.company_id = company_id
        lt.annual_quota = float(request.form.get("annual_quota", 0))
        lt.accrual_type = request.form.get("accrual_type", "yearly_upfront")
        lt.carry_forward = bool(request.form.get("carry_forward"))
        lt.max_carry_forward = _to_float_or_none(request.form.get("max_carry_forward"))
        lt.requires_approval = bool(request.form.get("requires_approval"))
        lt.min_days_notice = int(request.form.get("min_days_notice", 0))
        lt.allow_negative_balance = bool(request.form.get("allow_negative_balance"))
        lt.is_active = bool(request.form.get("is_active"))
        db.session.commit()
        flash(f"Leave type '{lt.name}' updated.", "success")
        return redirect(url_for("leave_types.list_leave_types"))

    return render_template("leave_types/form.html", leave_type=lt, companies=_active_companies())


@leave_types_bp.route("/<int:leave_type_id>/delete", methods=["POST"])
@login_required
@people_required
def delete_leave_type(leave_type_id):
    lt = LeaveType.query.get_or_404(leave_type_id)
    # Soft-delete: deactivate instead of hard delete, so history stays intact
    lt.is_active = False
    db.session.commit()
    flash(f"Leave type '{lt.name}' deactivated.", "success")
    return redirect(url_for("leave_types.list_leave_types"))


def _to_float_or_none(value):
    if value in (None, ""):
        return None
    return float(value)


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()
