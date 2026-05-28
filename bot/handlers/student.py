import json
from datetime import datetime, timezone, timedelta

_MSK = timezone(timedelta(hours=3))


def _fmt_dt(dt) -> str:
    if dt is None:
        return "?"
    return dt.replace(tzinfo=timezone.utc).astimezone(_MSK).strftime('%d.%m %H:%M')

from maxapi import Router, F
from maxapi.types import MessageCreated, MessageCallback
from maxapi.context import BaseContext
from sqlalchemy import select

from core.db import async_session
from core.models.user import User
from core.models.ticket import Ticket
from core.models.clarification import Clarification
from core.models.rating import Rating
from core.services import ticket_service, ai_service, notification_service
from bot.states.forms import StudentStates
from bot.keyboards.student_kb import (
    main_menu_kb,
    create_method_kb,
    semesters_kb,
    disciplines_kb,
    discipline_teachers_kb,
    teacher_search_prompt_kb,
    teacher_search_results_kb,
    teachers_kb,
    categories_kb,
    entering_text_kb,
    duplicate_found_kb,
    confirm_ticket_kb,
    after_create_kb,
    my_tickets_kb,
    back_to_menu_kb,
    reply_clarification_kb,
)

from teachers_config import TEACHERS
from curriculum_config import CURRICULUM

router = Router()

CATEGORY_LABELS = {
    "lab_work": "Лабораторные работы",
    "project": "Проект",
    "access": "Доступы",
    "grading": "Оценивание",
    "retake": "Пересдача",
    "other": "Прочее",
}

STATUS_LABELS = {
    "new": "Новый",
    "in_progress": "В работе",
    "awaiting_clarification": "Ожидает уточнения",
    "scheduled": "Консультация назначена",
    "pending_confirmation": "Ожидает подтверждения",
    "closed": "Закрыт",
}


def _teacher_name(teacher_id: int) -> str:
    for t in TEACHERS:
        if t["id"] == teacher_id:
            return t["name"]
    return f"Преподаватель #{teacher_id}"


async def _edit(event: MessageCallback, text: str, attachments=None):
    kwargs = {"message_id": event.message.body.mid, "text": text}
    if attachments:
        kwargs["attachments"] = attachments
    await event.bot.edit_message(**kwargs)


@router.message_callback(F.callback.payload.contains("student:"))
async def student_callbacks(event: MessageCallback, context: BaseContext):
    data = event.callback.payload
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id
    bot = event.bot

    if data == "student:main_menu":
        async with async_session() as session:
            user = await session.get(User, user_id)
        name = user.name if user else "студент"
        await context.clear()
        await _edit(event, f"Привет, {name}! Чем могу помочь?", attachments=[main_menu_kb()])

    elif data == "student:create":
        await _edit(event, "Как хотите найти преподавателя?", attachments=[create_method_kb()])

    elif data == "student:method:semester":
        await _edit(event, "Выберите семестр:", attachments=[semesters_kb()])

    elif data.startswith("student:semester:"):
        sem = int(data.split(":")[-1])
        await context.update_data(semester=sem)
        await _edit(event, f"Семестр {sem} — выберите дисциплину:", attachments=[disciplines_kb(sem)])

    elif data.startswith("student:discipline:"):
        parts = data.split(":")
        sem = int(parts[2])
        idx = int(parts[3])
        discipline = CURRICULUM.get(sem, [])[idx]
        await context.update_data(discipline=discipline["name"])
        await context.set_state(StudentStates.choosing_teacher)
        await _edit(event,
            f"Дисциплина: {discipline['name']}\nВыберите преподавателя:",
            attachments=[discipline_teachers_kb(discipline["teacher_ids"], sem)],
        )

    elif data == "student:method:search":
        await context.set_state(StudentStates.searching_teacher)
        await context.update_data(search_results=[])
        await _edit(event, "Введите имя преподавателя:", attachments=[teacher_search_prompt_kb()])

    elif data.startswith("student:search_page:"):
        page = int(data.split(":")[-1])
        fsm_data = await context.get_data()
        results = fsm_data.get("search_results", [])
        await _edit(event, "Выберите преподавателя из результатов:", attachments=[teacher_search_results_kb(results, page)])

    elif data.startswith("student:teachers_page:"):
        page = int(data.split(":")[-1])
        await _edit(event, "Выберите преподавателя:", attachments=[teachers_kb(page)])

    elif data == "student:noop":
        pass

    elif data.startswith("student:teacher:"):
        teacher_id = int(data.split(":")[-1])
        from bot.handlers.teacher import get_cooldown_expiry
        expiry = await get_cooldown_expiry(user_id, teacher_id)
        if expiry:
            from datetime import timezone, timedelta
            msk = expiry.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=3)))
            await _edit(event,
                f"Вы не можете написать этому преподавателю до {msk.strftime('%d.%m в %H:%M')} "
                f"— предыдущее обращение было отклонено.",
                attachments=[back_to_menu_kb()],
            )
            return
        await context.update_data(teacher_id=teacher_id)
        await context.set_state(StudentStates.choosing_category)
        await _edit(event, "Выберите категорию обращения:", attachments=[categories_kb()])

    elif data.startswith("student:confirm_resolved:"):
        ticket_id = int(data.split(":")[-1])
        async with async_session() as session:
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            if ticket and ticket.student_id == user_id:
                await ticket_service.update_ticket_status(session, ticket_id, "closed")
                await ticket_service.add_log(session, ticket_id, "confirmed_closed", user_id)
                await session.commit()
        from bot.keyboards.student_kb import rating_kb
        await _edit(event, "Рады помочь! Пожалуйста, оцените ответ:", attachments=[rating_kb(ticket_id)])

    elif data.startswith("student:not_resolved:"):
        ticket_id = int(data.split(":")[-1])
        async with async_session() as session:
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            if not ticket or ticket.student_id != user_id:
                await _edit(event, "Тикет не найден.", attachments=[back_to_menu_kb()])
                return
            logs = await ticket_service.get_ticket_logs(session, ticket_id)
            already_reopened = any(l.action == "reopened" for l in logs)
            if already_reopened:
                await ticket_service.update_ticket_status(session, ticket_id, "closed")
                await ticket_service.add_log(session, ticket_id, "closed", user_id, "Автозакрытие: лимит оспариваний исчерпан")
                await session.commit()
                await _edit(event, "Вы уже оспаривали закрытие этого обращения. Тикет закрыт.", attachments=[back_to_menu_kb()])
                return
            await ticket_service.update_ticket_status(session, ticket_id, "in_progress")
            await ticket_service.add_log(session, ticket_id, "reopened", user_id, "Студент считает вопрос нерешённым")
            teacher_cfg_id = ticket.teacher_id
            teacher_chat_result = await session.execute(select(User).where(User.role == "teacher"))
            db_teachers = teacher_chat_result.scalars().all()
            teacher_chat = None
            from teachers_config import TEACHERS
            for t in TEACHERS:
                if t["id"] == teacher_cfg_id:
                    for db_t in db_teachers:
                        if db_t.name == t["name"]:
                            teacher_chat = db_t.chat_id
            ticket_number = ticket.number
            await session.commit()
        await _edit(event, "Обращение возвращено в работу. Преподаватель получил уведомление.", attachments=[back_to_menu_kb()])
        if teacher_chat:
            await notification_service.notify_teacher_reopened(event.bot, teacher_chat, ticket_number, "Студент считает вопрос нерешённым", ticket_id)

    elif data.startswith("student:category:"):
        category = data.split(":")[-1]
        await context.update_data(category=category)
        await context.set_state(StudentStates.entering_text)
        await _edit(event,
            "Опишите ваш вопрос кратко.\n\n"
            "⚠️ Не указывайте персональные данные, не нужные для решения вопроса.\n"
            "Можно приложить ссылку на репозиторий.",
            attachments=[entering_text_kb()],
        )

    elif data == "student:back_to_categories":
        await context.set_state(StudentStates.choosing_category)
        await _edit(event, "Выберите категорию обращения:", attachments=[categories_kb()])

    elif data == "student:ai_satisfied":
        await context.clear()
        async with async_session() as session:
            user = await session.get(User, user_id)
        name = user.name if user else "студент"
        await _edit(event, f"Рад помочь! Если появятся вопросы — пишите.", attachments=[main_menu_kb()])

    elif data == "student:ai_skip":
        await _show_confirm(event, context)

    elif data == "student:force_create":
        await _show_confirm(event, context)

    elif data.startswith("student:view_ticket:"):
        ticket_id = int(data.split(":")[-1])
        await _show_ticket_detail(event, user_id, ticket_id)

    elif data == "student:confirm_send":
        await _do_create_ticket(event, user_id, context)

    elif data == "student:cancel_create":
        await context.clear()
        async with async_session() as session:
            user = await session.get(User, user_id)
        name = user.name if user else "студент"
        await _edit(event, f"Привет, {name}! Чем могу помочь?", attachments=[main_menu_kb()])

    elif data == "student:my_tickets":
        await _show_my_tickets(event, user_id, page=0)

    elif data.startswith("student:my_tickets_page:"):
        page = int(data.split(":")[-1])
        await _show_my_tickets(event, user_id, page=page)

    elif data.startswith("student:reply_clarification:"):
        ticket_id = int(data.split(":")[-1])
        await context.set_state(StudentStates.answering_clarification)
        await context.update_data(clarification_ticket_id=ticket_id)
        await _edit(event, "Введите ваш ответ на уточнение:")

    elif data.startswith("student:rate:"):
        parts = data.split(":")
        rating_val = parts[2]
        ticket_id = int(parts[3])
        async with async_session() as session:
            existing = await session.execute(select(Rating).where(Rating.ticket_id == ticket_id))
            if not existing.scalar_one_or_none():
                session.add(Rating(ticket_id=ticket_id, rating=rating_val))
                await session.commit()
        await _edit(event, "Спасибо за оценку!", attachments=[back_to_menu_kb()])



@router.message_created(StudentStates.searching_teacher)
async def student_teacher_search(event: MessageCreated, context: BaseContext):
    chat_id = event.chat.chat_id
    query = (event.message.body.text or "").strip().lower()

    matches = [t for t in TEACHERS if query in t["name"].lower()]

    if not matches:
        await event.bot.send_message(
            chat_id=chat_id,
            text=f"Преподаватель «{query}» не найден. Попробуйте ещё раз:",
            attachments=[teacher_search_prompt_kb()],
        )
        return

    await context.update_data(search_results=matches)
    await context.set_state(StudentStates.choosing_teacher)
    await event.bot.send_message(
        chat_id=chat_id,
        text=f"Найдено {len(matches)} препод.: выберите:",
        attachments=[teacher_search_results_kb(matches, 0)],
    )


@router.message_created(StudentStates.entering_text, StudentStates.answering_clarification)
async def student_text_input(event: MessageCreated, context: BaseContext):
    current_state = await context.get_state()
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id
    bot = event.bot
    text = event.message.body.text if event.message and event.message.body else ""

    if current_state == str(StudentStates.entering_text):
        await context.update_data(ticket_text=text)
        fsm_data = await context.get_data()

        async with async_session() as session:
            open_tickets = await ticket_service.get_student_tickets(session, user_id)
        open_tickets = [t for t in open_tickets if t.status != "closed"]

        if open_tickets:
            tickets_data = [{"number": t.number, "status": t.status, "text": t.text} for t in open_tickets]
            dup = await ai_service.check_duplicates(tickets_data, text)
            if dup:
                matching = next((t for t in open_tickets if t.number == dup["number"]), None)
                if matching:
                    status_label = STATUS_LABELS.get(matching.status, matching.status)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"У вас уже есть похожее обращение {matching.number} со статусом {status_label}.\nПосмотреть или создать новое?",
                        attachments=[duplicate_found_kb(matching.id)],
                    )
                    return

        fsm_data2 = await context.get_data()
        category = fsm_data2.get("category")
        teacher_id = fsm_data2.get("teacher_id")
        teacher_name = _teacher_name(teacher_id)
        category_label = CATEGORY_LABELS.get(category, category)
        await context.set_state(StudentStates.confirming)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"Ваше обращение:\n\n"
                f"Преподаватель: {teacher_name}\n"
                f"Категория: {category_label}\n"
                f"Текст: {text}\n\n"
                f"Отправить?"
            ),
            attachments=[confirm_ticket_kb()],
        )

    elif current_state == str(StudentStates.answering_clarification):
        fsm_data = await context.get_data()
        ticket_id = fsm_data.get("clarification_ticket_id")

        async with async_session() as session:
            clar_result = await session.execute(
                select(Clarification)
                .where(Clarification.ticket_id == ticket_id)
                .order_by(Clarification.created_at.desc())
                .limit(1)
            )
            clar = clar_result.scalar_one_or_none()
            if clar:
                clar.student_reply = text
                clar.replied_at = datetime.utcnow()
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            if ticket:
                await ticket_service.update_ticket_status(session, ticket_id, "in_progress")
                await ticket_service.add_log(session, ticket_id, "clarification_provided", user_id)
                teacher_chat = await _get_teacher_chat(session, ticket.teacher_id)
                ticket_number = ticket.number
            else:
                teacher_chat = None
                ticket_number = "?"
            await session.commit()

        await context.clear()
        await bot.send_message(
            chat_id=chat_id,
            text="✅ Ответ отправлен преподавателю.",
            attachments=[back_to_menu_kb()],
        )
        if teacher_chat:
            await notification_service.notify_teacher_clarification_reply(bot, teacher_chat, ticket_number, text, ticket_id)


async def _show_confirm(event: MessageCallback, context: BaseContext):
    fsm_data = await context.get_data()
    teacher_id = fsm_data.get("teacher_id")
    category = fsm_data.get("category")
    text = fsm_data.get("ticket_text", "")
    teacher_name = _teacher_name(teacher_id)
    category_label = CATEGORY_LABELS.get(category, category)
    await context.set_state(StudentStates.confirming)
    await _edit(event,
        f"Ваше обращение:\n\n"
        f"Преподаватель: {teacher_name}\n"
        f"Категория: {category_label}\n"
        f"Текст: {text}\n\n"
        f"Отправить?",
        attachments=[confirm_ticket_kb()],
    )


async def _do_create_ticket(event: MessageCallback, user_id: int, context: BaseContext):
    fsm_data = await context.get_data()
    teacher_id = fsm_data.get("teacher_id")
    category = fsm_data.get("category")
    text = fsm_data.get("ticket_text", "")
    bot = event.bot

    if not teacher_id or not category or not text.strip():
        await context.clear()
        await _edit(event,
            "Сессия устарела, начните создание обращения заново.",
            attachments=[main_menu_kb()],
        )
        return

    existing_ticket = None
    teacher_chat = None
    student_name = "Студент"
    summary = ""

    async with async_session() as session:
        existing = await session.execute(
            select(Ticket).where(
                Ticket.student_id == user_id,
                Ticket.teacher_id == teacher_id,
                Ticket.status == "new",
                Ticket.text == text,
            )
        )
        existing_ticket = existing.scalar_one_or_none()

        if existing_ticket:
            ticket = existing_ticket
        else:
            ticket = await ticket_service.create_ticket(session, user_id, teacher_id, category, text)
            user = await session.get(User, user_id)
            student_name = user.name if user else "Студент"
            await ticket_service.add_log(session, ticket.id, "created", user_id, student_name)
            await session.commit()

            summary = await ai_service.generate_summary(text)
            await ticket_service.set_ai_summary(session, ticket.id, summary)
            await session.commit()

            teacher_chat = await _get_teacher_chat(session, teacher_id)

        ticket_id = ticket.id
        ticket_number = ticket.number

    await context.clear()
    await _edit(event,
        f"✅ Обращение {ticket_number} создано!\n\nПреподаватель: {_teacher_name(teacher_id)}\nСтатус: Новый",
        attachments=[after_create_kb(ticket_id)],
    )

    if not existing_ticket and teacher_chat:
        await notification_service.notify_teacher_new_ticket(
            bot, teacher_chat, ticket_number, student_name, summary, ticket_id
        )


async def _show_my_tickets(event: MessageCallback, user_id: int, page: int = 0):
    async with async_session() as session:
        tickets = await ticket_service.get_student_tickets(session, user_id)

    if not tickets:
        await _edit(event, "У вас пока нет обращений.", attachments=[back_to_menu_kb()])
        return

    open_tickets = [t for t in tickets if t.status != "closed"]
    closed_tickets = [t for t in tickets if t.status == "closed"]

    items = []
    for ticket in open_tickets + closed_tickets:
        status_label = STATUS_LABELS.get(ticket.status, ticket.status)
        category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
        items.append((ticket.id, f"{ticket.number} · {status_label} · {category_label}"))

    total = len(items)
    text = f"Ваши обращения ({total}):"
    await _edit(event, text, attachments=[my_tickets_kb(items, page)])


async def _show_ticket_detail(event: MessageCallback, user_id: int, ticket_id: int):
    async with async_session() as session:
        ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
        if not ticket or ticket.student_id != user_id:
            await _edit(event, "Тикет не найден.", attachments=[back_to_menu_kb()])
            return
        logs = await ticket_service.get_ticket_logs(session, ticket_id)
        clar_result = await session.execute(
            select(Clarification)
            .where(Clarification.ticket_id == ticket_id, Clarification.student_reply.is_(None))
            .order_by(Clarification.created_at.desc())
            .limit(1)
        )
        pending_clar = clar_result.scalar_one_or_none()

    status_label = STATUS_LABELS.get(ticket.status, ticket.status)
    category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
    teacher_name = _teacher_name(ticket.teacher_id)

    action_labels = {
        "created": "Создано", "accepted": "Принято в работу",
        "clarification_requested": "Запрошено уточнение",
        "clarification_provided": "Уточнение предоставлено",
        "answered": "Отвечено", "closed": "Закрыто",
    }

    history_lines = []
    teacher_answer = None
    for log in logs:
        label = action_labels.get(log.action, log.action)
        line = f"• {label} — {_fmt_dt(log.created_at)}"
        if log.comment and log.action in ("closed", "answered"):
            teacher_answer = log.comment
        elif log.comment and log.action == "clarification_requested":
            line += f"\n  Комментарий: {log.comment}"
        history_lines.append(line)
    history_str = "\n".join(history_lines) or "Нет записей"

    text = (
        f"{ticket.number} · [{status_label}]\n\n"
        f"Преподаватель: {teacher_name}\n"
        f"Категория: {category_label}\n"
        f"Текст: {ticket.text}\n\n"
        f"История:\n{history_str}"
    )

    if teacher_answer:
        text += f"\n\n💬 Ответ преподавателя:\n{teacher_answer}"

    if pending_clar:
        fields = json.loads(pending_clar.requested_fields)
        fields_str = "\n".join(f"• {f}" for f in fields)
        comment_part = f"\nКомментарий: {pending_clar.teacher_comment}" if pending_clar.teacher_comment else ""
        text += f"\n\n❓ Преподаватель запрашивает уточнение:\n{fields_str}{comment_part}"
        await _edit(event, text, attachments=[reply_clarification_kb(ticket_id)])
    else:
        await _edit(event, text, attachments=[back_to_menu_kb()])


async def _get_teacher_chat(session, teacher_id: int) -> int | None:
    result = await session.execute(select(User).where(User.role == "teacher"))
    db_teachers = result.scalars().all()
    for t in TEACHERS:
        if t["id"] == teacher_id:
            for db_t in db_teachers:
                if db_t.name == t["name"]:
                    return db_t.chat_id
    return None
