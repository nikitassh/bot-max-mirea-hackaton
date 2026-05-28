from maxapi.types import ButtonsPayload, CallbackButton, LinkButton
from maxapi.types.attachments.attachment import Attachment

WEBAPP_URL = "https://precious-granita-65161f.netlify.app"


def main_menu_kb(new_count: int = 0, active_count: int = 0, closed_count: int = 0) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text=f"📋 Очередь ({new_count} новых)", payload="teacher:queue")],
        [CallbackButton(text=f"🔄 Активные тикеты ({active_count})", payload="teacher:active")],
        [CallbackButton(text=f"✅ Закрытые тикеты ({closed_count})", payload="teacher:closed")],
        [CallbackButton(text="📚 База знаний", payload="teacher:upload_kb")],
        [CallbackButton(text="📊 Статистика", payload="teacher:stats")],
        [CallbackButton(text="📰 Дайджест", payload="teacher:digest")],
        [LinkButton(text="🌐 WebApp Demo", url=WEBAPP_URL)],
    ]).pack()


def kb_articles_list_kb(articles: list) -> Attachment:
    rows = [
        [CallbackButton(text=f"📄 {(a.filename or 'Без названия')[:40]}", payload=f"teacher:kb_article:{a.id}")]
        for a in articles
    ]
    rows.append([CallbackButton(text="➕ Добавить статью", payload="teacher:kb_add_article")])
    rows.append([CallbackButton(text="« Назад", payload="teacher:main_menu")])
    return ButtonsPayload(buttons=rows).pack()


def kb_article_detail_kb(article_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="✏️ Редактировать", payload=f"teacher:kb_edit_article:{article_id}")],
        [CallbackButton(text="🗑 Удалить", payload=f"teacher:kb_delete_article:{article_id}")],
        [CallbackButton(text="« Назад", payload="teacher:upload_kb")],
    ]).pack()


def kb_article_delete_confirm_kb(article_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Да, удалить", payload=f"teacher:kb_confirm_delete_article:{article_id}")],
        [CallbackButton(text="Отмена", payload=f"teacher:kb_article:{article_id}")],
    ]).pack()


def queue_list_kb(items: list[tuple[int, str]]) -> Attachment:
    rows = [[CallbackButton(text=label, payload=f"teacher:view:{tid}")] for tid, label in items]
    rows.append([CallbackButton(text="« Назад", payload="teacher:main_menu")])
    return ButtonsPayload(buttons=rows).pack()


def queue_ticket_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="✅ Принять в работу", payload=f"teacher:accept:{ticket_id}")],
        [CallbackButton(text="🔍 Открыть", payload=f"teacher:view:{ticket_id}")],
        [CallbackButton(text="« Назад", payload="teacher:main_menu")],
    ]).pack()


def new_ticket_detail_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="✅ Принять в работу", payload=f"teacher:accept:{ticket_id}")],
        [CallbackButton(text="« Назад", payload="teacher:queue")],
    ]).pack()


def new_ticket_notify_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Принять в работу", payload=f"teacher:accept:{ticket_id}")],
        [CallbackButton(text="Смотреть", payload=f"teacher:view:{ticket_id}")],
    ]).pack()


def list_item_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="🔍 Открыть", payload=f"teacher:view:{ticket_id}")],
        [CallbackButton(text="« Назад", payload="teacher:main_menu")],
    ]).pack()


def working_ticket_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="💡 Ответ ИИ из базы знаний", payload=f"teacher:ai_suggest:{ticket_id}")],
        [CallbackButton(text="❓ Запросить уточнение", payload=f"teacher:request_clarification:{ticket_id}")],
        [CallbackButton(text="💬 Ответить и закрыть", payload=f"teacher:answer:{ticket_id}")],
        [CallbackButton(text="🔒 Закрыть", payload=f"teacher:close:{ticket_id}")],
        [CallbackButton(text="« Назад", payload="teacher:main_menu")],
    ]).pack()


def ai_suggestion_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="📤 Отправить студенту", payload=f"teacher:ai_send:{ticket_id}")],
        [CallbackButton(text="🔄 Сгенерировать снова", payload=f"teacher:ai_suggest:{ticket_id}")],
        [CallbackButton(text="« Назад к тикету", payload=f"teacher:view:{ticket_id}")],
    ]).pack()


def view_ticket_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Смотреть тикет", payload=f"teacher:view:{ticket_id}")],
    ]).pack()


CLARIFICATION_FIELDS = [
    ("Ссылка на репозиторий", "repo"),
    ("Номер группы", "group"),
    ("Скриншот ошибки", "screenshot"),
    ("Тема занятия", "topic"),
]


def clarification_fields_kb(ticket_id: int, selected: list[str]) -> Attachment:
    rows = []
    for label, key in CLARIFICATION_FIELDS:
        mark = "✓ " if key in selected else ""
        rows.append([CallbackButton(text=f"{mark}{label}", payload=f"teacher:clar_field:{ticket_id}:{key}")])
    rows.append([CallbackButton(text="Добавить комментарий", payload=f"teacher:clar_comment:{ticket_id}")])
    rows.append([CallbackButton(text="📤 Отправить запрос", payload=f"teacher:clar_send:{ticket_id}")])
    rows.append([CallbackButton(text="« Назад", payload=f"teacher:view:{ticket_id}")])
    return ButtonsPayload(buttons=rows).pack()


def close_outcome_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="✅ Решено", payload="teacher:outcome:resolved")],
        [CallbackButton(text="↪️ Перенаправлено", payload="teacher:outcome:redirected")],
        [CallbackButton(text="❌ Отказано с причиной", payload="teacher:outcome:rejected")],
        [CallbackButton(text="📅 Консультация назначена", payload="teacher:outcome:scheduled")],
        [CallbackButton(text="« Назад", payload=f"teacher:view:{ticket_id}")],
    ]).pack()


def after_schedule_kb(ticket_id: int) -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="🔒 Закрыть после консультации", payload=f"teacher:close_after_consult:{ticket_id}")],
        [CallbackButton(text="« Назад", payload=f"teacher:view:{ticket_id}")],
    ]).pack()


def kb_menu_kb(has_content: bool) -> Attachment:
    if has_content:
        return ButtonsPayload(buttons=[
            [CallbackButton(text="👁 Просмотреть", payload="teacher:kb_view")],
            [CallbackButton(text="✏️ Заменить всё", payload="teacher:kb_edit")],
            [CallbackButton(text="➕ Добавить данные", payload="teacher:kb_add")],
            [CallbackButton(text="🗑 Удалить", payload="teacher:kb_delete")],
            [CallbackButton(text="« Назад", payload="teacher:main_menu")],
        ]).pack()
    return ButtonsPayload(buttons=[
        [CallbackButton(text="➕ Загрузить", payload="teacher:kb_edit")],
        [CallbackButton(text="« Назад", payload="teacher:main_menu")],
    ]).pack()


def kb_delete_confirm_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="Да, удалить", payload="teacher:kb_confirm_delete")],
        [CallbackButton(text="Отмена", payload="teacher:upload_kb")],
    ]).pack()


def back_to_menu_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="« В главное меню", payload="teacher:main_menu")],
    ]).pack()


def back_to_kb_kb() -> Attachment:
    return ButtonsPayload(buttons=[
        [CallbackButton(text="« Назад к базе знаний", payload="teacher:upload_kb")],
    ]).pack()
