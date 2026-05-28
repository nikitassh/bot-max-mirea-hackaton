from loguru import logger


async def safe_send(bot, chat_id: int, text: str, attachments=None):
    try:
        kwargs = {"chat_id": chat_id, "text": text}
        if attachments:
            kwargs["attachments"] = attachments
        await bot.send_message(**kwargs)
    except Exception as e:
        logger.error(f"notification send error to {chat_id}: {e}")


async def notify_teacher_new_ticket(bot, teacher_chat_id: int, ticket_number: str, student_name: str, summary: str, ticket_id: int):
    from bot.keyboards.teacher_kb import new_ticket_notify_kb
    text = f"📥 Новое обращение {ticket_number} от {student_name}.\nИИ: {summary}"
    await safe_send(bot, teacher_chat_id, text, attachments=[new_ticket_notify_kb(ticket_id)])


async def notify_student_accepted(bot, student_chat_id: int, ticket_number: str):
    text = f"👀 Обращение {ticket_number} принято в работу"
    await safe_send(bot, student_chat_id, text)


async def notify_student_clarification(bot, student_chat_id: int, ticket_number: str, fields: list[str], comment: str | None, ticket_id: int):
    from bot.keyboards.student_kb import reply_clarification_kb
    fields_str = "\n".join(f"• {f}" for f in fields)
    comment_part = f"\nКомментарий: {comment}" if comment else ""
    text = f"❓ По обращению {ticket_number} нужно уточнение:\n{fields_str}{comment_part}"
    await safe_send(bot, student_chat_id, text, attachments=[reply_clarification_kb(ticket_id)])


async def notify_teacher_clarification_reply(bot, teacher_chat_id: int, ticket_number: str, reply: str, ticket_id: int):
    from bot.keyboards.teacher_kb import view_ticket_kb
    text = f"💬 Ответ на уточнение по {ticket_number}: {reply}"
    await safe_send(bot, teacher_chat_id, text, attachments=[view_ticket_kb(ticket_id)])


async def notify_student_pending_confirm(bot, student_chat_id: int, ticket_number: str, answer: str, ticket_id: int):
    from bot.keyboards.student_kb import confirm_close_kb
    text = (
        f"Преподаватель ответил на обращение {ticket_number}:\n\n"
        f"{answer}\n\n"
        f"Вопрос решён?"
    )
    await safe_send(bot, student_chat_id, text, attachments=[confirm_close_kb(ticket_id)])


async def notify_student_rejected(bot, student_chat_id: int, ticket_number: str, reason: str):
    text = f"Обращение {ticket_number} отклонено.\nПричина: {reason}"
    await safe_send(bot, student_chat_id, text)


async def notify_student_closed(bot, student_chat_id: int, ticket_number: str, answer: str, ticket_id: int):
    from bot.keyboards.student_kb import rating_kb
    text = f"✅ Обращение {ticket_number} закрыто.\nОтвет: {answer}"
    await safe_send(bot, student_chat_id, text, attachments=[rating_kb(ticket_id)])


async def notify_teacher_reopened(bot, teacher_chat_id: int, ticket_number: str, comment: str, ticket_id: int):
    from bot.keyboards.teacher_kb import view_ticket_kb
    text = f"Студент оспорил закрытие обращения {ticket_number}:\n{comment}"
    await safe_send(bot, teacher_chat_id, text, attachments=[view_ticket_kb(ticket_id)])


async def notify_student_slots(bot, student_chat_id: int, ticket_number: str, slots: list[str], ticket_id: int):
    from bot.keyboards.student_kb import slots_kb
    text = f"📅 Преподаватель предлагает консультацию по {ticket_number}"
    await safe_send(bot, student_chat_id, text, attachments=[slots_kb(ticket_id, slots)])


async def notify_teacher_slot_chosen(bot, teacher_chat_id: int, student_name: str, slot: str):
    text = f"✅ {student_name} выбрал: {slot}"
    await safe_send(bot, teacher_chat_id, text)
