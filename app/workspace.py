from flask_login import current_user


def active_company_id():
    return current_user.company_id if current_user.is_authenticated else None


def active_company():
    from app.models import Company
    company_id = active_company_id()
    return Company.query.get(company_id) if company_id else None


def ensure_active_company(company_id):
    return company_id == active_company_id()
