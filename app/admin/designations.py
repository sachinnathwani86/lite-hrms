from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from app.extensions import db
from app.models import Designation, Company
from app.admin import people_required
from app.workspace import active_company_id

designations_bp = Blueprint("designations", __name__, url_prefix="/admin/designations")


@designations_bp.route("/")
@login_required
@people_required
def list_designations():
    designations = Designation.query.filter_by(company_id=active_company_id()).order_by(Designation.title).all()
    return render_template("designations/list.html", designations=designations)


@designations_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_designation():
    if request.method == "POST":
        title = request.form["title"].strip()
        company_id = active_company_id()
        if Designation.query.filter_by(title=title, company_id=company_id).first():
            flash(f"A designation titled '{title}' already exists at this company.", "error")
            return render_template("designations/form.html", designation=None, companies=_active_companies())

        d = Designation(title=title, company_id=company_id)
        db.session.add(d)
        db.session.commit()
        flash(f"Designation '{d.title}' created.", "success")
        return redirect(url_for("designations.list_designations"))

    return render_template("designations/form.html", designation=None, companies=_active_companies())


@designations_bp.route("/<int:designation_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_designation(designation_id):
    d = Designation.query.get_or_404(designation_id)

    if request.method == "POST":
        title = request.form["title"].strip()
        company_id = active_company_id()
        existing = Designation.query.filter_by(title=title, company_id=company_id).first()
        if existing and existing.id != d.id:
            flash(f"A designation titled '{title}' already exists at this company.", "error")
            return render_template("designations/form.html", designation=d, companies=_active_companies())

        d.title = title
        d.company_id = company_id
        d.is_active = bool(request.form.get("is_active"))
        db.session.commit()
        flash(f"Designation '{d.title}' updated.", "success")
        return redirect(url_for("designations.list_designations"))

    return render_template("designations/form.html", designation=d, companies=_active_companies())


@designations_bp.route("/<int:designation_id>/delete", methods=["POST"])
@login_required
@people_required
def delete_designation(designation_id):
    d = Designation.query.get_or_404(designation_id)
    # Soft-delete: deactivate instead of hard delete, so history stays intact
    d.is_active = False
    db.session.commit()
    flash(f"Designation '{d.title}' deactivated.", "success")
    return redirect(url_for("designations.list_designations"))


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()
