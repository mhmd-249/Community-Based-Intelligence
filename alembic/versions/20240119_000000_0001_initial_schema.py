"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-19 00:00:00.000000

"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # Create ENUM types
    report_status = postgresql.ENUM(
        "open", "investigating", "resolved", "false_alarm",
        name="report_status", create_type=False
    )
    report_status.create(op.get_bind(), checkfirst=True)

    urgency_level = postgresql.ENUM(
        "critical", "high", "medium", "low",
        name="urgency_level", create_type=False
    )
    urgency_level.create(op.get_bind(), checkfirst=True)

    alert_type = postgresql.ENUM(
        "suspected_outbreak", "cluster", "single_case", "rumor",
        name="alert_type", create_type=False
    )
    alert_type.create(op.get_bind(), checkfirst=True)

    disease_type = postgresql.ENUM(
        "cholera", "dengue", "malaria", "measles", "meningitis", "unknown",
        name="disease_type", create_type=False
    )
    disease_type.create(op.get_bind(), checkfirst=True)

    reporter_rel = postgresql.ENUM(
        "self", "family", "neighbor", "health_worker", "community_leader", "other",
        name="reporter_rel", create_type=False
    )
    reporter_rel.create(op.get_bind(), checkfirst=True)

    link_type = postgresql.ENUM(
        "geographic", "temporal", "symptom", "manual",
        name="link_type", create_type=False
    )
    link_type.create(op.get_bind(), checkfirst=True)

    # Create reporters table
    op.create_table(
        "reporters",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("phone_hash", sa.String(64), nullable=False),
        sa.Column("phone_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("preferred_language", sa.String(5), server_default="ar", nullable=True),
        sa.Column("total_reports", sa.Integer(), server_default="0", nullable=True),
        sa.Column("first_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_hash"),
    )
    op.create_index("idx_reporters_phone_hash", "reporters", ["phone_hash"])
    op.create_index("idx_reporters_last_report", "reporters", [sa.text("last_report_at DESC")])

    # Create officers table
    op.create_table(
        "officers",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), server_default="officer", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_officers_email", "officers", ["email"])
    op.create_index("idx_officers_region", "officers", ["region"])

    # Create reports table
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("officer_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.String(100), nullable=False),
        sa.Column("status", postgresql.ENUM("open", "investigating", "resolved", "false_alarm", name="report_status", create_type=False), server_default="open", nullable=True),
        sa.Column("symptoms", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=True),
        sa.Column("suspected_disease", postgresql.ENUM("cholera", "dengue", "malaria", "measles", "meningitis", "unknown", name="disease_type", create_type=False), server_default="unknown", nullable=True),
        sa.Column("reporter_relation", postgresql.ENUM("self", "family", "neighbor", "health_worker", "community_leader", "other", name="reporter_rel", create_type=False), nullable=True),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("location_normalized", sa.String(200), nullable=True),
        sa.Column("location_point", geoalchemy2.types.Geography(geometry_type="POINT", srid=4326, from_text="ST_GeogFromText", name="geography"), nullable=True),
        sa.Column("onset_text", sa.Text(), nullable=True),
        sa.Column("onset_date", sa.Date(), nullable=True),
        sa.Column("cases_count", sa.Integer(), server_default="1", nullable=True),
        sa.Column("deaths_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("affected_groups", sa.Text(), nullable=True),
        sa.Column("urgency", postgresql.ENUM("critical", "high", "medium", "low", name="urgency_level", create_type=False), server_default="medium", nullable=True),
        sa.Column("alert_type", postgresql.ENUM("suspected_outbreak", "cluster", "single_case", "rumor", name="alert_type", create_type=False), server_default="single_case", nullable=True),
        sa.Column("data_completeness", sa.Float(), server_default="0.0", nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("raw_conversation", postgresql.JSONB(), server_default="[]", nullable=True),
        sa.Column("extracted_entities", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("source", sa.String(20), server_default="telegram", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("data_completeness >= 0 AND data_completeness <= 1", name="valid_completeness"),
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="valid_confidence"),
        sa.CheckConstraint("cases_count >= 0 AND deaths_count >= 0", name="valid_counts"),
        sa.ForeignKeyConstraint(["reporter_id"], ["reporters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["officer_id"], ["officers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_reports_reporter", "reports", ["reporter_id"])
    op.create_index("idx_reports_officer", "reports", ["officer_id"])
    op.create_index("idx_reports_conversation", "reports", ["conversation_id"])
    op.create_index("idx_reports_status", "reports", ["status"])
    op.create_index("idx_reports_urgency", "reports", ["urgency"])
    op.create_index("idx_reports_disease", "reports", ["suspected_disease"])
    op.create_index("idx_reports_created", "reports", [sa.text("created_at DESC")])
    op.create_index("idx_reports_location", "reports", ["location_point"], postgresql_using="gist")

    # Create report_links table
    op.create_table(
        "report_links",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("report_id_1", sa.UUID(), nullable=False),
        sa.Column("report_id_2", sa.UUID(), nullable=False),
        sa.Column("link_type", postgresql.ENUM("geographic", "temporal", "symptom", "manual", name="link_type", create_type=False), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("created_by", sa.String(50), server_default="surveillance_agent", nullable=True),
        sa.CheckConstraint("report_id_1 != report_id_2", name="different_reports"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_link_confidence"),
        sa.ForeignKeyConstraint(["report_id_1"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id_2"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id_1", "report_id_2", "link_type", name="unique_link"),
    )
    op.create_index("idx_report_links_report1", "report_links", ["report_id_1"])
    op.create_index("idx_report_links_report2", "report_links", ["report_id_2"])
    op.create_index("idx_report_links_type", "report_links", ["link_type"])

    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=True),
        sa.Column("officer_id", sa.UUID(), nullable=True),
        sa.Column("urgency", postgresql.ENUM("critical", "high", "medium", "low", name="urgency_level", create_type=False), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("channels", postgresql.ARRAY(sa.Text()), server_default="{dashboard}", nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["officer_id"], ["officers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notifications_officer", "notifications", ["officer_id"])
    op.create_index("idx_notifications_report", "notifications", ["report_id"])

    # Create audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("changes", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_actor", "audit_logs", ["actor_type", "actor_id"])
    op.create_index("idx_audit_created", "audit_logs", [sa.text("created_at DESC")])

    # Create conversation_states table
    op.create_table(
        "conversation_states",
        sa.Column("conversation_id", sa.String(100), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("state", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("mode", sa.String(20), server_default="listening", nullable=True),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["reporter_id"], ["reporters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index("idx_conversation_reporter", "conversation_states", ["reporter_id"])

    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Apply triggers
    for table in ["reporters", "officers", "reports", "conversation_states"]:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table in ["reporters", "officers", "reports", "conversation_states"]:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables
    op.drop_table("conversation_states")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("report_links")
    op.drop_table("reports")
    op.drop_table("officers")
    op.drop_table("reporters")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS link_type")
    op.execute("DROP TYPE IF EXISTS reporter_rel")
    op.execute("DROP TYPE IF EXISTS disease_type")
    op.execute("DROP TYPE IF EXISTS alert_type")
    op.execute("DROP TYPE IF EXISTS urgency_level")
    op.execute("DROP TYPE IF EXISTS report_status")
