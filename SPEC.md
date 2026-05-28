# Спецификация: Тикет-бот для мессенджера МАСК

> Этот документ является полным техническим заданием. Реализуй всё описанное строго по порядку разделов. Не придумывай функциональность которой нет в спеке.

---

## 1. Контекст и назначение

Чат-бот в мессенджере МАСК для обработки обращений студентов к преподавателям в виде тикетов. Студент создаёт обращение, преподаватель отвечает, весь процесс фиксируется с прозрачной историей действий.

**Важные ограничения из кейса:**
- Слово «срочно» в тексте тикета обрабатывается в стандартном порядке — без приоритизации
- Повторное нажатие кнопки «Отправить» не создаёт дубль — возвращает существующий тикет
- Бот является приложением разработчика, а не платформы — в интерфейсе обязательны дисклеймер и ссылки на документы разработчика

---

## 2. Технический стек

### Backend / Bot
| Компонент | Версия | Назначение |
|---|---|---|
| Python | 3.12+ | основной язык |
| maxapi | latest (pip install maxapi) | фреймворк для бота МАСК, polling, FSM, inline-кнопки |
| FastAPI | 0.115+ | REST API для будущего веб-приложения |
| uvicorn | latest | ASGI-сервер для FastAPI |
| SQLAlchemy | 2.x async | ORM, shared между ботом и API |
| asyncpg | latest | async драйвер PostgreSQL |
| alembic | latest | миграции схемы БД |
| pydantic-settings | latest | типизированный конфиг из .env |
| openai SDK | latest | клиент для OpenRouter (совместим по API) |
| pymupdf | latest | парсинг PDF → текст для базы знаний |
| loguru | latest | логирование |
| python-dotenv | latest | загрузка .env |

### База данных
- PostgreSQL 16 (в Docker)

### Инфраструктура
- Docker Compose (bot + api + db в одной сети)

### ИИ
- OpenRouter API (совместим с openai SDK, меняется только base_url и api_key)
- Модель по умолчанию: `openai/gpt-4o-mini` (дешёвая, быстрая)

---

## 3. Структура проекта

```
project/
├── bot/
│   ├── __init__.py
│   ├── main.py                  # точка входа бота
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── onboarding.py        # онбординг, согласие, выбор роли
│   │   ├── student.py           # флоу студента
│   │   ├── teacher.py           # флоу преподавателя
│   │   └── common.py            # общие хендлеры (помощь, удаление данных)
│   ├── states/
│   │   ├── __init__.py
│   │   └── forms.py             # StatesGroup для FSM
│   └── keyboards/
│       ├── __init__.py
│       ├── student_kb.py        # клавиатуры студента
│       └── teacher_kb.py        # клавиатуры преподавателя
├── api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app
│   └── routers/
│       ├── __init__.py
│       ├── tickets.py           # GET /tickets, GET /tickets/{id}
│       └── health.py            # GET /health
├── core/
│   ├── __init__.py
│   ├── config.py                # pydantic-settings конфиг
│   ├── db.py                    # engine, session, Base
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── ticket.py
│   │   ├── ticket_log.py
│   │   ├── clarification.py
│   │   ├── rating.py
│   │   └── knowledge_base.py
│   └── services/
│       ├── __init__.py
│       ├── ticket_service.py
│       ├── ai_service.py
│       ├── pdf_service.py
│       └── notification_service.py
├── alembic/
│   ├── env.py
│   └── versions/
├── teachers_config.py           # фиксированный справочник преподавателей
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
└── alembic.ini
```

---

## 4. Конфигурация

### `.env.example`
```
MAX_BOT_TOKEN=your_token_here
DATABASE_URL=postgresql+asyncpg://bot:secret@db:5432/tickets
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
```

### `core/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MAX_BOT_TOKEN: str
    DATABASE_URL: str
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    class Config:
        env_file = ".env"

settings = Settings()
```

### `teachers_config.py` — фиксированный справочник (для демо)
```python
TEACHERS = [
    {"id": 1, "name": "Иванов Иван Иванович", "subject": "Алгоритмы и структуры данных"},
    {"id": 2, "name": "Петрова Анна Сергеевна", "subject": "Базы данных"},
    {"id": 3, "name": "Сидоров Виктор Константинович", "subject": "Операционные системы"},
]
```

---

## 5. Схема базы данных

### `users`
```sql
id          BIGINT PRIMARY KEY          -- user_id из МАСК
role        VARCHAR(20) NOT NULL        -- 'student' | 'teacher'
name        VARCHAR(255) NOT NULL       -- отображаемое имя
chat_id     BIGINT NOT NULL             -- для отправки нотификаций
consent_version VARCHAR(10) NOT NULL    -- версия документов на момент согласия
consent_at  TIMESTAMP NOT NULL
created_at  TIMESTAMP DEFAULT NOW()
```

### `tickets`
```sql
id          SERIAL PRIMARY KEY
number      VARCHAR(10) UNIQUE NOT NULL  -- #42, #43, ...
student_id  BIGINT REFERENCES users(id)
teacher_id  INT REFERENCES teachers(id)  -- из teachers_config
category    VARCHAR(50) NOT NULL         -- см. категории ниже
text        TEXT NOT NULL
status      VARCHAR(30) NOT NULL DEFAULT 'new'
ai_summary  TEXT                         -- ИИ-саммари для преподавателя
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()
```

**Статусы тикета:** `new` → `in_progress` → `awaiting_clarification` → `scheduled` → `closed`

**Категории:** `lab_work` | `project` | `access` | `grading` | `retake` | `other`

### `ticket_log`
```sql
id          SERIAL PRIMARY KEY
ticket_id   INT REFERENCES tickets(id)
action      VARCHAR(50) NOT NULL    -- 'created' | 'accepted' | 'clarification_requested' | 'clarification_provided' | 'answered' | 'closed'
actor_id    BIGINT REFERENCES users(id)
comment     TEXT
created_at  TIMESTAMP DEFAULT NOW()
```

### `clarifications`
```sql
id              SERIAL PRIMARY KEY
ticket_id       INT REFERENCES tickets(id)
requested_fields TEXT NOT NULL       -- JSON список запрошенных полей
teacher_comment TEXT
student_reply   TEXT
created_at      TIMESTAMP DEFAULT NOW()
replied_at      TIMESTAMP
```

### `ratings`
```sql
id          SERIAL PRIMARY KEY
ticket_id   INT REFERENCES tickets(id) UNIQUE
rating      VARCHAR(10) NOT NULL     -- 'useful' | 'not_useful'
created_at  TIMESTAMP DEFAULT NOW()
```

### `knowledge_base`
```sql
id          SERIAL PRIMARY KEY
teacher_id  INT NOT NULL             -- из teachers_config
filename    VARCHAR(255)
content     TEXT NOT NULL            -- распарсенный текст из PDF
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()
```

---

## 6. FSM — состояния диалога

```python
# bot/states/forms.py
from maxapi.context import StatesGroup, State

class OnboardingStates(StatesGroup):
    waiting_consent = State()
    waiting_role    = State()

class StudentStates(StatesGroup):
    choosing_teacher   = State()
    choosing_category  = State()
    entering_text      = State()
    confirming         = State()
    answering_clarification = State()

class TeacherStates(StatesGroup):
    viewing_queue      = State()
    working_ticket     = State()
    entering_answer    = State()
    requesting_clarification = State()
    entering_close_comment   = State()
    offering_slots     = State()
    uploading_kb       = State()
```

---

## 7. Полный флоу бота

### 7.1 Онбординг (все пользователи, первый запуск)

**Триггер:** событие `bot_started` или команда `/start` от нового пользователя (нет в таблице `users`)

**Шаг 1 — Дисклеймер:**
```
Тикет-бот МАСК

Сервис разработан командой хакатона. Не является официальной функцией платформы МАСК.

Разработчик: [имя команды]
[Политика обработки данных] [Условия использования]
```
Кнопки: `[Политика обработки данных]` `[Условия использования]` `[Продолжить]`

**Шаг 2 — Согласие на обработку данных:**
```
Для работы сервиса используются:
• Ваш идентификатор пользователя
• Отображаемое имя

Данные не передаются третьим лицам.
Вы можете удалить их в любой момент через меню.
```
Кнопки: `[Принять и продолжить]` `[Отказаться]`

При нажатии «Отказаться» — бот завершает работу с сообщением «Без согласия сервис недоступен».

При нажатии «Принять» — записать в БД: `consent_version='1.0'`, `consent_at=now()`

**Шаг 3 — Выбор роли:**
```
Добро пожаловать! Выберите вашу роль:
```
Кнопки: `[Я студент]` `[Я преподаватель]`

После выбора — сохранить пользователя в БД и перейти в соответствующее меню.

---

### 7.2 Флоу студента

#### Главное меню студента
```
Привет, {name}! Чем могу помочь?
```
Кнопки:
- `[+ Создать обращение]`
- `[Мои обращения]`
- `[Помощь]`
- `[Удалить мои данные]`

---

#### Создание обращения

**Шаг 1 — Выбор преподавателя:**
Показать список из `teachers_config.py` в виде кнопок.

**Шаг 2 — Выбор категории:**
```
Выберите категорию обращения:
```
Кнопки: `[Лабораторные работы]` `[Проект]` `[Доступы]` `[Оценивание]` `[Пересдача]` `[Прочее]`

**Шаг 3 — Ввод текста:**
```
Опишите ваш вопрос кратко.

⚠️ Не указывайте персональные данные, не нужные для решения вопроса.
Можно приложить ссылку на репозиторий.
```
Студент вводит текст свободно.

**Шаг 4 — ИИ-проверка (если есть база знаний у выбранного преподавателя):**

Вызвать `ai_service.check_knowledge_base(teacher_id, text)`.

Если ИИ нашёл ответ:
```
{ИИ-ответ на основе базы знаний преподавателя}

Это отвечает на ваш вопрос?
```
Кнопки: `[Да, спасибо]` `[Нет, всё равно создать тикет]`

При «Да, спасибо» — тикет НЕ создаётся, пользователь возвращается в главное меню.

**Шаг 5 — Проверка дублей:**

Вызвать `ai_service.check_duplicates(student_id, teacher_id, text)`.

Если найден похожий открытый тикет:
```
У вас уже есть похожее обращение #{number} со статусом {status}.
Посмотреть или создать новое?
```
Кнопки: `[Посмотреть #N]` `[Создать новое]`

**Шаг 6 — Подтверждение:**
```
Ваше обращение:

Преподаватель: {teacher_name}
Категория: {category}
Текст: {text}

Отправить?
```
Кнопки: `[Отправить]` `[Отменить]`

**Идемпотентность:** если у студента есть тикет в статусе `pending_confirm` (создан но не подтверждён) — вернуть его вместо создания нового.

**После подтверждения:**
1. Создать тикет в БД, присвоить номер `#N`
2. Вызвать `ai_service.generate_summary(text)` → сохранить в `tickets.ai_summary`
3. Записать в `ticket_log`: action=`created`
4. Отправить уведомление преподавателю (см. раздел 9)
5. Показать студенту:
```
✅ Обращение #42 создано!

Преподаватель: {teacher_name}
Статус: Новый
```
Кнопки: `[Смотреть статус]` `[В главное меню]`

---

#### Мои обращения

Показать список тикетов студента (открытые сверху, закрытые ниже).

Каждый тикет — карточка:
```
#42 · Лабораторные работы · [Новый]
Иванов И.И. · 5 минут назад
```
Кнопка `[Открыть]` → детальный просмотр тикета.

**Детальный просмотр тикета (студент):**
```
#42 · [В работе]

Преподаватель: Иванов И.И.
Категория: Лабораторные работы
Текст: {text}

История:
• Создано — 14:32
• Принято в работу — 14:45
```
Если статус `awaiting_clarification`:
```
❓ Преподаватель запрашивает уточнение:
• Ссылка на репозиторий
• Номер группы
Комментарий: {teacher_comment}
```
Кнопка: `[Ответить на уточнение]`

---

#### Ответ на уточнение (студент)

Студент вводит текст ответа свободно.

После отправки:
- Обновить `clarifications.student_reply`, `replied_at`
- Изменить статус тикета на `in_progress`
- Записать в `ticket_log`: action=`clarification_provided`
- Уведомить преподавателя

---

#### Удаление данных

```
Будет удалено:
• Ваша привязка к сервису
• Тексты всех ваших обращений ({N} тикетов)

Анонимная статистика (без текстов) сохраняется.

Вы уверены?
```
Кнопки: `[Да, удалить всё]` `[Отмена]`

При подтверждении — удалить пользователя из `users`, обнулить текст тикетов (заменить на `[удалено]`).

---

### 7.3 Флоу преподавателя

#### Главное меню преподавателя
```
Привет, {name}!
```
Кнопки:
- `[Очередь ({N} новых)]`
- `[Активные тикеты]`
- `[Закрытые тикеты]`
- `[Загрузить базу знаний]`
- `[Статистика]`

---

#### Очередь

Показать тикеты со статусом `new`, адресованные этому преподавателю. Сортировка: по времени создания.

Каждая карточка:
```
[Новый] #42
Петров А. · Лабораторные работы
ИИ: «вопрос про формат сдачи лабы №3»
5 минут назад
```
Кнопки под карточкой: `[Принять в работу]` `[Открыть]`

**При нажатии «Принять в работу»:**
- Изменить статус на `in_progress`
- Записать в `ticket_log`: action=`accepted`
- Уведомить студента
- Показать тикет полностью с кнопками действий

---

#### Детальный просмотр тикета (преподаватель)

```
#42 · [В работе]

От: Петров А. (ИВТ-21)
Категория: Лабораторные работы
Текст: Какой формат сдачи лабы №3?

История:
• Создано — 14:32
• Принято в работу — 14:45
```
Кнопки:
- `[Запросить уточнение]`
- `[Ответить и закрыть]`
- `[Назначить консультацию]`
- `[Закрыть]`

---

#### Запрос уточнения

```
Что именно нужно уточнить?
(можно выбрать несколько)
```
Кнопки (мультивыбор через отдельные нажатия, выбранное помечается ✓):
- `[Ссылка на репозиторий]`
- `[Номер группы]`
- `[Скриншот ошибки]`
- `[Тема занятия]`

После выбора: `[Добавить комментарий]` (опционально, однострочный текст) и `[Отправить запрос]`

После отправки:
- Сохранить в `clarifications`
- Изменить статус на `awaiting_clarification`
- Записать в `ticket_log`: action=`clarification_requested`
- Уведомить студента

---

#### Ответ и закрытие

**Ответ текстом:**
Преподаватель вводит текст ответа. После ввода:
```
Выберите итог обращения:
```
Кнопки:
- `[Решено]`
- `[Перенаправлено]`
- `[Отказано с причиной]`
- `[Консультация назначена]`

После выбора:
- Изменить статус на `closed`
- Записать в `ticket_log`: action=`closed`, comment=итог
- Уведомить студента с текстом ответа и кнопками оценки

**Назначить консультацию:**
Преподаватель вводит 2-3 варианта времени текстом (например: «Пн 26 мая 14:00», «Вт 27 мая 10:00»).

Студент получает уведомление с кнопками выбора слота.

После выбора студентом:
- Статус → `scheduled`
- Оба получают подтверждение
- После наступления времени или нажатия кнопки преподавателем `[Закрыть после консультации]` → статус `closed`

---

#### Загрузка базы знаний

```
Отправьте PDF-файл с требованиями к курсу.
Бот извлечёт текст и будет использовать его
для автоответов студентам.
```
Преподаватель присылает PDF.

Бот:
1. Получает файл
2. Вызывает `pdf_service.extract_text(file)`
3. Сохраняет в `knowledge_base`
4. Подтверждает:
```
✅ База знаний загружена.
Извлечено {N} символов из файла {filename}.
Теперь студенты будут получать автоответы
на типичные вопросы до создания тикета.
```

---

#### Статистика (диагностика)

```
Ваша статистика:

Всего тикетов: {N}
Открытых: {N}
Среднее время закрытия: {N} ч
Полезных ответов: {N}%
```

---

## 8. ИИ-сервис (`core/services/ai_service.py`)

Все методы используют OpenRouter через openai SDK.

```python
from openai import AsyncOpenAI
from core.config import settings

client = AsyncOpenAI(
    base_url=settings.OPENROUTER_BASE_URL,
    api_key=settings.OPENROUTER_API_KEY,
)
```

### `categorize_ticket(text: str) -> str`
Определить категорию тикета по тексту. Возвращает одну из: `lab_work | project | access | grading | retake | other`.

Промпт: верни только одно слово из списка категорий без пояснений.

### `generate_summary(text: str) -> str`
Сгенерировать саммари тикета в 1 предложение для отображения преподавателю в очереди.

### `check_knowledge_base(knowledge_text: str, question: str) -> str | None`
Проверить, есть ли ответ на вопрос в базе знаний. Если есть — вернуть ответ. Если нет — вернуть None.

Промпт: «Ниже база знаний преподавателя. Если вопрос студента покрыт базой знаний — ответь кратко и конкретно. Если нет — ответь только словом NULL».

### `check_duplicates(student_tickets: list[dict], new_text: str) -> dict | None`
Проверить похожесть нового вопроса с открытыми тикетами студента. Вернуть наиболее похожий тикет или None.

---

## 9. Система нотификаций (`core/services/notification_service.py`)

Все нотификации — `await bot.send_message(chat_id=..., text=..., attachments=[keyboard])`.

| Событие | Получатель | Текст | Кнопки |
|---|---|---|---|
| Тикет создан | Преподаватель | `📥 Новое обращение #N от {student}. ИИ: {summary}` | `[Принять в работу]` `[Смотреть]` |
| Принято в работу | Студент | `👀 Обращение #N принято в работу` | — |
| Запрос уточнения | Студент | `❓ По обращению #N нужно уточнение: {fields}. Комментарий: {comment}` | `[Ответить]` |
| Студент ответил на уточнение | Преподаватель | `💬 Ответ на уточнение по #N: {reply}` | `[Смотреть тикет]` |
| Тикет закрыт с ответом | Студент | `✅ Обращение #N закрыто. Ответ: {answer}` | `[Полезно]` `[Не полезно]` |
| Предложены слоты консультации | Студент | `📅 Преподаватель предлагает консультацию по #N` | кнопки-слоты |
| Студент выбрал слот | Преподаватель | `✅ {student} выбрал: {slot}` | — |

**Важно:** `chat_id` сохраняется в `users.chat_id` при онбординге. Ошибки отправки логировать, не падать.

---

## 10. FastAPI (`api/`)

### `api/main.py`
```python
from fastapi import FastAPI
from api.routers import tickets, health

app = FastAPI(title="Ticket Bot API", version="1.0.0")
app.include_router(health.router)
app.include_router(tickets.router, prefix="/tickets")
```

### Эндпоинты

**GET /health**
```json
{"status": "ok", "version": "1.0.0"}
```

**GET /tickets**
Query params: `status`, `teacher_id`, `student_id`, `limit=20`, `offset=0`
Возвращает список тикетов.

**GET /tickets/{id}**
Возвращает тикет с полной историей из `ticket_log`.

---

## 11. Docker Compose

```yaml
version: '3.9'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: tickets
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: secret
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot -d tickets"]
      interval: 5s
      timeout: 5s
      retries: 5

  bot:
    build: .
    command: python -m bot.main
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
```

---

## 12. Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]
```

---

## 13. `requirements.txt`

```
maxapi
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
alembic
pydantic-settings
openai
pymupdf
loguru
python-dotenv
```

---

## 14. Маркер обновлений МАСК (важно!)

В МАСК API есть маркер обновлений — без его сохранения бот при перезапуске повторно обрабатывает все старые события.

В `bot/main.py` реализовать сохранение маркера в БД (таблица `bot_state`, ключ `marker`). При старте загружать маркер и передавать в `bot.set_marker_updates(marker)`.

---

## 15. Порядок реализации

Реализуй строго в этом порядке:

1. **Инфраструктура:** `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`
2. **Конфиг:** `core/config.py`, `teachers_config.py`
3. **БД:** все модели SQLAlchemy в `core/models/`, настройка Alembic, первая миграция
4. **Сервисы:** `ticket_service.py`, `ai_service.py`, `pdf_service.py`, `notification_service.py`
5. **FSM:** `bot/states/forms.py`
6. **Клавиатуры:** `bot/keyboards/`
7. **Хендлеры онбординга:** `bot/handlers/onboarding.py`
8. **Хендлеры студента:** `bot/handlers/student.py`
9. **Хендлеры преподавателя:** `bot/handlers/teacher.py`
10. **Общие хендлеры:** `bot/handlers/common.py`
11. **Точка входа бота:** `bot/main.py` с маркером
12. **FastAPI:** `api/main.py`, роутеры
13. **Проверка:** запустить `docker compose up --build`, убедиться что бот отвечает на /start

---

## 16. Критические требования (жюри проверит)

- [ ] Дисклеймер о разработчике показывается при первом запуске
- [ ] Согласие на обработку данных фиксируется в БД с версией и временем
- [ ] Повторное нажатие «Отправить» не создаёт дубль тикета
- [ ] Слово «срочно» в тексте тикета не даёт приоритет — обрабатывается стандартно
- [ ] Студент видит только свои тикеты
- [ ] Преподаватель видит только тикеты адресованные ему
- [ ] Каждое действие фиксируется в `ticket_log` с актором и временем
- [ ] Кнопка «Удалить мои данные» работает с подтверждением и показом что будет удалено
- [ ] ИИ-проверка базы знаний происходит до создания тикета
- [ ] Нотификации отправляются асинхронно, ошибки не роняют основной флоу
