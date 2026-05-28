from openai import AsyncOpenAI
from loguru import logger

from core.config import settings

client = AsyncOpenAI(
    base_url=settings.OPENROUTER_BASE_URL,
    api_key=settings.OPENROUTER_API_KEY,
    timeout=20.0,
)

CATEGORIES = ["lab_work", "project", "access", "grading", "retake", "other"]


def _get_content(resp) -> str:
    """Extract text from OpenRouter response, falling back to reasoning for thinking models."""
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    if content:
        return content
    # Reasoning models (e.g. nvidia/nemotron) may put the answer only in .reasoning
    reasoning = getattr(msg, "reasoning", None) or ""
    return reasoning.strip()


async def categorize_ticket(text: str) -> str:
    try:
        resp = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Определи категорию обращения студента. "
                        "Верни только одно слово из списка без пояснений: "
                        "lab_work, project, access, grading, retake, other"
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=10,
        )
        category = _get_content(resp).lower()
        return category if category in CATEGORIES else "other"
    except Exception as e:
        logger.error(f"categorize_ticket error: {e}")
        return "other"


async def generate_summary(text: str) -> str:
    try:
        resp = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Отвечай ТОЛЬКО на русском языке. "
                        "Сформулируй суть обращения студента в одном коротком предложении для преподавателя. "
                        "Только суть — без лишних слов."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=80,
        )
        return _get_content(resp) or text[:100]
    except Exception as e:
        logger.error(f"generate_summary error: {e}")
        return text[:100]


async def check_knowledge_base(knowledge_text: str, question: str) -> str | None:
    try:
        resp = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помощник студента. Отвечай ТОЛЬКО на русском языке. "
                        "Ответ должен быть коротким, чётким и по существу — максимум 3 предложения. "
                        "Ниже база знаний преподавателя. "
                        "Если вопрос студента покрыт базой знаний — ответь кратко и конкретно. "
                        "Если нет — ответь только словом NULL.\n\n"
                        f"База знаний:\n{knowledge_text}"
                    ),
                },
                {"role": "user", "content": question},
            ],
            max_tokens=300,
        )
        answer = _get_content(resp)
        return None if not answer or answer.upper() == "NULL" else answer
    except Exception as e:
        logger.error(f"check_knowledge_base error: {e}")
        return None


async def suggest_teacher_answer(knowledge_text: str, question: str) -> str | None:
    try:
        resp = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помощник преподавателя. Отвечай ТОЛЬКО на русском языке. "
                        "Сформулируй короткий конкретный ответ студенту — максимум 3 предложения. "
                        "Пиши только сам ответ, без вступлений, заголовков и пояснений. "
                        "Если база знаний не содержит нужной информации — ответь только словом NULL.\n\n"
                        f"База знаний:\n{knowledge_text}"
                    ),
                },
                {"role": "user", "content": question},
            ],
            max_tokens=300,
        )
        answer = _get_content(resp)
        return None if not answer or answer.upper() == "NULL" else answer
    except Exception as e:
        logger.error(f"suggest_teacher_answer error: {e}")
        return None


async def check_duplicates(student_tickets: list[dict], new_text: str) -> dict | None:
    if not student_tickets:
        return None
    try:
        tickets_str = "\n".join(
            f"#{t['number']} (статус: {t['status']}): {t['text'][:200]}"
            for t in student_tickets
        )
        resp = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Есть открытые тикеты студента:\n"
                        f"{tickets_str}\n\n"
                        "Если новый вопрос очень похож на один из тикетов — верни только номер тикета (например: #5). "
                        "Если нет похожего — ответь только словом NULL."
                    ),
                },
                {"role": "user", "content": new_text},
            ],
            max_tokens=10,
        )
        answer = _get_content(resp)
        if not answer or answer.upper() == "NULL":
            return None
        for t in student_tickets:
            if f"#{t['number']}" == answer or t['number'] == answer.lstrip('#'):
                return t
        return None
    except Exception as e:
        logger.error(f"check_duplicates error: {e}")
        return None
