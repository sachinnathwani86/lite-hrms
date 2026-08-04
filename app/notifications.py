from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Notification


notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    notifications = Notification.query.filter_by(employee_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return render_template("notifications/list.html", notifications=notifications)


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id, employee_id=current_user.id
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(notification.link or url_for("notifications.list_notifications"))


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(employee_id=current_user.id, is_read=False).update(
        {Notification.is_read: True}
    )
    db.session.commit()
    return redirect(url_for("notifications.list_notifications"))
