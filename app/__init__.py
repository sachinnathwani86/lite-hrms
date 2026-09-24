import click
import os
import shutil
from datetime import datetime
from flask import Flask
from config import Config
from app.extensions import db, login_manager, migrate
from app.security import init_security


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    init_security(app)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    from app.models import Employee

    @login_manager.user_loader
    def load_user(user_id):
        return Employee.query.get(int(user_id))

    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.self_service import self_service_bp
    from app.notifications import notifications_bp
    from app.audit import audit_bp
    from app.reports import reports_bp
    from app.payroll_routes import payroll_bp
    from app.company_profile import company_profile_bp
    from app.leave_requests import leave_requests_bp
    from app.attendance import attendance_bp
    from app.admin.leave_types import leave_types_bp
    from app.admin.employees import employees_bp
    from app.admin.designations import designations_bp
    from app.admin.salary_components import salary_components_bp
    from app.admin.holidays import holidays_bp
    from app.admin.candidates import candidates_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(self_service_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(company_profile_bp)

    @app.get("/health")
    def health():
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.cli.command("accrue-leave")
    @click.option("--year", type=int)
    @click.option("--month", type=int)
    def accrue_leave_command(year, month):
        """Apply monthly leave accruals and carry-forward balances."""
        from app.leave_accrual import run_accrual
        changed = run_accrual(year, month)
        print(f"Updated {changed} leave balances.")

    @app.cli.command("reset-password")
    @click.option("--email", required=True, help="Login email of the employee.")
    @click.password_option()
    def reset_password_command(email, password):
        """Set a new password for an employee (for server administrators)."""
        from app.models import AuditLog
        user = Employee.query.filter_by(email=email.strip().lower()).first()
        if not user:
            raise click.ClickException("No employee with that email.")
        if len(password) < 8:
            raise click.ClickException("The password must be at least 8 characters.")
        user.set_password(password)
        db.session.add(AuditLog(
            company_id=user.company_id, action="reset_password", entity="employee",
            entity_id=user.id, details="Password reset from the command line",
        ))
        db.session.commit()
        print(f"Password updated for {user.email}.")

    @app.cli.command("backup-db")
    def backup_db_command():
        """Create a timestamped backup for the local SQLite database."""
        database_url = app.config["SQLALCHEMY_DATABASE_URI"]
        if not database_url.startswith("sqlite:///"):
            raise click.ClickException("Use your PostgreSQL backup policy (pg_dump) for non-SQLite databases.")
        source = database_url.removeprefix("sqlite:///")
        os.makedirs(app.config["BACKUP_FOLDER"], exist_ok=True)
        target = os.path.join(
            app.config["BACKUP_FOLDER"], f"hrms-{datetime.now():%Y%m%d-%H%M%S}.db"
        )
        shutil.copy2(source, target)
        print(f"Backup created: {target}")

    @app.context_processor
    def notification_context():
        from flask_login import current_user
        from app.models import Notification
        from app.workspace import active_company
        unread_count = 0
        workspace = None
        if current_user.is_authenticated:
            unread_count = Notification.query.filter_by(
                employee_id=current_user.id, is_read=False
            ).count()
            workspace = active_company()
        return {
            "unread_notification_count": unread_count,
            "active_workspace": workspace,
        }
    app.register_blueprint(leave_requests_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(leave_types_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(designations_bp)
    app.register_blueprint(salary_components_bp)
    app.register_blueprint(holidays_bp)
    app.register_blueprint(candidates_bp)

    return app
