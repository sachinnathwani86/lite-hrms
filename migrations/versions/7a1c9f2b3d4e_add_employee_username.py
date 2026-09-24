"""add employee username and make email optional

Revision ID: 7a1c9f2b3d4e
Revises: 34f3a788e9bf
Create Date: 2026-09-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a1c9f2b3d4e'
down_revision = '34f3a788e9bf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(length=60), nullable=True))
        batch_op.alter_column('email', existing_type=sa.String(length=120), nullable=True)

    # Backfill usernames for existing employees from their email local part,
    # falling back to a generated id-based handle, keeping them unique.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, email FROM employees")).fetchall()
    used = set()
    for row in rows:
        base = (row.email or "").split("@")[0].strip().lower()
        base = "".join(ch for ch in base if ch.isalnum() or ch in "._-") or f"user{row.id}"
        username = base
        suffix = 1
        while username in used:
            suffix += 1
            username = f"{base}{suffix}"
        used.add(username)
        conn.execute(
            sa.text("UPDATE employees SET username = :username WHERE id = :id"),
            {"username": username, "id": row.id},
        )

    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.alter_column('username', existing_type=sa.String(length=60), nullable=False)
        batch_op.create_unique_constraint('uq_company_username', ['company_id', 'username'])


def downgrade():
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_constraint('uq_company_username', type_='unique')
        batch_op.alter_column('email', existing_type=sa.String(length=120), nullable=False)
        batch_op.drop_column('username')
