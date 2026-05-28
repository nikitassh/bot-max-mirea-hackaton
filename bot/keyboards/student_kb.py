from maxapi.types import ButtonsPayload, CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment

from teachers_config import TEACHERS

CATEGORY_LABELS = {
    "lab_work": "Лабораторные работы",
    "project": "Проект",
    "access": "Доступы",
    "grading": "Оценивание",
    "retake": "Пересдача",
    "other": "Прочее",
}


def main_menu_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="✏️ Создать обращение", payload="student:create")],
        [CallbackButton(text="📋 Мои обращения", payload="student:my_tickets")],
        [CallbackButton(text="❓ Помощь", payload="common:help")],
        [CallbackButton(text="🗑 Удалить мои данные", payload="common:delete_data")],
    ]).pack()


PAGE_SIZE = 7


def teachers_kb(page: int = 0) -> Attachment:
    total = len(TEACHERS)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    start = page * PAGE_SIZE
    chunk = TEACHERS[start:start + PAGE_SIZE]

    rows = [
        [CallbackButton(text=t["name"], payload=f"student:teacher:{t['id']}")]
        for t in chunk
    ]

    prev_payload = f"student:teachers_page:{page - 1}" if page > 0 else "student:noop"
    next_payload = f"student:teachers_page:{page + 1}" if page < total_pages - 1 else "student:noop"
    rows.append([
        CallbackButton(text="◀", payload=prev_payload),
        CallbackButton(text=f"{page + 1}/{total_pages}", payload="student:noop"),
        CallbackButton(text="▶", payload=next_payload),
    ])

    rows.append([CallbackButton(text="« Назад", payload="student:main_menu")])
    return ButtonsPayload(buttons=rows).pack()


def categories_kb() -> Attachment:
    rows = [
        [CallbackButton(text=label, payload=f"student:category:{key}")]
        for key, label in CATEGORY_LABELS.items()
    ]
    rows.append([CallbackButton(text="« Назад", payload="student:create")])
    return ButtonsPayload(buttons=rows).pack()


def ai_answer_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Да, спасибо", payload="student:ai_satisfied")],
        [CallbackButton(text="Нет, всё равно создать тикет", payload="student:ai_skip")],
    ]).pack()


def duplicate_found_kb(existing_ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Посмотреть", payload=f"student:view_ticket:{existing_ticket_id}")],
        [CallbackButton(text="Создать новое", payload="student:force_create")],
    ]).pack()


def confirm_ticket_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Отправить", payload="student:confirm_send")],
        [CallbackButton(text="Отменить", payload="student:cancel_create")],
    ]).pack()


def after_create_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Смотреть статус", payload=f"student:view_ticket:{ticket_id}")],
        [CallbackButton(text="В главное меню", payload="student:main_menu")],
    ]).pack()


def my_tickets_kb(items: list[tuple[int, str]]) -> Attachment:
    rows = [[CallbackButton(text=label, payload=f"student:view_ticket:{tid}")] for tid, label in items]
    rows.append([CallbackButton(text="« В главное меню", payload="student:main_menu")])
    return ButtonsPayload(buttons=rows).pack()


def ticket_list_item_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Открыть", payload=f"student:view_ticket:{ticket_id}")],
    ]).pack()


def reply_clarification_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Ответить", payload=f"student:reply_clarification:{ticket_id}")],
    ]).pack()


def rating_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Полезно", payload=f"student:rate:useful:{ticket_id}")],
        [CallbackButton(text="Не полезно", payload=f"student:rate:not_useful:{ticket_id}")],
    ]).pack()


def slots_kb(ticket_id: int, slots: list[str]) -> Attachment:
    rows = [
        [CallbackButton(text=slot, payload=f"student:slot:{ticket_id}:{i}")]
        for i, slot in enumerate(slots)
    ]
    return ButtonsPayload(buttons=rows).pack()


def back_to_menu_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="« В главное меню", payload="student:main_menu")],
    ]).pack()
