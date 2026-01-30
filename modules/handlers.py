from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputMediaPhoto, ReplyKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardRemove, ForceReply
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from . import state_manager as sm
from . import audio_processor as ap
from . import uploader
from bot_init import log

router = Router()


def build_keyboard(trim_start: float = 0, trim_end: float | None = None):
    builder = InlineKeyboardBuilder()
    builder.button(text="название", callback_data="edit:title")
    builder.button(text="автор", callback_data="edit:artist")
    builder.button(text="обложка", callback_data="edit:art")

    # only show timestamps if they're set
    if trim_start > 0:
        start_text = f"начало {format_time(trim_start)}"
    else:
        start_text = "начало"

    if trim_end is not None:
        end_text = f"конец {format_time(trim_end)}"
    else:
        end_text = "конец"

    builder.button(text=start_text, callback_data="edit:trim_start")
    builder.button(text=end_text, callback_data="edit:trim_end")

    builder.button(text="✅ готово", callback_data="done")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


def format_info(title: str, artist: str) -> str:
    return f"**{title}**\nby {artist}"


def format_time(seconds: float) -> str:
    """format seconds as m:ss.s"""
    m = int(seconds // 60)
    s = seconds % 60
    if s % 1 == 0:
        return f"{m}:{int(s):02d}"
    return f"{m}:{s:04.1f}" # e.g. 3:21.5


def get_none_keyboard():
    """keyboard with 'none' button"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="не обрезать")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


@router.message(Command(commands=["start"]))
async def start(msg: Message):
    await msg.answer(
        """<b><u>lostya's audio metadata editor</u></b>
меняет данные аудиофайла и позволяет его обрезать

<b><i>КАК ПОЛЬЗОВАТЬСЯ:</i></b>
<blockquote>- скинь аудио
- бот покажет тебе текущих автора, название и обложку аудио
- (предел 2 гб)
- можно будет изменить автора название и обложку
- можно будет обрезать аудио в начале и в конце
- обрезка поддерживает нецелые значения между секундами</blockquote>""",
        parse_mode="HTML",
    )

@router.message(F.audio)
async def handle_audio(msg: Message, bot: Bot):
    user_id = msg.from_user.id
    log.info(f"user {user_id}: received audio")

    downloading_msg = await msg.reply("скачиваю...")

    old_session = sm.get_session(user_id)
    if old_session:
        log.info(f"user {user_id}: canceling previous session")
        try:
            await bot.delete_message(msg.chat.id, old_session.info_message_id)
            if old_session.prompt_message_id:
                await bot.delete_message(msg.chat.id, old_session.prompt_message_id)
        except Exception as e:
            log.warning(f"user {user_id}: failed to clean up old session messages: {e}")
        uploader.cleanup_file(old_session.file_path)
        sm.delete_session(user_id)

    file_path = await uploader.download_file(bot, msg.audio.file_id, user_id)
    log.info(f"user {user_id}: extracting metadata")
    metadata = ap.extract_metadata(file_path)
    art = ap.extract_album_art(file_path)

    if art_io := ap.prepare_art_for_telegram(art):
        art_file = BufferedInputFile(art_io.read(), 'cover.jpg')
        sent = await msg.answer_photo(
            art_file,
            caption=format_info(metadata['title'], metadata['artist']),
            reply_markup=build_keyboard()
        )
    else:
        sent = await msg.answer(
            format_info(metadata['title'], metadata['artist']),
            reply_markup=build_keyboard()
        )

    await bot.delete_message(msg.chat.id, downloading_msg.message_id)

    sm.create_session(
        user_id, file_path, msg.audio.file_name or 'audio.mp3',
        metadata['title'], metadata['artist'], art, sent.message_id
    )
    log.info(f"[{user_id}] session created")


@router.callback_query(F.data.startswith("edit:"))
async def handle_edit(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    session = sm.get_session(user_id)
    if not session:
        return

    field = callback.data.split(':')[1]

    # cleanup: delete old prompt AND old error message if they exist
    for msg_id in [session.prompt_message_id, session.error_message_id]:
        if msg_id:
            try:
                await bot.delete_message(callback.message.chat.id, msg_id)
            except:
                pass
    sm.update_field(user_id, 'error_message_id', None)  # reset error id
    log.info(f"[{user_id}] editing {field}")

    # delete old prompt if exists
    if session.prompt_message_id:
        try:
            await bot.delete_message(callback.message.chat.id, session.prompt_message_id)
        except:
            pass

    prompts = {
        'title': 'как назвать?',
        'artist': 'кто автор?',
        'art': 'кидай новую обложку (в виде фото, не файлом)',
        'trim_start': 'с какого момента?\n(например: 23, 1:23, 1:01:23, 4:23.5, 3.33)',
        'trim_end': 'до какого момента?\n(например: 23, 1:23, 1:01:23, 4:23.5, 3.33)'
    }

    current_val = {
        'title': session.title,
        'artist': session.artist,
        'trim_start': format_time(session.trim_start) if session.trim_start > 0 else '0:00',
        'trim_end': format_time(session.trim_end) if session.trim_end else 'конец трека'
    }.get(field, "")

    if field in ['trim_start', 'trim_end']:
        prompt_msg = await callback.message.answer(
            prompts[field],
            reply_markup=get_none_keyboard(),
            reply_to_message_id=callback.message.message_id
        )
    else:
        force_reply = ForceReply(
            input_field_placeholder=str(current_val)[:64],
            selective=True
        )
        prompt_msg = await callback.message.answer(
            prompts[field],
            reply_markup=force_reply,
            reply_to_message_id=callback.message.message_id
        )

    sm.set_editing_field(user_id, field, prompt_msg.message_id)
    await callback.answer()


async def update_info_message(bot: Bot, session: sm.EditSession, chat_id: int):
    """helper to update the info message"""
    try:
        if session.album_art:
            art_io = ap.prepare_art_for_telegram(session.album_art)
            art_file = BufferedInputFile(art_io.read(), 'cover.jpg')
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=session.info_message_id,
                media=InputMediaPhoto(
                    media=art_file,
                    caption=format_info(session.title, session.artist)
                ),
                reply_markup=build_keyboard(session.trim_start, session.trim_end),
            )
        else:
            await bot.edit_message_text(
                format_info(session.title, session.artist),
                chat_id=chat_id,
                message_id=session.info_message_id,
                reply_markup=build_keyboard(session.trim_start, session.trim_end)
            )
    except TelegramBadRequest as e:
        if "message is not modified" in e.message:
            return
        raise e


@router.message(F.text)
async def handle_text_edit(msg: Message, bot: Bot):
    user_id = msg.from_user.id
    session = sm.get_session(user_id)

    if not session or not session.editing_field:
        await msg.delete()
        return

    # helper to clean up error message if it exists
    async def delete_error():
        if session.error_message_id:
            try:
                await bot.delete_message(msg.chat.id, session.error_message_id)
            except:
                pass
            sm.update_field(user_id, 'error_message_id', None)

    # handle "none" for trim fields
    if msg.text.lower() == "не обрезать":
        if session.editing_field == 'trim_start':
            sm.update_field(user_id, 'trim_start', 0.0)
        elif session.editing_field == 'trim_end':
            sm.update_field(user_id, 'trim_end', None)
    elif session.editing_field in ['title', 'artist']:
        sm.update_field(user_id, session.editing_field, msg.text)
    elif session.editing_field in ['trim_start', 'trim_end']:
        try:
            seconds = ap.parse_timestamp(msg.text)
            sm.update_field(user_id, session.editing_field, seconds)
        except:
            await delete_error() # remove old error before sending new one
            err = await msg.reply("не понял формат, попробуй ещё раз")
            sm.update_field(user_id, 'error_message_id', err.message_id)
            await bot.delete_message(msg.chat.id, msg.message_id)
            return

    await delete_error()
    await update_info_message(bot, session, msg.chat.id)
    await bot.delete_message(msg.chat.id, session.prompt_message_id)
    await bot.delete_message(msg.chat.id, msg.message_id)

    sm.clear_editing_field(user_id)


@router.message(F.photo)
async def handle_photo_edit(msg: Message, bot: Bot):
    user_id = msg.from_user.id
    session = sm.get_session(user_id)

    if not session or session.editing_field != 'art':
        await bot.delete_message(msg.chat.id, msg.message_id)
        return

    log.info(f"[{user_id}] updating album art")
    photo_data = await uploader.download_photo(bot, msg.photo[-1].file_id, user_id)
    sm.update_field(user_id, 'album_art', photo_data)

    await update_info_message(bot, session, msg.chat.id)
    await bot.delete_message(msg.chat.id, session.prompt_message_id)
    await bot.delete_message(msg.chat.id, msg.message_id)
    sm.clear_editing_field(user_id)
    log.info(f"[{user_id}] album art updated")


@router.message(F.document)
async def handle_unexpected_document(msg: Message, bot: Bot):
    """delete files sent when not expected"""
    user_id = msg.from_user.id
    session = sm.get_session(user_id)
    if not session or session.editing_field != 'art':
        await bot.delete_message(msg.chat.id, msg.message_id)


@router.callback_query(F.data == "done")
async def handle_done(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    session = sm.get_session(user_id)
    if not session:
        await callback.answer("мммм чёт пошло не так хз")
        return

    log.info(f"[{user_id}] finalizing edit")
    status_msg = await callback.message.answer("отправка...")

    final_path = session.file_path

    # trim if needed
    if session.trim_start > 0 or session.trim_end:
        trimmed_path = session.file_path + '_trimmed.mp3'
        ap.trim_audio(session.file_path, trimmed_path,
                      session.trim_start, session.trim_end)
        final_path = trimmed_path

    log.info(f"[{user_id}] applying metadata changes")
    ap.apply_metadata(final_path, session.title, session.artist, session.album_art)

    thumb_data = None
    if session.album_art:
        art_io = ap.prepare_art_for_telegram(session.album_art)
        if art_io:
            thumb_data = art_io.read()

    await uploader.upload_audio(
        bot, callback.message.chat.id, final_path,
        session.original_file_name, thumb_bytes=thumb_data
    )

    await bot.delete_message(callback.message.chat.id, status_msg.message_id)
    await bot.delete_message(callback.message.chat.id, session.info_message_id)

    uploader.cleanup_file(session.file_path)
    if final_path != session.file_path:
        uploader.cleanup_file(final_path)

    sm.delete_session(user_id)
    log.info(f"[{user_id}] session completed")
    await callback.answer()