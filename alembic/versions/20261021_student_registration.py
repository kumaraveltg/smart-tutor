"""student registration, plans, subscription, payment

Revision ID: a1b2c3d4e5f6
Revises: <PUT_YOUR_LATEST_REVISION_ID_HERE>
Create Date: 2026-10-21

Put this file in alembic/versions/. Then set:
  revision      -> keep it, or use the id that `alembic revision` generated for you
  down_revision -> the id of your latest existing migration (run `alembic heads`)
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "None"  # ADJUST
branch_labels = None
depends_on = None

SCHEMA = "smarttutor"


def upgrade() -> None:
    op.create_table(
        "st_student_profile",
        sa.Column("profile_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mobile", sa.String(15), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("medium_id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True),
        sa.Column("school", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_st_student_profile_user_id"),
        sa.UniqueConstraint("mobile", name="uq_st_student_profile_mobile"),
        # ADJUST table names, then uncomment to add real foreign keys:
        # sa.ForeignKeyConstraint(["user_id"], ["smarttutor.users.id"]),
        # sa.ForeignKeyConstraint(["class_id"], ["smarttutor.classes.id"]),
        # sa.ForeignKeyConstraint(["medium_id"], ["smarttutor.mediums.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        "st_plan",
        sa.Column("plan_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema=SCHEMA,
    )

    op.create_table(
        "st_subscription",
        sa.Column("sub_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("trial_start", sa.Date(), nullable=False),
        sa.Column("trial_end", sa.Date(), nullable=False),
        sa.Column("paid_until", sa.Date(), nullable=True),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("free_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("user_id", name="uq_st_subscription_user_id"),
        sa.ForeignKeyConstraint(["plan_id"], [f"{SCHEMA}.st_plan.plan_id"]),
        schema=SCHEMA,
    )

    op.create_table(
        "st_payment",
        sa.Column("payment_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("razorpay_order_id", sa.String(60), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(60), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("razorpay_order_id", name="uq_st_payment_order_id"),
        sa.ForeignKeyConstraint(["plan_id"], [f"{SCHEMA}.st_plan.plan_id"]),
        schema=SCHEMA,
    )
    op.create_index("ix_st_payment_user_id", "st_payment", ["user_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_st_payment_user_id", table_name="st_payment", schema=SCHEMA)
    op.drop_table("st_payment", schema=SCHEMA)
    op.drop_table("st_subscription", schema=SCHEMA)
    op.drop_table("st_plan", schema=SCHEMA)
    op.drop_table("st_student_profile", schema=SCHEMA)
