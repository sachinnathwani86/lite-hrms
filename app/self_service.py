import os
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.admin import people_required
from app.activity import record_audit
from app.extensions import db
from app.models import Employee, EmployeeDocument
from app.workspace import active_company_id


self_service_bp = Blueprint("self_service", __name__, url_prefix="/me")
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}


@self_service_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        existing = Employee.query.filter_by(email=email, company_id=current_user.company_id).first()
        if existing and existing.id != current_user.id:
            flash("That email address is already used in your company.", "error")
        elif not email:
            flash("Email is required.", "error")
        else:
            current_user.full_name = request.form.get("full_name", "").strip()
            current_user.email = email
            record_audit(current_user, "update", "employee", current_user.id, "Updated self-service profile")
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("self_service.profile"))

    documents = EmployeeDocument.query.filter_by(employee_id=current_user.id).order_by(
        EmployeeDocument.uploaded_on.desc()
    ).all()
    return render_template("self_service/profile.html", documents=documents)


@self_service_bp.route("/documents/upload", methods=["POST"])
@login_required
def upload_document():
    upload = request.files.get("document")
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "other").strip() or "other"
    if not upload or not upload.filename or not title:
        flash("A document title and file are required.", "error")
        return redirect(url_for("self_service.profile"))

    extension = os.path.splitext(upload.filename)[1].lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        flash("Documents must be PDF, Word, JPG, PNG, or JPEG files.", "error")
        return redirect(url_for("self_service.profile"))

    filename = f"{uuid.uuid4().hex}{extension}"
    folder = os.path.join(current_app.config["DOCUMENT_UPLOAD_FOLDER"], str(current_user.id))
    os.makedirs(folder, exist_ok=True)
    upload.save(os.path.join(folder, filename))
    db.session.add(EmployeeDocument(
        employee_id=current_user.id,
        title=title,
        category=category,
        filename=filename,
    ))
    record_audit(current_user, "upload", "employee_document", None, f"Uploaded {title}")
    db.session.commit()
    flash("Document uploaded successfully.", "success")
    return redirect(url_for("self_service.profile"))


@self_service_bp.route("/documents/<int:document_id>")
@login_required
def download_document(document_id):
    document = EmployeeDocument.query.filter_by(
        id=document_id, employee_id=current_user.id
    ).first_or_404()
    path = os.path.join(
        current_app.config["DOCUMENT_UPLOAD_FOLDER"], str(current_user.id), document.filename
    )
    return send_file(path, as_attachment=True, download_name=secure_filename(document.title) + os.path.splitext(document.filename)[1])


@self_service_bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_document(document_id):
    document = EmployeeDocument.query.filter_by(
        id=document_id, employee_id=current_user.id
    ).first_or_404()
    path = os.path.join(
        current_app.config["DOCUMENT_UPLOAD_FOLDER"], str(current_user.id), document.filename
    )
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(document)
    record_audit(current_user, "delete", "employee_document", document.id, f"Removed {document.title}")
    db.session.commit()
    flash("Document removed.", "success")
    return redirect(url_for("self_service.profile"))


@self_service_bp.route("/password-reset/<int:employee_id>", methods=["POST"])
@login_required
@people_required
def reset_employee_password(employee_id):
    employee = Employee.query.filter_by(id=employee_id, company_id=active_company_id()).first_or_404()
    temporary_password = uuid.uuid4().hex[:12]
    employee.set_password(temporary_password)
    record_audit(current_user, "reset_password", "employee", employee.id, "Generated temporary password")
    db.session.commit()
    flash(f"Temporary password for {employee.full_name}: {temporary_password}", "success")
    return redirect(url_for("employees.edit_employee", employee_id=employee.id))
