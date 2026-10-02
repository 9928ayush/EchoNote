"""Initial durable audio notes and processing checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audio_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("upload_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("duration", sa.Float()),
        sa.Column(
            "status",
            sa.Enum(
                "UPLOADING",
                "QUEUED",
                "TRANSCRIBING",
                "SUMMARIZING",
                "COMPLETED",
                "FAILED",
                name="status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("transcript", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("chunks", sa.JSON(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(300)),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("run_token", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notes_created", "audio_notes", ["created_at", "id"])
    op.create_index("ix_notes_dispatch", "audio_notes", ["status", "updated_at"])


def downgrade():
    op.drop_table("audio_notes")
