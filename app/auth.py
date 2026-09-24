import hashlib

from flask import Blueprint, current_app, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from app.models import Company, Employee, LeaveType, SalaryComponent
from app.activity import record_audit
from app.extensions import db
from app.mailer import mail_configured, send_email

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


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def _password_fingerprint(user):
    # Tying the token to the current hash makes it single-use: it stops
    # verifying as soon as the password changes.
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def _active_company():
    return Company.query.filter_by(is_active=True).order_by(Company.id).first()


def _user_from_reset_token(token):
    try:
        data = _reset_serializer().loads(
            token, max_age=current_app.config["PASSWORD_RESET_MAX_AGE"]
        )
    except (SignatureExpired, BadSignature):
        return None
    company = _active_company()
    if not company or not isinstance(data, dict):
        return None
    user = Employee.query.filter_by(
        id=data.get("id"), company_id=company.id, is_active=True
    ).first()
    if not user or data.get("fp") != _password_fingerprint(user):
        return None
    return user


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("auth.change_password"))
    if request.method == "POST":
        if not mail_configured():
            flash("Password reset by email is not available. Please contact your HR administrator.", "error")
            return render_template("auth/forgot_password.html")
        email = request.form.get("email", "").strip().lower()
        company = _active_company()
        user = Employee.query.filter_by(
            email=email, company_id=company.id, is_active=True
        ).first() if company and email else None
        if user:
            token = _reset_serializer().dumps({"id": user.id, "fp": _password_fingerprint(user)})
            path = url_for("auth.reset_password", token=token)
            base_url = current_app.config.get("APP_BASE_URL")
            link = f"{base_url}{path}" if base_url else url_for("auth.reset_password", token=token, _external=True)
            minutes = current_app.config["PASSWORD_RESET_MAX_AGE"] // 60
            try:
                send_email(
                    user.email,
                    f"Reset your {company.name} HRMS password",
                    f"Hello {user.full_name},\n\n"
                    f"We received a request to reset your password. Use the link below "
                    f"within {minutes} minutes to choose a new one:\n\n{link}\n\n"
                    f"If you did not request this, you can ignore this email.\n",
                )
            except Exception:
                current_app.logger.exception("Password reset email could not be sent (employee id %s)", user.id)
                flash("We could not send the reset email right now. Please try again later.", "error")
                return render_template("auth/forgot_password.html")
        # Same response whether or not the email exists, to avoid account enumeration.
        flash("If that email belongs to an active account, a password reset link has been sent.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = _user_from_reset_token(token)
    if not user:
        flash("This password reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        if len(new_password) < 8:
            flash("Your new password must be at least 8 characters.", "error")
        elif new_password != confirmation:
            flash("The new passwords do not match.", "error")
        else:
            user.set_password(new_password)
            record_audit(user, "reset_password", "employee", user.id, "Reset own password via email link")
            db.session.commit()
            flash("Your password has been reset. Sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)
