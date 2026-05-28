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
from core.models.clarification import Clarification
from core.models.knowledge_base import KnowledgeBase
from core.models.rating import Rating
from core.services import ticket_service, notification_service, pdf_service, ai_service
from bot.states.forms import TeacherStates
from bot.keyboards.teacher_kb import (
    main_menu_kb,
    queue_list_kb,
    list_item_kb,
    working_ticket_kb,
    new_ticket_detail_kb,
    ai_suggestion_kb,
    kb_menu_kb,
    kb_delete_confirm_kb,
    clarification_fields_kb,
    close_outcome_kb,
    back_to_menu_kb,
    after_schedule_kb,
    CLARIFICATION_FIELDS,
)
from teachers_config import TEACHERS

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
    "closed": "Закрыт",
}


def _get_teacher_config_id(user_name: str) -> int | None:
    for t in TEACHERS:
        if t["name"] == user_name:
            return t["id"]
    return None


async def _edit(event: MessageCallback, text: str, attachments=None):
    kwargs = {"message_id": event.message.body.mid, "text": text}
    if attachments:
        kwargs["attachments"] = attachments
    await event.bot.edit_message(**kwargs)


@router.message_callback(F.callback.payload.contains("teacher:"))
async def teacher_callbacks(event: MessageCallback, context: BaseContext):
    data = event.callback.payload
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id
    bot = event.bot

    async with async_session() as session:
        user = await session.get(User, user_id)
    if not user or user.role != "teacher":
        return

    teacher_id = _get_teacher_config_id(user.name)

    if data == "teacher:main_menu":
        await context.clear()
        count = 0
        if teacher_id:
            async with async_session() as session:
                new_tickets = await ticket_service.get_teacher_tickets(session, teacher_id, "new")
            count = len(new_tickets)
        await _edit(event, f"Привет, {user.name}!", attachments=[main_menu_kb(count)])

    elif data == "teacher:queue":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            tickets = await ticket_service.get_teacher_tickets(session, teacher_id, "new")
            student_names = {}
            for t in tickets:
                s = await session.get(User, t.student_id)
                student_names[t.id] = s.name if s else "Студент"

        if not tickets:
            await _edit(event, "Нет новых обращений.", attachments=[back_to_menu_kb()])
            return

        items = []
        for ticket in tickets:
            category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
            student_name = student_names.get(ticket.id, "Студент")
            items.append((ticket.id, f"{ticket.number} · {student_name} · {category_label}"))
        await _edit(event, f"Очередь ({len(tickets)} новых):", attachments=[queue_list_kb(items)])

    elif data == "teacher:active":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            in_progress = await ticket_service.get_teacher_tickets(session, teacher_id, "in_progress")
            awaiting = await ticket_service.get_teacher_tickets(session, teacher_id, "awaiting_clarification")
            scheduled = await ticket_service.get_teacher_tickets(session, teacher_id, "scheduled")
        tickets = in_progress + awaiting + scheduled
        if not tickets:
            await _edit(event, "Нет активных тикетов.", attachments=[back_to_menu_kb()])
            return
        items = []
        for ticket in tickets:
            status_label = STATUS_LABELS.get(ticket.status, ticket.status)
            category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
            items.append((ticket.id, f"{ticket.number} · {status_label} · {category_label}"))
        await _edit(event, f"Активные тикеты ({len(tickets)}):", attachments=[queue_list_kb(items)])

    elif data == "teacher:closed":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            tickets = await ticket_service.get_teacher_tickets(session, teacher_id, "closed")
        if not tickets:
            await _edit(event, "Нет закрытых тикетов.", attachments=[back_to_menu_kb()])
            return
        items = []
        for ticket in tickets:
            category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
            items.append((ticket.id, f"{ticket.number} · {category_label}"))
        await _edit(event, f"Закрытые тикеты ({len(tickets)}):", attachments=[queue_list_kb(items)])

    elif data == "teacher:stats":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            all_tickets = await ticket_service.get_teacher_tickets(session, teacher_id)
            open_count = sum(1 for t in all_tickets if t.status != "closed")
            closed_tickets = [t for t in all_tickets if t.status == "closed"]
            avg_hours = 0
            if closed_tickets:
                total_h = sum(
                    (t.updated_at - t.created_at).total_seconds() / 3600
                    for t in closed_tickets if t.updated_at and t.created_at
                )
                avg_hours = round(total_h / len(closed_tickets), 1)
            useful_pct = 0
            if closed_tickets:
                ids = [t.id for t in closed_tickets]
                r = await session.execute(select(Rating).where(Rating.ticket_id.in_(ids)))
                ratings = r.scalars().all()
                useful = sum(1 for x in ratings if x.rating == "useful")
                useful_pct = round(useful / len(ratings) * 100) if ratings else 0
        await _edit(event,
            f"Ваша статистика:\n\n"
            f"Всего тикетов: {len(all_tickets)}\n"
            f"Открытых: {open_count}\n"
            f"Среднее время закрытия: {avg_hours} ч\n"
            f"Полезных ответов: {useful_pct}%",
            attachments=[back_to_menu_kb()],
        )

    elif data == "teacher:upload_kb":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.teacher_id == teacher_id)
            )
            kb = kb_result.scalar_one_or_none()
        if kb:
            updated = kb.updated_at.replace(tzinfo=__import__('datetime').timezone.utc).astimezone(
                __import__('datetime').timezone(__import__('datetime').timedelta(hours=3))
            ).strftime('%d.%m.%Y %H:%M')
            await _edit(event,
                f"📚 База знаний\n\nИсточник: {kb.filename}\nОбъём: {len(kb.content)} симв.\nОбновлено: {updated}",
                attachments=[kb_menu_kb(True)],
            )
        else:
            await _edit(event, "📚 База знаний\n\nБаза знаний ещё не загружена.", attachments=[kb_menu_kb(False)])

    elif data == "teacher:kb_view":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.teacher_id == teacher_id)
            )
            kb = kb_result.scalar_one_or_none()
        if not kb:
            await _edit(event, "База знаний не загружена.", attachments=[kb_menu_kb(False)])
            return
        preview = kb.content[:3000]
        truncated = "…\n\n[показаны первые 3000 символов]" if len(kb.content) > 3000 else ""
        from maxapi.types import ButtonsPayload, CallbackButton
        back_kb = ButtonsPayload(buttons=[
            [CallbackButton(text="« Назад", payload="teacher:upload_kb")]
        ]).pack()
        await _edit(event, f"{preview}{truncated}", attachments=[back_kb])

    elif data == "teacher:kb_edit":
        await context.set_state(TeacherStates.uploading_kb)
        await context.update_data(kb_mode="replace")
        await _edit(event,
            "✏️ Отправьте новое содержимое базы знаний — PDF или текст.\nТекущие данные будут заменены.",
            attachments=[kb_menu_kb(False)],
        )

    elif data == "teacher:kb_add":
        await context.set_state(TeacherStates.uploading_kb)
        await context.update_data(kb_mode="append")
        await _edit(event,
            "➕ Отправьте данные для добавления в базу знаний — PDF или текст.\nОни будут добавлены к существующим.",
            attachments=[kb_menu_kb(False)],
        )

    elif data == "teacher:kb_delete":
        await _edit(event, "Удалить всю базу знаний?", attachments=[kb_delete_confirm_kb()])

    elif data == "teacher:kb_confirm_delete":
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.teacher_id == teacher_id)
            )
            kb = kb_result.scalar_one_or_none()
            if kb:
                await session.delete(kb)
                await session.commit()
        await _edit(event, "🗑 База знаний удалена.", attachments=[kb_menu_kb(False)])

    elif data.startswith("teacher:accept:"):
        ticket_id = int(data.split(":")[-1])
        async with async_session() as session:
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            if not ticket:
                await _edit(event, "Тикет не найден.", attachments=[back_to_menu_kb()])
                return
            await ticket_service.update_ticket_status(session, ticket_id, "in_progress")
            await ticket_service.add_log(session, ticket_id, "accepted", user_id)
            student = await session.get(User, ticket.student_id)
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number
            await session.commit()
        await _show_ticket_detail_teacher(event, ticket_id)
        if student_chat:
            await notification_service.notify_student_accepted(bot, student_chat, ticket_number)

    elif data.startswith("teacher:view:"):
        ticket_id = int(data.split(":")[-1])
        await _show_ticket_detail_teacher(event, ticket_id)

    elif data.startswith("teacher:request_clarification:"):
        ticket_id = int(data.split(":")[-1])
        await context.set_state(TeacherStates.requesting_clarification)
        await context.update_data(clar_ticket_id=ticket_id, clar_selected=[])
        await _edit(event,
            "Что именно нужно уточнить?\n(можно выбрать несколько)",
            attachments=[clarification_fields_kb(ticket_id, [])],
        )

    elif data.startswith("teacher:clar_field:"):
        parts = data.split(":")
        ticket_id = int(parts[2])
        field_key = parts[3]
        fsm_data = await context.get_data()
        selected = list(fsm_data.get("clar_selected", []))
        if field_key in selected:
            selected.remove(field_key)
        else:
            selected.append(field_key)
        await context.update_data(clar_selected=selected)
        await _edit(event,
            "Что именно нужно уточнить?\n(можно выбрать несколько)",
            attachments=[clarification_fields_kb(ticket_id, selected)],
        )

    elif data.startswith("teacher:clar_comment:"):
        ticket_id = int(data.split(":")[-1])
        await context.update_data(awaiting_clar_comment=True, clar_ticket_id=ticket_id)
        await _edit(event, "Введите комментарий к запросу уточнения:")

    elif data.startswith("teacher:clar_send:"):
        ticket_id = int(data.split(":")[-1])
        fsm_data = await context.get_data()
        selected_keys = fsm_data.get("clar_selected", [])
        comment = fsm_data.get("clar_comment")
        field_labels = {k: label for label, k in CLARIFICATION_FIELDS}
        field_names = [field_labels.get(k, k) for k in selected_keys]

        async with async_session() as session:
            clar = Clarification(
                ticket_id=ticket_id,
                requested_fields=json.dumps(field_names, ensure_ascii=False),
                teacher_comment=comment,
            )
            session.add(clar)
            await ticket_service.update_ticket_status(session, ticket_id, "awaiting_clarification")
            await ticket_service.add_log(session, ticket_id, "clarification_requested", user_id, comment)
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            student = await session.get(User, ticket.student_id) if ticket else None
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number if ticket else "?"
            await session.commit()

        await context.clear()
        await _edit(event, "✅ Запрос уточнения отправлен студенту.", attachments=[back_to_menu_kb()])
        if student_chat:
            await notification_service.notify_student_clarification(bot, student_chat, ticket_number, field_names, comment, ticket_id)

    elif data.startswith("teacher:ai_suggest:"):
        ticket_id = int(data.split(":")[-1])
        if not teacher_id:
            await _edit(event, "Вы не найдены в справочнике.", attachments=[back_to_menu_kb()])
            return
        async with async_session() as session:
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.teacher_id == teacher_id)
            )
            kb = kb_result.scalar_one_or_none()

        if not kb:
            await _edit(event,
                "База знаний не загружена. Добавьте её через «📚 База знаний» в главном меню.",
                attachments=[working_ticket_kb(ticket_id)],
            )
            return

        await _edit(event, "⏳ Генерирую ответ...")
        try:
            import asyncio
            suggestion = await asyncio.wait_for(
                ai_service.suggest_teacher_answer(kb.content, ticket.text if ticket else ""),
                timeout=25.0,
            )
        except asyncio.TimeoutError:
            suggestion = None
        except Exception:
            suggestion = None

        if not suggestion:
            await _edit(event,
                "ИИ не смог сформировать ответ. Попробуйте позже или ответьте вручную.",
                attachments=[working_ticket_kb(ticket_id)],
            )
            return

        await context.update_data(ai_suggestion=suggestion)
        await _edit(event,
            f"💡 Предлагаемый ответ студенту:\n\n{suggestion}",
            attachments=[ai_suggestion_kb(ticket_id)],
        )

    elif data.startswith("teacher:ai_send:"):
        ticket_id = int(data.split(":")[-1])
        fsm_data = await context.get_data()
        suggestion = fsm_data.get("ai_suggestion", "")
        async with async_session() as session:
            await ticket_service.update_ticket_status(session, ticket_id, "closed")
            await ticket_service.add_log(session, ticket_id, "closed", user_id, suggestion)
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            student = await session.get(User, ticket.student_id) if ticket else None
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number if ticket else "?"
            await session.commit()
        await context.clear()
        await _edit(event, "✅ Ответ отправлен студенту, тикет закрыт.", attachments=[back_to_menu_kb()])
        if student_chat and student_chat != chat_id:
            await notification_service.notify_student_closed(bot, student_chat, ticket_number, suggestion, ticket_id)

    elif data.startswith("teacher:answer:"):
        ticket_id = int(data.split(":")[-1])
        await context.set_state(TeacherStates.entering_answer)
        await context.update_data(answer_ticket_id=ticket_id)
        await _edit(event, "Введите текст ответа:")

    elif data.startswith("teacher:close:"):
        ticket_id = int(data.split(":")[-1])
        await context.set_state(TeacherStates.entering_close_comment)
        await context.update_data(close_ticket_id=ticket_id, close_prompt_mid=event.message.body.mid)
        await _edit(event, "Введите комментарий к закрытию (или «-» без комментария):")

    elif data.startswith("teacher:outcome:"):
        outcome = data.split(":")[-1]
        fsm_data = await context.get_data()
        ticket_id = fsm_data.get("answer_ticket_id")
        answer_text = fsm_data.get("answer_text", "")
        outcome_labels = {
            "resolved": "Решено", "redirected": "Перенаправлено",
            "rejected": "Отказано с причиной", "scheduled": "Консультация назначена",
        }
        outcome_label = outcome_labels.get(outcome, outcome)
        async with async_session() as session:
            await ticket_service.update_ticket_status(session, ticket_id, "closed")
            await ticket_service.add_log(session, ticket_id, "closed", user_id, f"{outcome_label}: {answer_text}")
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            student = await session.get(User, ticket.student_id) if ticket else None
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number if ticket else "?"
            await session.commit()
        await context.clear()
        await _edit(event, "✅ Тикет закрыт.", attachments=[back_to_menu_kb()])
        if student_chat and student_chat != chat_id:
            await notification_service.notify_student_closed(bot, student_chat, ticket_number, answer_text, ticket_id)

    elif data.startswith("teacher:schedule:"):
        ticket_id = int(data.split(":")[-1])
        await context.set_state(TeacherStates.offering_slots)
        await context.update_data(schedule_ticket_id=ticket_id)
        await _edit(event,
            "Введите 2-3 варианта времени консультации (каждый с новой строки).\n"
            "Например:\nПн 26 мая 14:00\nВт 27 мая 10:00"
        )

    elif data.startswith("teacher:close_after_consult:"):
        ticket_id = int(data.split(":")[-1])
        async with async_session() as session:
            await ticket_service.update_ticket_status(session, ticket_id, "closed")
            await ticket_service.add_log(session, ticket_id, "closed", user_id, "Консультация проведена")
            await session.commit()
        await _edit(event, "✅ Тикет закрыт после консультации.", attachments=[back_to_menu_kb()])


@router.message_created(
    TeacherStates.uploading_kb,
    TeacherStates.entering_answer,
    TeacherStates.entering_close_comment,
    TeacherStates.requesting_clarification,
    TeacherStates.offering_slots,
)
async def teacher_text_input(event: MessageCreated, context: BaseContext):
    current_state = await context.get_state()
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id
    bot = event.bot
    text = event.message.body.text if event.message and event.message.body else ""

    async with async_session() as session:
        user = await session.get(User, user_id)
    if not user or user.role != "teacher":
        return

    teacher_id = _get_teacher_config_id(user.name)

    if current_state == str(TeacherStates.uploading_kb):
        if not teacher_id:
            await bot.send_message(chat_id=chat_id, text="Вы не найдены в справочнике.")
            await context.clear()
            return

        attachments = getattr(event.message, "attachments", None) or []
        pdf_attachment = None
        for att in attachments:
            att_type = getattr(att, "type", None)
            if att_type and str(att_type).lower() in ("file", "attachment"):
                pdf_attachment = att
                break

        if pdf_attachment:
            try:
                payload = getattr(pdf_attachment, "payload", None)
                file_url = getattr(payload, "url", None) if payload else None
                filename = getattr(payload, "filename", "document.pdf") if payload else "document.pdf"
                if file_url:
                    import aiohttp
                    async with aiohttp.ClientSession() as http:
                        async with http.get(file_url) as resp:
                            file_bytes = await resp.read()
                    extracted_text = pdf_service.extract_text(file_bytes)
                else:
                    extracted_text = ""
            except Exception:
                extracted_text = ""
                filename = "document.pdf"

            if not extracted_text:
                await bot.send_message(chat_id=chat_id, text="Не удалось извлечь текст из файла.")
                await context.clear()
                return
        elif text.strip():
            extracted_text = text.strip()
            filename = "текст"
        else:
            await bot.send_message(
                chat_id=chat_id,
                text="Отправьте PDF-файл или напишите текст с требованиями курса.",
            )
            return

        fsm_data = await context.get_data()
        kb_mode = fsm_data.get("kb_mode", "replace")

        async with async_session() as session:
            existing = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.teacher_id == teacher_id)
            )
            kb = existing.scalar_one_or_none()
            if kb:
                if kb_mode == "append":
                    kb.content = kb.content + "\n\n" + extracted_text
                    kb.filename = f"{kb.filename} + {filename}" if kb.filename != filename else filename
                else:
                    kb.content = extracted_text
                    kb.filename = filename
                kb.updated_at = datetime.utcnow()
            else:
                session.add(KnowledgeBase(teacher_id=teacher_id, filename=filename, content=extracted_text))
            await session.commit()

        await context.clear()
        action = "Данные добавлены" if kb_mode == "append" else "База знаний загружена"
        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ {action} ({len(extracted_text)} симв.).",
            attachments=[kb_menu_kb(True)],
        )

    elif current_state == str(TeacherStates.entering_answer):
        fsm_data = await context.get_data()
        ticket_id = fsm_data.get("answer_ticket_id")
        await context.update_data(answer_text=text)
        await bot.send_message(
            chat_id=chat_id,
            text="Выберите итог обращения:",
            attachments=[close_outcome_kb(ticket_id)],
        )

    elif current_state == str(TeacherStates.entering_close_comment):
        fsm_data = await context.get_data()
        ticket_id = fsm_data.get("close_ticket_id")
        close_prompt_mid = fsm_data.get("close_prompt_mid")
        comment = None if text.strip() == "-" else text
        async with async_session() as session:
            await ticket_service.update_ticket_status(session, ticket_id, "closed")
            await ticket_service.add_log(session, ticket_id, "closed", user_id, comment)
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            student = await session.get(User, ticket.student_id) if ticket else None
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number if ticket else "?"
            await session.commit()
        await context.clear()
        if close_prompt_mid:
            await bot.edit_message(message_id=close_prompt_mid, text="✅ Тикет закрыт.", attachments=[back_to_menu_kb()])
        else:
            await bot.send_message(chat_id=chat_id, text="✅ Тикет закрыт.", attachments=[back_to_menu_kb()])
        if student_chat and student_chat != chat_id:
            await notification_service.notify_student_closed(bot, student_chat, ticket_number, comment or "", ticket_id)

    elif current_state == str(TeacherStates.requesting_clarification):
        fsm_data = await context.get_data()
        if fsm_data.get("awaiting_clar_comment"):
            ticket_id = fsm_data.get("clar_ticket_id")
            selected = fsm_data.get("clar_selected", [])
            await context.update_data(clar_comment=text, awaiting_clar_comment=False)
            await bot.send_message(
                chat_id=chat_id,
                text=f"Комментарий добавлен: «{text}»\nНажмите «Отправить запрос».",
                attachments=[clarification_fields_kb(ticket_id, selected)],
            )

    elif current_state == str(TeacherStates.offering_slots):
        fsm_data = await context.get_data()
        ticket_id = fsm_data.get("schedule_ticket_id")
        slots = [s.strip() for s in text.split("\n") if s.strip()]
        async with async_session() as session:
            ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
            student = await session.get(User, ticket.student_id) if ticket else None
            student_chat = student.chat_id if student else None
            ticket_number = ticket.number if ticket else "?"
        await context.update_data(**{f"slots_{ticket_id}": slots})
        await context.set_state(None)
        await bot.send_message(
            chat_id=chat_id,
            text="✅ Варианты времени отправлены студенту.",
            attachments=[after_schedule_kb(ticket_id)],
        )
        if student_chat:
            await notification_service.notify_student_slots(bot, student_chat, ticket_number, slots, ticket_id)


async def _show_ticket_detail_teacher(event: MessageCallback, ticket_id: int):
    async with async_session() as session:
        ticket = await ticket_service.get_ticket_by_id(session, ticket_id)
        if not ticket:
            await _edit(event, "Тикет не найден.", attachments=[back_to_menu_kb()])
            return
        logs = await ticket_service.get_ticket_logs(session, ticket_id)
        student = await session.get(User, ticket.student_id)

    status_label = STATUS_LABELS.get(ticket.status, ticket.status)
    category_label = CATEGORY_LABELS.get(ticket.category, ticket.category)
    student_name = student.name if student else "Студент"
    student_group = getattr(student, "group", None) or "ИКБО-65-23"

    action_labels = {
        "created": "Создано", "accepted": "Принято в работу",
        "clarification_requested": "Запрошено уточнение",
        "clarification_provided": "Уточнение предоставлено",
        "answered": "Отвечено", "closed": "Закрыто",
    }
    history_str = "\n".join(
        f"• {action_labels.get(log.action, log.action)} — {_fmt_dt(log.created_at)}"
        for log in logs
    ) or "Нет записей"

    kb = new_ticket_detail_kb(ticket_id) if ticket.status == "new" else working_ticket_kb(ticket_id)
    await _edit(event,
        f"{ticket.number} · [{status_label}]\n\n"
        f"Студент: {student_name}\n"
        f"Группа: {student_group}\n"
        f"Категория: {category_label}\n"
        f"Текст: {ticket.text}\n\n"
        f"История:\n{history_str}",
        attachments=[kb],
    )
