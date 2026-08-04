from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from app.extensions import db
from app.models import Holiday, Company
from app.admin import people_required
from app.workspace import active_company_id

# The holiday list itself is visible to every logged-in employee;
# only add/edit/delete are admin-only.
holidays_bp = Blueprint("holidays", __name__, url_prefix="/holidays")


@holidays_bp.route("/")
@login_required
def list_holidays():
    holidays = Holiday.query.filter_by(company_id=active_company_id()).order_by(Holiday.date).all()
    return render_template("holidays/list.html", holidays=holidays)


@holidays_bp.route("/new", methods=["GET", "POST"])
@login_required
@people_required
def create_holiday():
    if request.method == "POST":
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        company_id = active_company_id()
        if Holiday.query.filter_by(date=date, company_id=company_id).first():
            flash(f"A holiday already exists on {date} for this company.", "error")
            return render_template("holidays/form.html", holiday=None, companies=_active_companies())

        h = Holiday(name=request.form["name"].strip(), date=date, company_id=company_id)
        db.session.add(h)
        db.session.commit()
        flash(f"Holiday '{h.name}' added.", "success")
        return redirect(url_for("holidays.list_holidays"))

    return render_template("holidays/form.html", holiday=None, companies=_active_companies())


@holidays_bp.route("/<int:holiday_id>/edit", methods=["GET", "POST"])
@login_required
@people_required
def edit_holiday(holiday_id):
    h = Holiday.query.get_or_404(holiday_id)

    if request.method == "POST":
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        company_id = active_company_id()
        existing = Holiday.query.filter_by(date=date, company_id=company_id).first()
        if existing and existing.id != h.id:
            flash(f"A holiday already exists on {date} for this company.", "error")
            return render_template("holidays/form.html", holiday=h, companies=_active_companies())

        h.name = request.form["name"].strip()
        h.date = date
        h.company_id = company_id
        db.session.commit()
        flash(f"Holiday '{h.name}' updated.", "success")
        return redirect(url_for("holidays.list_holidays"))

    return render_template("holidays/form.html", holiday=h, companies=_active_companies())


@holidays_bp.route("/<int:holiday_id>/delete", methods=["POST"])
@login_required
@people_required
def delete_holiday(holiday_id):
    h = Holiday.query.get_or_404(holiday_id)
    # Hard delete is fine here: nothing references a holiday row
    db.session.delete(h)
    db.session.commit()
    flash(f"Holiday '{h.name}' deleted.", "success")
    return redirect(url_for("holidays.list_holidays"))


def _active_companies():
    return Company.query.filter_by(id=active_company_id(), is_active=True).all()
