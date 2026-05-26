"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("role", sa.Enum("resident", "shipper", "manager", "admin", name="userrole"), nullable=False, server_default="resident"),
        sa.Column("building_id", sa.String(32), nullable=True),
        sa.Column("unit_number", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("notif_type", sa.String(32), nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("delivery_id", sa.Integer, nullable=True),
        sa.Column("shelf_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("read_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tracking_code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("shipper_id", sa.String(64), nullable=False),
        sa.Column("recipient_id", sa.String(64), nullable=False),
        sa.Column("building_id", sa.String(32), nullable=False),
        sa.Column("unit_number", sa.String(16), nullable=False),
        sa.Column("status", sa.Enum("pending", "in_transit", "arrived", "verified", "collected", "disputed", name="deliverystatus"), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("camera_snapshot_url", sa.String(512), nullable=True),
        sa.Column("ai_confidence_score", sa.Float, nullable=True),
        sa.Column("ai_detection_detail", sa.Text, nullable=True),
        sa.Column("verified_at", sa.DateTime, nullable=True),
        sa.Column("verification_note", sa.Text, nullable=True),
    )

    op.create_table(
        "delivery_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("delivery_id", sa.Integer, sa.ForeignKey("deliveries.id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("snapshot_url", sa.String(512), nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "shipper_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shipper_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("company", sa.String(128), nullable=True),
        sa.Column("photo_path", sa.String(512), nullable=True),
        sa.Column("face_embedding", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("registered_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "smart_shelves",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("building_id", sa.String(32), nullable=False, index=True),
        sa.Column("floor", sa.String(8), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("location_note", sa.Text, nullable=True),
        sa.Column("total_slots", sa.Integer, nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "shelf_slots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shelf_id", sa.Integer, sa.ForeignKey("smart_shelves.id"), nullable=False, index=True),
        sa.Column("slot_number", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum("empty", "occupied", "reserved", "maintenance", name="slotstatus"), nullable=False, server_default="empty"),
        sa.Column("current_delivery_id", sa.Integer, nullable=True),
        sa.Column("access_token", sa.String(64), nullable=True),
        sa.Column("occupied_since", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    op.create_table(
        "shelf_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shelf_id", sa.Integer, sa.ForeignKey("smart_shelves.id"), nullable=False, index=True),
        sa.Column("slot_number", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("delivery_id", sa.Integer, nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shelf_events")
    op.drop_table("shelf_slots")
    op.drop_table("smart_shelves")
    op.drop_table("shipper_profiles")
    op.drop_table("delivery_events")
    op.drop_table("deliveries")
    op.drop_table("notifications")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS deliverystatus")
    op.execute("DROP TYPE IF EXISTS slotstatus")
