from flask import Blueprint, render_template
from flask_login import login_required

from app.admin import people_required
from app.models import AuditLog
from app.workspace import active_company_id


audit_bp = Blueprint("audit", __name__, url_prefix="/admin/audit")


@audit_bp.route("/")
@login_required
@people_required
def list_audit_logs():
    logs = AuditLog.query.filter_by(company_id=active_company_id()).order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("audit/list.html", logs=logs)
