from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.models.ticket import Ticket
from core.models.ticket_log import TicketLog

router = APIRouter()


@router.get("")
async def list_tickets(
    status: Optional[str] = None,
    teacher_id: Optional[int] = None,
    student_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    q = select(Ticket)
    if status:
        q = q.where(Ticket.status == status)
    if teacher_id:
        q = q.where(Ticket.teacher_id == teacher_id)
    if student_id:
        q = q.where(Ticket.student_id == student_id)
    q = q.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    tickets = result.scalars().all()
    return [
        {
            "id": t.id,
            "number": t.number,
            "student_id": t.student_id,
            "teacher_id": t.teacher_id,
            "category": t.category,
            "text": t.text,
            "status": t.status,
            "ai_summary": t.ai_summary,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tickets
    ]


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    session: AsyncSession = Depends(get_session),
):
    ticket = await session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    logs_result = await session.execute(
        select(TicketLog)
        .where(TicketLog.ticket_id == ticket_id)
        .order_by(TicketLog.created_at.asc())
    )
    logs = logs_result.scalars().all()

    return {
        "id": ticket.id,
        "number": ticket.number,
        "student_id": ticket.student_id,
        "teacher_id": ticket.teacher_id,
        "category": ticket.category,
        "text": ticket.text,
        "status": ticket.status,
        "ai_summary": ticket.ai_summary,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "history": [
            {
                "id": log.id,
                "action": log.action,
                "actor_id": log.actor_id,
                "comment": log.comment,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }
