import asyncio
import bot_init
from modules import handlers

async def main():
    bot, dp = await bot_init.init_bot()
    dp.include_router(handlers.router)
    bot_init.log.info("i'm ready!")
    bot_init.log.debug(f'local api: {bot_init.using_local_api}')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())