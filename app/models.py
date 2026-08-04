from datetime import date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    legal_name = db.Column(db.String(160), nullable=True)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(160), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    letterhead_filename = db.Column(db.String(255), nullable=True)
    office_latitude = db.Column(db.Float, nullable=True)
    office_longitude = db.Column(db.Float, nullable=True)

    employees = db.relationship("Employee", backref="company", lazy=True)


class Employee(UserMixin, db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="employee")  # employee | admin
    designation_id = db.Column(db.Integer, db.ForeignKey("designations.id"), nullable=True)
    photo_filename = db.Column(db.String(255), nullable=True)
    date_of_joining = db.Column(db.Date, default=date.today)
    monthly_gross = db.Column(db.Numeric(10, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    relieving_date = db.Column(db.Date, nullable=True)
    termination_reason = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("company_id", "email", name="uq_company_email"),
    )

    leave_requests = db.relationship(
        "LeaveRequest", backref="employee", lazy=True, foreign_keys="LeaveRequest.employee_id"
    )
    leave_balances = db.relationship("LeaveBalance", backref="employee", lazy=True)
    attendance_records = db.relationship("Attendance", backref="employee", lazy=True)
    payroll_runs = db.relationship(
        "PayrollRun", backref="employee", lazy=True, foreign_keys="PayrollRun.employee_id"
    )
    salary_lines = db.relationship(
        "EmployeeSalary", backref="employee", lazy=True, cascade="all, delete-orphan"
    )
    documents = db.relationship(
        "EmployeeDocument", backref="employee", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def is_admin(self):
        return self.role == "admin"

    def has_role(self, *roles):
        return self.role in roles

    def can_manage_people(self):
        return self.role in {"admin", "hr_manager"}

    def can_approve(self):
        return self.role in {"admin", "hr_manager", "manager"}


class Designation(db.Model):
    __tablename__ = "designations"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("company_id", "title", name="uq_company_designation_title"),
    )

    company = db.relationship("Company")
    employees = db.relationship("Employee", backref="designation", lazy=True)


class SalaryComponent(db.Model):
    __tablename__ = "salary_components"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(10), nullable=False, default="earning")  # earning | deduction
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("company_id", "name", name="uq_company_component_name"),
    )

    company = db.relationship("Company")
    salary_lines = db.relationship("EmployeeSalary", backref="component", lazy=True)


class EmployeeSalary(db.Model):
    __tablename__ = "employee_salaries"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey("salary_components.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), default=0)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "component_id", name="uq_emp_component"),
    )


class Candidate(db.Model):
    __tablename__ = "candidates"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    designation_id = db.Column(db.Integer, db.ForeignKey("designations.id"), nullable=True)
    proposed_salary = db.Column(db.Numeric(10, 2), default=0)
    offer_date = db.Column(db.Date, default=date.today)
    joining_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="offered")  # offered | joined | rejected
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)

    company = db.relationship("Company")
    designation = db.relationship("Designation")
    employee = db.relationship("Employee")


class Holiday(db.Model):
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("company_id", "date", name="uq_company_holiday_date"),
    )

    company = db.relationship("Company")


class LeaveType(db.Model):
    __tablename__ = "leave_types"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)
    annual_quota = db.Column(db.Float, nullable=False, default=0)
    # yearly_upfront | monthly | none
    accrual_type = db.Column(db.String(20), nullable=False, default="yearly_upfront")
    carry_forward = db.Column(db.Boolean, default=False)
    max_carry_forward = db.Column(db.Float, nullable=True)
    requires_approval = db.Column(db.Boolean, default=True)
    min_days_notice = db.Column(db.Integer, default=0)
    allow_negative_balance = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("company_id", "name", name="uq_company_leavetype_name"),
    )

    company = db.relationship("Company")
    leave_requests = db.relationship("LeaveRequest", backref="leave_type", lazy=True)
    leave_balances = db.relationship("LeaveBalance", backref="leave_type", lazy=True)


class LeaveBalance(db.Model):
    __tablename__ = "leave_balances"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    opening_balance = db.Column(db.Float, default=0)
    accrued = db.Column(db.Float, default=0)
    used = db.Column(db.Float, default=0)
    carried_forward = db.Column(db.Float, default=0)
    last_accrued_month = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_emp_leavetype_year"),
    )

    @property
    def available(self):
        return self.opening_balance + self.accrued + self.carried_forward - self.used


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type_id = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_count = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default="pending")  # pending | approved | rejected
    applied_on = db.Column(db.DateTime, default=db.func.now())
    approved_by = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)

    approver = db.relationship("Employee", foreign_keys=[approved_by])


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="present")  # present | absent | half_day | on_leave
    check_in = db.Column(db.Time, nullable=True)
    check_out = db.Column(db.Time, nullable=True)
    check_in_latitude = db.Column(db.Float, nullable=True)
    check_in_longitude = db.Column(db.Float, nullable=True)
    check_in_distance_m = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "date", name="uq_emp_date"),
    )


class PayrollRun(db.Model):
    __tablename__ = "payroll_runs"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    gross = db.Column(db.Numeric(10, 2), nullable=False)
    deductions = db.Column(db.Numeric(10, 2), default=0)
    net_pay = db.Column(db.Numeric(10, 2), nullable=False)
    payslip_path = db.Column(db.String(255), nullable=True)
    generated_on = db.Column(db.DateTime, default=db.func.now())
    status = db.Column(db.String(20), default="draft", nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "month", "year", name="uq_emp_month_year"),
    )

    approver = db.relationship("Employee", foreign_keys=[approved_by])


class EmployeeDocument(db.Model):
    __tablename__ = "employee_documents"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), nullable=False, default="other")
    filename = db.Column(db.String(255), nullable=False)
    uploaded_on = db.Column(db.DateTime, default=db.func.now(), nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    action = db.Column(db.String(40), nullable=False)
    entity = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    company = db.relationship("Company")
    actor = db.relationship("Employee", foreign_keys=[actor_id])


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    employee = db.relationship("Employee", backref=db.backref("notifications", lazy=True))


class EmployeeChecklistItem(db.Model):
    __tablename__ = "employee_checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(30), nullable=False, default="onboarding")
    completed = db.Column(db.Boolean, default=False, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    employee = db.relationship("Employee", backref=db.backref("checklist_items", lazy=True, cascade="all, delete-orphan"))
