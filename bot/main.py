import asyncio
from loguru import logger
from sqlalchemy import select

from maxapi import Bot, Dispatcher

from core.config import settings
from core.db import engine, async_session, Base
from core.models.bot_state import BotState
from bot.handlers import onboarding, student, teacher, common


async def load_marker(session) -> int | None:
    result = await session.execute(select(BotState).where(BotState.key == "marker"))
    state = result.scalar_one_or_none()
    return int(state.value) if state and state.value else None


async def save_marker(marker: int) -> None:
    async with async_session() as session:
        existing = await session.execute(select(BotState).where(BotState.key == "marker"))
        state = existing.scalar_one_or_none()
        if state:
            state.value = str(marker)
        else:
            session.add(BotState(key="marker", value=str(marker)))
        await session.commit()


async def marker_saver_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(30)
        if bot.marker_updates is not None:
            try:
                await save_marker(bot.marker_updates)
            except Exception as e:
                logger.error(f"Failed to save marker: {e}")


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot = Bot(token=settings.MAX_BOT_TOKEN)
    dp = Dispatcher()

    dp.include_routers(onboarding.router, student.router, teacher.router, common.router)

    async with async_session() as session:
        marker = await load_marker(session)

    if marker is not None:
        bot.set_marker_updates(marker)
        logger.info(f"Restored polling marker: {marker}")

    asyncio.create_task(marker_saver_loop(bot))

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
