# Lite HRMS

Lite HRMS is a lightweight, server-rendered HR management product built with
Flask, SQLAlchemy, Flask-Login, and ReportLab. It is designed for a single
company deployment and keeps company branding, contact details, office
location, and letterhead configurable through the company profile.

## Features

- Company profile and first-run setup wizard
- Employee records, roles, salaries, documents, and checklists
- Leave types, balances, accruals, carry-forward, requests, approvals, and calendar
- Attendance marking with optional office geofencing
- Payroll breakup, payslips, LOP deductions, history, and approval
- Candidate management and employee CSV import/export
- Dashboard, reports, audit log, and in-app notifications
- CSRF protection, secure private document storage, and security headers

## Local Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `.env` with a production-quality `SECRET_KEY`. `DATABASE_URL` is
optional for local development; SQLite is the default.

```bash
flask db upgrade
flask run
```

Open `http://localhost:5000/login`. On a new database, Lite HRMS redirects to
`/setup`, where the company profile and first administrator are created.

Useful commands:

```bash
flask accrue-leave --year YYYY --month M
flask backup-db
python -m py_compile $(find app -name '*.py')
python -m app.payroll
```

## Configuration

The company profile controls the display name, legal name, address, phone,
email, website, office coordinates, and letterhead used throughout the UI and
generated PDFs. Important environment variables include:

- `SECRET_KEY`
- `DATABASE_URL`
- `UPLOAD_FOLDER`
- `DOCUMENT_UPLOAD_FOLDER`
- `BACKUP_FOLDER`
- `SESSION_COOKIE_SECURE=1` when served over HTTPS
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS`,
  `MAIL_USE_SSL`, `MAIL_DEFAULT_SENDER` to enable "Forgot password?" reset emails
- `APP_BASE_URL` (e.g. `https://hr.example.com`) for links in emails, and
  optionally `PASSWORD_RESET_MAX_AGE` in seconds (default 3600)

Reset links are signed with `SECRET_KEY`, expire after `PASSWORD_RESET_MAX_AGE`,
and stop working once the password changes. Without SMTP settings, users are
told to contact HR. Server administrators can always set a password with
`flask reset-password --email user@example.com`.

## Production

Run behind nginx or another TLS reverse proxy with Gunicorn:

```bash
gunicorn -w 3 -b 127.0.0.1:8000 run:app
```

Keep the database, environment file, private documents, uploads, backups, and
generated runtime files outside source control. Use PostgreSQL and scheduled
`pg_dump` backups for production deployments.

## Security Notes

- All state-changing forms require the application CSRF token.
- Logout is POST-only.
- Employee documents are stored outside static URLs and require authentication.
- Passwords are hashed and are never included in exports or logs.
- Configure a strong secret key and HTTPS before exposing the application.
