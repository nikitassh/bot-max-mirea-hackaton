from maxapi import Router, F
from maxapi.types import MessageCallback, MessageCreated
from maxapi.types import ButtonsPayload, CallbackButton
from maxapi.types import Command
from maxapi.types.attachments.attachment import Attachment
from maxapi.context import BaseContext
from sqlalchemy import select, update

from core.db import async_session
from core.models.user import User
from core.models.ticket import Ticket

router = Router()


def delete_confirm_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Да, удалить всё", payload="common:confirm_delete")],
        [CallbackButton(text="Отмена", payload="common:cancel_delete")],
    ]).pack()


def back_to_menu_kb(role: str = "student") -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="« В главное меню", payload=f"{role}:main_menu")],
    ]).pack()


async def _edit(event: MessageCallback, text: str, attachments=None):
    kwargs = {"message_id": event.message.body.mid, "text": text}
    if attachments:
        kwargs["attachments"] = attachments
    await event.bot.edit_message(**kwargs)


@router.message_callback(F.callback.payload.contains("common:"))
async def common_callbacks(event: MessageCallback, context: BaseContext):
    data = event.callback.payload
    user_id = event.from_user.user_id

    if data == "common:help":
        await _edit(event,
            "Помощь:\n\n"
            "• Для создания обращения нажмите «+ Создать обращение»\n"
            "• Все обращения хранятся в разделе «Мои обращения»\n"
            "• При возникновении вопросов обращайтесь к преподавателю\n\n"
            "По техническим вопросам: разработчик — команда хакатона",
            attachments=[back_to_menu_kb("student")],
        )

    elif data == "common:delete_data":
        async with async_session() as session:
            result = await session.execute(select(Ticket).where(Ticket.student_id == user_id))
            ticket_count = len(result.scalars().all())
        await _edit(event,
            f"Будет удалено:\n"
            f"• Ваша привязка к сервису\n"
            f"• Тексты всех ваших обращений ({ticket_count} тикетов)\n\n"
            f"Анонимная статистика (без текстов) сохраняется.\n\n"
            f"Вы уверены?",
            attachments=[delete_confirm_kb()],
        )

    elif data == "common:confirm_delete":
        async with async_session() as session:
            await session.execute(
                update(Ticket).where(Ticket.student_id == user_id).values(text="[удалено]")
            )
            user = await session.get(User, user_id)
            if user:
                await session.delete(user)
            await session.commit()
        await context.clear()
        await _edit(event, "✅ Все ваши данные удалены. Для повторного использования введите /start.")

    elif data == "common:cancel_delete":
        async with async_session() as session:
            user = await session.get(User, user_id)
        role = user.role if user else "student"
        await _edit(event, "Удаление отменено.", attachments=[back_to_menu_kb(role)])


@router.message_created(Command("me"))
async def handle_me(event: MessageCreated, context: BaseContext):
    user_id = event.from_user.user_id
    await event.bot.send_message(
        chat_id=event.chat.chat_id,
        text=f"Ваш user ID в MAX: {user_id}",
    )
