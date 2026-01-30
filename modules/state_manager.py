from dataclasses import dataclass

@dataclass
class EditSession:
    file_path: str
    original_file_name: str
    title: str
    artist: str
    album_art: bytes | None
    info_message_id: int
    error_message_id: int | None = None
    editing_field: str | None = None
    prompt_message_id: int | None = None
    trim_start: float = 0.0  # in seconds
    trim_end: float | None = None  # None = no trim
    downloading_msg_id: int | None = None

_sessions: dict[int, EditSession] = {}

def create_session(user_id: int, file_path: str, file_name: str,
                   title: str, artist: str, art: bytes | None,
                   msg_id: int) -> EditSession:
    session = EditSession(
        file_path=file_path,
        original_file_name=file_name,
        title=title,
        artist=artist,
        album_art=art,
        info_message_id=msg_id
    )
    _sessions[user_id] = session
    return session

def get_session(user_id: int) -> EditSession | None:
    return _sessions.get(user_id)

def delete_session(user_id: int):
    if user_id in _sessions:
        del _sessions[user_id]

def set_editing_field(user_id: int, field: str, prompt_id: int):
    if session := _sessions.get(user_id):
        session.editing_field = field
        session.prompt_message_id = prompt_id

def clear_editing_field(user_id: int):
    if session := _sessions.get(user_id):
        session.editing_field = None
        session.prompt_message_id = None

def update_field(user_id: int, field: str, value):
    if session := _sessions.get(user_id):
        setattr(session, field, value)