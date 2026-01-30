import aiohttp
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import dotenv_values


_apis: list[str] = [
    "http://localhost:8081"
]


class ColoredFormatter(logging.Formatter):
    cyan = "\x1b[36m"
    grey = "\x1b[33;20m\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    COLORS = {
        logging.DEBUG: cyan,
        logging.INFO: grey,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelno, self.grey)
        format_str = f"{log_color}[%(levelname)s] %(message)s{self.reset}"
        formatter = logging.Formatter(format_str)
        return formatter.format(record)


handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logging.addLevelName(logging.WARNING, "WARN")

log = logging.getLogger('bot')
log.setLevel(logging.DEBUG)
log.addHandler(handler)


_env = dotenv_values('.env')
using_local_api: bool = False
max_file_size: int = 50 * 1024 * 1024


async def _get_session() -> AiohttpSession:
    global using_local_api
    async with aiohttp.ClientSession() as client_session:
        for api in _apis:
            log.info(f"trying {api}")
            try:
                async with client_session.get(f"{api}", timeout=10) as resp:
                    if resp.status == 404:
                        server = TelegramAPIServer.from_base(api)
                        session = AiohttpSession(api=server)
                        log.info(f"using {api}")
                        using_local_api = True
                        return session
            except Exception as e:
                log.warning(f'{e}')
            log.warning(f"{api} unavailable")
    log.warning("local api unavailable, falling back to default")
    try:
        server = TelegramAPIServer.from_base('https://api.telegram.org')
        session = AiohttpSession(api=server)
        return session
    except Exception as e:
        log.error(f'{e}')
        log.critical('no apis available, exiting')
        exit()


async def init_bot() -> tuple[Bot, Dispatcher]:
    global max_file_size
    session = await _get_session()
    max_file_size = (2000 if using_local_api else 50) * 1024 * 1024
    # 2gb if local, 50mb otherwise
    bot = Bot(token=_env["TOKEN"], session=session)
    my_user = await bot.get_me()
    log.info(f'connected as @{my_user.username}')
    dp = Dispatcher(bot=bot)
    return bot, dp