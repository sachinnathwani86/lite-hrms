from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Company, Employee, LeaveType, SalaryComponent
from app.activity import record_audit
from app.extensions import db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))
    if not Company.query.filter_by(is_active=True).first():
        return redirect(url_for("auth.setup"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if not Company.query.filter_by(is_active=True).first():
        return redirect(url_for("auth.setup"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        company = Company.query.filter_by(is_active=True).order_by(Company.id).first()
        user = Employee.query.filter(
            db.func.lower(Employee.username) == username.lower(),
            Employee.company_id == company.id,
            Employee.is_active == True,
        ).first() if company and username else None

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard.home"))

        flash("Invalid user ID or password", "error")

    return render_template("auth/login.html")


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if Company.query.filter_by(is_active=True).first():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        admin_name = request.form.get("admin_name", "").strip()
        admin_username = request.form.get("admin_username", "").strip()
        admin_email = request.form.get("admin_email", "").strip().lower() or None
        password = request.form.get("password", "")
        if not company_name or not admin_name or not admin_username:
            flash("Company name, administrator name, and user ID are required.", "error")
        elif len(password) < 8:
            flash("The administrator password must be at least 8 characters.", "error")
        elif Employee.query.filter(db.func.lower(Employee.username) == admin_username.lower()).first():
            flash("That administrator user ID is already in use.", "error")
        else:
            company = Company(
                name=company_name,
                legal_name=request.form.get("legal_name", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                email=request.form.get("company_email", "").strip().lower() or None,
                website=request.form.get("website", "").strip() or None,
            )
            db.session.add(company)
            db.session.flush()
            admin = Employee(
                company_id=company.id,
                full_name=admin_name,
                username=admin_username,
                email=admin_email,
                role="admin",
            )
            admin.set_password(password)
            db.session.add(admin)
            for values in [
                dict(name="Casual", annual_quota=12, accrual_type="yearly_upfront"),
                dict(name="Sick", annual_quota=8, accrual_type="yearly_upfront"),
                dict(name="Earned", annual_quota=15, accrual_type="monthly", carry_forward=True, max_carry_forward=30),
            ]:
                db.session.add(LeaveType(company_id=company.id, **values))
            for component_name in ["Basic", "HRA", "Conveyance", "Medical Allowance", "Special Allowance"]:
                db.session.add(SalaryComponent(company_id=company.id, name=component_name, category="earning"))
            db.session.add(SalaryComponent(company_id=company.id, name="Professional Tax", category="deduction"))
            db.session.commit()
            flash("Setup complete. Sign in to continue.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/setup.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        if not current_user.check_password(current):
            flash("Your current password is incorrect.", "error")
        elif len(new_password) < 8:
            flash("Your new password must be at least 8 characters.", "error")
        elif new_password != confirmation:
            flash("The new passwords do not match.", "error")
        else:
            current_user.set_password(new_password)
            from app.extensions import db
            record_audit(current_user, "change_password", "employee", current_user.id, "Changed own password")
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for("dashboard.home"))
    return render_template("auth/change_password.html")
