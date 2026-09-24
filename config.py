import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-this-in-prod")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'hrms.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(basedir, "app", "static", "uploads")
    )
    DOCUMENT_UPLOAD_FOLDER = os.environ.get(
        "DOCUMENT_UPLOAD_FOLDER", os.path.join(basedir, "instance", "documents")
    )
    BACKUP_FOLDER = os.environ.get(
        "BACKUP_FOLDER", os.path.join(basedir, "instance", "backups")
    )
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB upload cap (employee photos)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    # Outgoing email (used for password reset links). Leave MAIL_SERVER unset to disable.
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "0") == "1"
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")
    # Public base URL used in emailed links, e.g. https://hr.example.com
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")
    PASSWORD_RESET_MAX_AGE = int(os.environ.get("PASSWORD_RESET_MAX_AGE", "3600"))
