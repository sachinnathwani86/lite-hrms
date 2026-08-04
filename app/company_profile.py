import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.admin import people_required
from app.activity import record_audit
from app.extensions import db
from app.models import Company


company_profile_bp = Blueprint("company_profile", __name__, url_prefix="/admin/company-profile")
ALLOWED_LETTERHEAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@company_profile_bp.route("/", methods=["GET", "POST"])
@login_required
@people_required
def edit_profile():
    company = Company.query.filter_by(id=current_user.company_id).first_or_404()
    if request.method == "POST":
        company.name = request.form.get("name", "").strip()
        company.legal_name = request.form.get("legal_name", "").strip() or None
        company.address = request.form.get("address", "").strip() or None
        company.phone = request.form.get("phone", "").strip() or None
        company.email = request.form.get("email", "").strip().lower() or None
        company.website = request.form.get("website", "").strip() or None
        company.office_latitude = _float_or_none(request.form.get("office_latitude"))
        company.office_longitude = _float_or_none(request.form.get("office_longitude"))

        if not company.name:
            flash("Company name is required.", "error")
            return render_template("company_profile/form.html", company=company)

        upload = request.files.get("letterhead")
        if upload and upload.filename:
            extension = os.path.splitext(upload.filename)[1].lower()
            if extension not in ALLOWED_LETTERHEAD_EXTENSIONS:
                flash("Letterhead must be a PNG, JPG, JPEG, or WebP image.", "error")
                return render_template("company_profile/form.html", company=company)
            folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "letterheads")
            os.makedirs(folder, exist_ok=True)
            filename = f"company_{company.id}_letterhead{extension}"
            upload.save(os.path.join(folder, filename))
            company.letterhead_filename = filename

        if request.form.get("remove_letterhead") and company.letterhead_filename:
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], "letterheads", company.letterhead_filename)
            if os.path.exists(path):
                os.remove(path)
            company.letterhead_filename = None

        record_audit(current_user, "update", "company", company.id, "Updated company profile")
        db.session.commit()
        flash("Company profile updated.", "success")
        return redirect(url_for("company_profile.edit_profile"))

    return render_template("company_profile/form.html", company=company)


def _float_or_none(value):
    value = (value or "").strip()
    return float(value) if value else None
