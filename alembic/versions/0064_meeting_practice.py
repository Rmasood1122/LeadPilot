"""Meeting prep script + roleplay practice (Part 2).

ALTERS
  meeting_prep_briefs  script_json, script_edited_at, script_edited_by_user_id,
                       practice_required

CREATES
  roleplay_sessions    one practice run: who practised, against which brief,
                       with what persona, and the feedback afterwards
  roleplay_turns       every line of that conversation, in order

WHY THE SCRIPT IS ITS OWN COLUMN and not another key in `sections_json`. The
brief is MODEL OUTPUT, regenerated whenever "Regenerate" is pressed.  The
script is the user's -- they edit it, and an edit that a regeneration silently
overwrites is an edit nobody will make twice. Keeping it separate means
`generate_brief` can rewrite `sections_json` freely while `script_json` is only
ever written by a person (or seeded once, when it is still empty).

WHY THE TURNS ARE ROWS AND NOT A JSON BLOB ON THE SESSION. A roleplay is
appended to one line at a time by a live UI; a JSON array means read-modify-
write on every turn, which loses a line whenever two requests overlap. Rows
with a turn number cannot interleave wrongly, and UNIQUE (session, turn_no)
makes a duplicated submit a conflict rather than a duplicated line.

Revision ID: 0064_meeting_practice
Revises: 0063_client_workspaces
"""

import sqlalchemy as sa
from alembic import op

revision = "0064_meeting_practice"
down_revision = "0063_client_workspaces"
branch_labels = None
depends_on = None


def _brief_columns() -> list[sa.Column]:
    return [
        sa.Column("script_json", sa.JSON(), nullable=True),
        sa.Column("script_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("script_edited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("practice_required", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    ]


def upgrade() -> None:
    with op.batch_alter_table("meeting_prep_briefs") as batch:
        for column in _brief_columns():
            batch.add_column(column)
    with op.batch_alter_table("meeting_prep_briefs") as batch:
        batch.create_foreign_key(
            "fk_meeting_prep_briefs_script_edited_by_user_id_users",
            "users", ["script_edited_by_user_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "roleplay_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("difficulty", sa.String(length=20), nullable=False,
                  server_default=sa.text("'realistic'")),
        sa.Column("persona_json", sa.JSON(), nullable=True),
        sa.Column("objectives_json", sa.JSON(), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("feedback_json", sa.JSON(), nullable=True),
        sa.Column("score_overall", sa.Integer(), nullable=True),
        sa.Column("score_discovery", sa.Integer(), nullable=True),
        sa.Column("score_objections", sa.Integer(), nullable=True),
        sa.Column("score_tone", sa.Integer(), nullable=True),
        sa.Column("score_close", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roleplay_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_roleplay_sessions_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_roleplay_sessions_lead_id_leads"),
        sa.ForeignKeyConstraint(["brief_id"], ["meeting_prep_briefs.id"],
                                ondelete="SET NULL",
                                name="fk_roleplay_sessions_brief_id_meeting_prep_briefs"),
    )
    op.create_index("ix_roleplay_sessions_user_id", "roleplay_sessions", ["user_id"])
    op.create_index("ix_roleplay_sessions_lead_id", "roleplay_sessions", ["lead_id"])
    op.create_index("ix_roleplay_sessions_status", "roleplay_sessions", ["status"])

    op.create_table(
        "roleplay_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roleplay_turns"),
        sa.UniqueConstraint("session_id", "turn_no", name="roleplay_turn_order"),
        sa.ForeignKeyConstraint(["session_id"], ["roleplay_sessions.id"],
                                ondelete="CASCADE",
                                name="fk_roleplay_turns_session_id_roleplay_sessions"),
    )
    op.create_index("ix_roleplay_turns_session_id", "roleplay_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_roleplay_turns_session_id", table_name="roleplay_turns")
    op.drop_table("roleplay_turns")
    op.drop_index("ix_roleplay_sessions_status", table_name="roleplay_sessions")
    op.drop_index("ix_roleplay_sessions_lead_id", table_name="roleplay_sessions")
    op.drop_index("ix_roleplay_sessions_user_id", table_name="roleplay_sessions")
    op.drop_table("roleplay_sessions")
    with op.batch_alter_table("meeting_prep_briefs") as batch:
        batch.drop_constraint("fk_meeting_prep_briefs_script_edited_by_user_id_users",
                              type_="foreignkey")
        for column in reversed(_brief_columns()):
            batch.drop_column(column.name)
