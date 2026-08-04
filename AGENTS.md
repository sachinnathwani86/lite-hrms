# Repository Instructions

## Project Shape

- This is a small server-rendered Flask HRMS product. Keep client-facing names, domains, emails, and infrastructure configurable; never hardcode a customer or hosting infrastructure.
- `run.py` exposes the WSGI object (`run:app`); `app/create_app` initializes extensions and is the only place blueprints are registered. New routes require an import and `app.register_blueprint(...)` there.
- All SQLAlchemy models are in `app/models.py`. Feature routes live in `app/` and admin CRUD routes in `app/admin/`; templates extend `app/templates/base.html`, and shared styling is in `app/static/css/style.css`.
- The app is server-rendered Jinja2 with Flask-Login; do not introduce an SPA or API layer for ordinary feature work.

## Local Commands

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- Create a local `.env` with at least `SECRET_KEY` and optionally `DATABASE_URL` (SQLite `hrms.db` is the default; production uses PostgreSQL). There is currently no checked-in `.env.example`.
- Apply the existing migrations: `flask db upgrade`. Do not run `flask db init` in a checkout that already has `migrations/`; first-run setup is completed at `/setup`.
- Run locally with `flask run` or `python run.py`; the default URL is `http://localhost:5000/login`.
- Production runs `gunicorn -w 3 -b 127.0.0.1:8000 run:app` behind nginx/systemd; uploaded files must remain writable at `UPLOAD_FOLDER`.

## Data And Permissions

- This is a single-company deployment. `Company` remains as the parent profile record for existing foreign keys, but do not add company switching, tenant selection, or multi-company UI.
- `Employee`, `Candidate`, `Designation`, `SalaryComponent`, `LeaveType`, and `Holiday` retain `company_id` for schema/history; all application queries and forms must stay within the configured company.
- `LeaveBalance`, `LeaveRequest`, `Attendance`, `EmployeeSalary`, and `PayrollRun` inherit company scope through their employee/leave-type/component foreign keys; do not add redundant `company_id` fields.
- Login is company-scoped: email is looked up without a company selector, against the single active company profile. Roles are `admin`, `hr_manager`, `manager`, and `employee`; use `people_required` or `approver_required` from `app.admin` instead of widening permissions accidentally.
- Preserve the explicit `foreign_keys` configuration on `Employee.leave_requests` and `LeaveRequest.approver`; `LeaveRequest` has two foreign keys to `employees`.
- New HR models should follow the existing employee/company foreign-key pattern; do not expose a company selector in new forms.

## Feature Constraints

- Form routes use GET to render and POST to process, with Flask flash messages for feedback. Keep feature logic in the route/module rather than adding an unnecessary abstraction layer.
- Employee CSV import is at `app/admin/employees.py`; validate company/designation ownership and never include plaintext passwords in logs or exported data.
- Leave days count weekdays only; holiday exclusion is not implemented. Leave requests enforce notice and balance rules, and non-approval leave types auto-approve.
- Attendance marking uses the company's optional office coordinates and a 100-meter geofence when configured; the employee/date uniqueness constraint must be preserved.
- Payroll generates payslips from configured salary components or the monthly-gross breakup, with attendance-based loss-of-pay deductions and payroll approval history.
- PDF letters and payslips are generated with ReportLab. Letterhead images are read from `UPLOAD_FOLDER/letterheads`; employee photos use `UPLOAD_FOLDER/photos`, with a 2 MB upload cap.
- Employee self-service lives in `app/self_service.py`: profile changes and documents are always filtered to `current_user.id`; private documents belong under `DOCUMENT_UPLOAD_FOLDER/<employee_id>` and must be served through the authenticated route, not static URLs.
- All state-changing forms use the custom CSRF token injected by `app/security.py`; preserve it when adding POST forms. Logout is POST-only.
- First-run setup is `/setup`; company name, legal details, contact details, office coordinates, and letterhead are stored in the singleton `Company` profile and drive product branding/PDFs.
- Money values use `Numeric(10, 2)`/`Decimal`, not floats. Keep the existing Indian payroll assumptions in `app/payroll.py` unless the business requirement changes.

## Verification And Migrations

- There is no test suite or CI configuration. Run `python -m py_compile $(find app -name '*.py')` after Python changes and `python -m app.payroll` to exercise the payroll module's built-in assertions.
- Model changes require a migration: `flask db migrate -m "message"`, inspect the generated revision, then `flask db upgrade`. Commit migration revisions with the model change. Scheduled leave accrual runs with `flask accrue-leave --year YYYY --month M`; local SQLite backups use `flask backup-db`.
- Keep generated PDFs, uploads, `.env`, databases, and other runtime data out of source control.

See `README.md` for VPS deployment and handover details; verify it against executable code when it conflicts with this file.
