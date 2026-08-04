from app.extensions import db
from app.models import AuditLog, Notification


def record_audit(actor, action, entity, entity_id=None, details=None):
    db.session.add(AuditLog(
        company_id=actor.company_id if actor else None,
        actor_id=actor.id if actor else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
    ))


def notify(employee_id, title, message, link=None):
    db.session.add(Notification(
        employee_id=employee_id,
        title=title,
        message=message,
        link=link,
    ))
