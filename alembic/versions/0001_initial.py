"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('consent_version', sa.String(10), nullable=False),
        sa.Column('consent_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('number', sa.String(10), unique=True, nullable=False),
        sa.Column('student_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='new'),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'ticket_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('actor_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'clarifications',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False),
        sa.Column('requested_fields', sa.Text(), nullable=False),
        sa.Column('teacher_comment', sa.Text(), nullable=True),
        sa.Column('student_reply', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('replied_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'ratings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), unique=True, nullable=False),
        sa.Column('rating', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'knowledge_base',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(255), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'bot_state',
        sa.Column('key', sa.String(50), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('bot_state')
    op.drop_table('knowledge_base')
    op.drop_table('ratings')
    op.drop_table('clarifications')
    op.drop_table('ticket_log')
    op.drop_table('tickets')
    op.drop_table('users')
