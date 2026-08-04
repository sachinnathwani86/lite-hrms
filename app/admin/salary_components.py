from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from app.extensions import db
from app.models import SalaryComponent, Company
from app.admin import people_required
from app.workspace import active_company_id

salary_components_bp = Blueprint("salary_components", __name__, url_prefix="/admin/salary-components")


@salary_components_bp.route("/")
@login_required
@people_required
def list_salary_components():
    # earnings first, then deductions
    components = SalaryComponent.query.filter_by(company_id=active_company_id()).order_by(
        SalaryComponent.category.desc(), SalaryComponent.name
    ).all()
    return render_template("salary_components/list.html", components=components)


@salary_components_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_salary_component():
    if request.method == "POST":
        name = request.form["name"].strip()
        company_id = active_company_id()
        if SalaryComponent.query.filter_by(name=name, company_id=company_id).first():
            flash(f"A salary component named '{name}' already exists at this company.", "error")
            return render_template("salary_components/form.html", component=None, companies=_active_companies())

        c = SalaryComponent(
            name=name,
            company_id=company_id,
            category=request.form.get("category", "earning"),
        )
        db.session.add(c)
        db.session.commit()
        flash(f"Salary component '{c.name}' created.", "success")
        return redirect(url_for("salary_components.list_salary_components"))

    return render_template("salary_components/form.html", component=None, companies=_active_companies())


@salary_components_bp.route("/<int:component_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_salary_component(component_id):
    c = SalaryComponent.query.get_or_404(component_id)

    if request.method == "POST":
        name = request.form["name"].strip()
        company_id = active_company_id()
        existing = SalaryComponent.query.filter_by(name=name, company_id=company_id).first()
        if existing and existing.id != c.id:
            flash(f"A salary component named '{name}' already exists at this company.", "error")
            return render_template("salary_components/form.html", component=c, companies=_active_companies())

        c.name = name
        c.company_id = company_id
        c.category = request.form.get("category", "earning")
        c.is_active = bool(request.form.get("is_active"))
        db.session.commit()
        flash(f"Salary component '{c.name}' updated.", "success")
        return redirect(url_for("salary_components.list_salary_components"))

    return render_template("salary_components/form.html", component=c, companies=_active_companies())


@salary_components_bp.route("/<int:component_id>/delete", methods=["POST"])
@login_required
@people_required
def delete_salary_component(component_id):
    c = SalaryComponent.query.get_or_404(component_id)
    # Soft-delete: deactivate instead of hard delete, so history stays intact
    c.is_active = False
    db.session.commit()
    flash(f"Salary component '{c.name}' deactivated.", "success")
    return redirect(url_for("salary_components.list_salary_components"))


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()
