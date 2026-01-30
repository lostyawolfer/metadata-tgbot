import aiofiles
import os
from pathlib import Path

import aiogram.exceptions
from aiogram import Bot
from aiogram.types import FSInputFile, BufferedInputFile
import bot_init

TEMP_DIR = Path('temp')
TEMP_DIR.mkdir(exist_ok=True)


async def download_file(bot: Bot, file_id: str, user_id: int) -> str | None:
    try:
        bot_init.log.info(f"downloading file for user {user_id}")
        file = await bot.get_file(file_id)
        file_path = TEMP_DIR / f"{user_id}_{file.file_unique_id}"

        bot_init.log.debug(f"file path from telegram: {file.file_path}")
        bot_init.log.debug(f"using local api: {bot_init.using_local_api}")

        if bot_init.using_local_api:
            # simply copy the file from the local storage to your temp dir
            async with aiofiles.open(file.file_path, 'rb') as src:
                async with aiofiles.open(file_path, 'wb') as dest:
                    await dest.write(await src.read())
        else:
            await bot.download_file(file.file_path, file_path)

        bot_init.log.info(f"file saved to {file_path}")
        return str(file_path)
    except aiogram.exceptions.TelegramBadRequest as e:
        if "file is too big" in e.message:
            await bot.send_message(user_id, 'файл слишком большой сори тг петух')
        else:
            raise e

async def download_photo(bot: Bot, file_id: str, user_id: int) -> bytes:
    bot_init.log.info(f"downloading photo for user {user_id}")
    file = await bot.get_file(file_id)
    data = b''

    if bot_init.using_local_api:
        # read directly from the path provided by local api
        async with aiofiles.open(file.file_path, 'rb') as f:
            data = await f.read()
    else:
        temp_path = TEMP_DIR / f"{user_id}_photo.jpg"
        await bot.download_file(file.file_path, temp_path)
        async with aiofiles.open(temp_path, 'rb') as f:
            data = await f.read()
        os.remove(temp_path)

    bot_init.log.info(f"photo downloaded, size: {len(data)} bytes")
    return data


async def upload_audio(bot: Bot, chat_id: int, file_path: str,
                       filename: str, thumb_bytes: bytes | None = None) -> None:
    bot_init.log.info(f"uploading audio: {filename}")

    thumb_file = None
    if thumb_bytes:
        thumb_file = BufferedInputFile(thumb_bytes, filename="thumb.jpg")

    audio = FSInputFile(file_path, filename=filename)
    await bot.send_audio(
        chat_id,
        audio,
        thumbnail=thumb_file
    )
    bot_init.log.info("audio uploaded successfully")


def cleanup_file(file_path: str):
    if os.path.exists(file_path):
        os.remove(file_path)
        bot_init.log.info(f"cleaned up {file_path}")