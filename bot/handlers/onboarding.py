from datetime import datetime

from maxapi import Router, F
from maxapi.types import MessageCreated, MessageCallback, BotStarted
from maxapi.types import ButtonsPayload, CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment
from maxapi.context import BaseContext
from maxapi.types import CommandStart
from core.db import async_session
from core.models.user import User
from bot.states.forms import OnboardingStates

router = Router()

PRIVACY_URL = "https://example.com/privacy"
TERMS_URL = "https://example.com/terms"
CONSENT_VERSION = "1.0"


def disclaimer_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [
            LinkButton(text="Политика обработки данных", url=PRIVACY_URL),
            LinkButton(text="Условия использования", url=TERMS_URL),
        ],
        [CallbackButton(text="Продолжить", payload="onboarding:continue")],
    ]).pack()


def consent_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Принять и продолжить", payload="onboarding:accept")],
        [CallbackButton(text="Отказаться", payload="onboarding:decline")],
    ]).pack()


def role_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Я студент", payload="onboarding:role:student")],
        [CallbackButton(text="Я преподаватель", payload="onboarding:role:teacher")],
    ]).pack()


async def _edit(event: MessageCallback, text: str, attachments=None):
    kwargs = {"message_id": event.message.body.mid, "text": text}
    if attachments:
        kwargs["attachments"] = attachments
    await event.bot.edit_message(**kwargs)


async def _clear_chat(bot, chat_id: int):
    while True:
        result = await bot.get_messages(chat_id=chat_id, count=100)
        if not result.messages:
            break
        deleted = 0
        for msg in result.messages:
            try:
                await bot.delete_message(message_id=msg.body.mid)
                deleted += 1
            except Exception:
                pass
        if deleted == 0 or len(result.messages) < 100:
            break


async def _show_disclaimer(bot, chat_id: int, context: BaseContext):
    await context.clear()
    await _clear_chat(bot, chat_id)
    await context.set_state(OnboardingStates.waiting_consent)
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Тикет-бот МАСК\n\n"
            "Сервис разработан командой хакатона. "
            "Не является официальной функцией платформы МАСК.\n\n"
            "Разработчик: команда хакатона"
        ),
        attachments=[disclaimer_kb()],
    )


@router.bot_started()
async def handle_bot_started(event: BotStarted, context: BaseContext):
    bot = event.bot
    chat_id = event.chat_id
    user_id = event.user.user_id
    await context.update_data(user_id=user_id, chat_id=chat_id, name=_make_name(event.user))
    await _show_disclaimer(bot, chat_id, context)


@router.message_created(CommandStart())
async def handle_start_command(event: MessageCreated, context: BaseContext):
    bot = event.bot
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id
    await context.clear()
    await context.update_data(user_id=user_id, chat_id=chat_id, name=_make_name(event.from_user))
    await _show_disclaimer(bot, chat_id, context)


@router.message_callback(F.callback.payload.contains("onboarding:"))
async def handle_onboarding_callbacks(event: MessageCallback, context: BaseContext):
    data = event.callback.payload
    chat_id = event.chat.chat_id
    user_id = event.from_user.user_id

    if data == "onboarding:continue":
        await context.set_state(OnboardingStates.waiting_consent)
        await _edit(event,
            "Для работы сервиса используются:\n"
            "• Ваш идентификатор пользователя\n"
            "• Отображаемое имя\n\n"
            "Данные не передаются третьим лицам.\n"
            "Вы можете удалить их в любой момент через меню.",
            attachments=[consent_kb()],
        )

    elif data == "onboarding:decline":
        await context.clear()
        await _edit(event, "Без согласия сервис недоступен.")

    elif data == "onboarding:accept":
        await context.set_state(OnboardingStates.waiting_role)
        fsm_data = await context.get_data()
        if "user_id" not in fsm_data:
            await context.update_data(
                user_id=user_id,
                chat_id=chat_id,
                name=_make_name(event.from_user),
            )
        await _edit(event, "Добро пожаловать! Кто вы?", attachments=[role_kb()])

    elif data.startswith("onboarding:role:"):
        role = data.split(":")[-1]
        mid = event.message.body.mid
        fsm_data = await context.get_data()
        uid = fsm_data.get("user_id", user_id)
        cid = fsm_data.get("chat_id", chat_id)
        try:
            await event.bot.delete_message(message_id=mid)
        except Exception:
            pass

        if role == "teacher":
            from teachers_config import TEACHERS
            name = TEACHERS[0]["name"]
            teacher_cfg_id = TEACHERS[0]["id"]
        else:
            name = fsm_data.get("name") or _make_name(event.from_user)
            teacher_cfg_id = None

        async with async_session() as session:
            existing = await session.get(User, uid)
            if existing:
                existing.role = role
                existing.name = name
                existing.chat_id = cid
            else:
                session.add(User(
                    id=uid,
                    role=role,
                    name=name,
                    chat_id=cid,
                    consent_version=CONSENT_VERSION,
                    consent_at=datetime.utcnow(),
                ))
            await session.commit()

        await context.clear()
        await _redirect_to_menu(event.bot, uid, cid, role=role, name=name, teacher_cfg_id=teacher_cfg_id)


def _make_name(user) -> str:
    if user is None:
        return "Пользователь"
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return name or user.username or f"user_{user.user_id}"


async def _redirect_to_menu(bot, user_id: int, chat_id: int, role: str | None = None, name: str | None = None, teacher_cfg_id: int | None = None):
    if role is None or name is None:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if user:
                role = user.role
                name = user.name

    if role == "student":
        from bot.keyboards.student_kb import main_menu_kb
        await bot.send_message(
            chat_id=chat_id,
            text=f"Привет, {name}! Чем могу помочь?",
            attachments=[main_menu_kb()],
        )
    elif role == "teacher":
        from bot.keyboards.teacher_kb import main_menu_kb
        from teachers_config import TEACHERS
        from core.services.ticket_service import get_teacher_tickets
        if teacher_cfg_id is None:
            teacher_cfg_id = next((t["id"] for t in TEACHERS if t["name"] == name), TEACHERS[0]["id"])
        teacher_info = next((t for t in TEACHERS if t["id"] == teacher_cfg_id), TEACHERS[0])
        count = 0
        async with async_session() as session:
            new_tickets = await get_teacher_tickets(session, teacher_cfg_id, "new")
            count = len(new_tickets)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"Вы вошли как преподаватель:\n\n"
                f"👤 {teacher_info['name']}\n\n"
                f"Новых обращений: {count}"
            ),
            attachments=[main_menu_kb(count)],
        )
