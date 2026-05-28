from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.ticket import Ticket
from core.models.ticket_log import TicketLog


async def get_next_ticket_number(session: AsyncSession) -> str:
    result = await session.execute(select(Ticket.id).order_by(Ticket.id.desc()).limit(1))
    last_id = result.scalar()
    next_num = (last_id or 0) + 1
    return f"#{next_num}"


async def create_ticket(
    session: AsyncSession,
    student_id: int,
    teacher_id: int,
    category: str,
    text: str,
) -> Ticket:
    number = await get_next_ticket_number(session)
    ticket = Ticket(
        number=number,
        student_id=student_id,
        teacher_id=teacher_id,
        category=category,
        text=text,
        status="new",
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def add_log(
    session: AsyncSession,
    ticket_id: int,
    action: str,
    actor_id: int,
    comment: str | None = None,
) -> None:
    log = TicketLog(
        ticket_id=ticket_id,
        action=action,
        actor_id=actor_id,
        comment=comment,
    )
    session.add(log)


async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()


async def get_ticket_by_number(session: AsyncSession, number: str) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.number == number))
    return result.scalar_one_or_none()


async def get_student_tickets(session: AsyncSession, student_id: int) -> list[Ticket]:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.student_id == student_id)
        .order_by(Ticket.created_at.desc())
    )
    return list(result.scalars().all())


async def get_teacher_tickets(
    session: AsyncSession, teacher_id: int, status: str | None = None
) -> list[Ticket]:
    q = select(Ticket).where(Ticket.teacher_id == teacher_id)
    if status:
        q = q.where(Ticket.status == status)
    q = q.order_by(Ticket.created_at.asc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_ticket_status(
    session: AsyncSession, ticket_id: int, status: str
) -> None:
    await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(status=status, updated_at=datetime.utcnow())
    )


async def set_ai_summary(session: AsyncSession, ticket_id: int, summary: str) -> None:
    await session.execute(
        update(Ticket).where(Ticket.id == ticket_id).values(ai_summary=summary)
    )


async def get_ticket_logs(session: AsyncSession, ticket_id: int) -> list[TicketLog]:
    result = await session.execute(
        select(TicketLog)
        .where(TicketLog.ticket_id == ticket_id)
        .order_by(TicketLog.created_at.asc())
    )
    return list(result.scalars().all())
