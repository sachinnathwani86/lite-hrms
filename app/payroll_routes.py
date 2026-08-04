from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.activity import notify, record_audit
from app.admin import people_required
from app.extensions import db
from app.models import Employee, PayrollRun
from app.workspace import active_company_id


payroll_bp = Blueprint("payroll_admin", __name__, url_prefix="/admin/payroll")


@payroll_bp.route("/")
@login_required
@people_required
def history():
    runs = PayrollRun.query.join(PayrollRun.employee).filter(Employee.company_id == active_company_id()).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).limit(200).all()
    return render_template("payroll/history.html", runs=runs)


@payroll_bp.route("/<int:run_id>/approve", methods=["POST"])
@login_required
@people_required
def approve(run_id):
    run = PayrollRun.query.get_or_404(run_id)
    if run.employee.company_id != active_company_id():
        return redirect(url_for("payroll_admin.history"))
    run.status = "approved"
    run.approved_by = current_user.id
    notify(run.employee_id, "Payroll approved", f"Your payslip for {run.month:02d}/{run.year} has been approved.", "/me/profile")
    record_audit(current_user, "approve", "payroll_run", run.id, f"Approved payroll for {run.employee.full_name}")
    db.session.commit()
    flash("Payroll run approved.", "success")
    return redirect(url_for("payroll_admin.history"))
