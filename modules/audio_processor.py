from mutagen import File
from mutagen.id3 import APIC, TIT2, TPE1
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from io import BytesIO
from PIL import Image
import subprocess


def trim_audio(input_path: str, output_path: str, start: float, end: float | None = None):
    """trim audio using ffmpeg. times in seconds."""
    cmd = ['ffmpeg', '-i', input_path, '-ss', str(start)]
    if end:
        cmd.extend(['-to', str(end)])
    cmd.extend(['-c', 'copy', '-y', output_path])
    subprocess.run(cmd, check=True, capture_output=True)

def parse_timestamp(ts: str) -> float:
    """convert '1:23.5' or '3:21.5' to seconds"""
    parts = ts.split(':')
    if len(parts) == 2:
        # m:ss.s
        return float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        # h:mm:ss.s
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(ts)


def extract_metadata(file_path: str) -> dict:
    audio = File(file_path)
    if audio is None:
        return {'title': '???', 'artist': '???'}

    def get_tag(audio_file, *keys):
        for key in keys:
            val = audio_file.get(key)
            if val:
                if isinstance(val, list) and len(val) > 0:
                    return str(val[0])
                if hasattr(val, 'text'):  # id3 tags
                    return str(val.text[0]) if val.text else None
                return str(val)
        return '???'

    title = get_tag(audio, 'TIT2', 'title', '\xa9nam')
    artist = get_tag(audio, 'TPE1', 'artist', '\xa9ART')

    return {'title': title, 'artist': artist}


def extract_album_art(file_path: str) -> bytes | None:
    audio = File(file_path)

    if isinstance(audio, MP3):
        for tag in audio.tags.values():
            if isinstance(tag, APIC):
                return tag.data
    elif isinstance(audio, FLAC):
        if audio.pictures:
            return audio.pictures[0].data

    return None


def apply_metadata(file_path: str, title: str, artist: str, art: bytes | None):
    audio = File(file_path)

    if isinstance(audio, MP3):
        if audio.tags is None:
            audio.add_tags()
        audio.tags['TIT2'] = TIT2(encoding=3, text=title)
        audio.tags['TPE1'] = TPE1(encoding=3, text=artist)

        if art:
            audio.tags['APIC'] = APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=art
            )
    elif isinstance(audio, FLAC):
        audio['title'] = title
        audio['artist'] = artist

        if art:
            pic = Picture()
            pic.type = 3
            pic.mime = 'image/jpeg'
            pic.data = art
            audio.clear_pictures()
            audio.add_picture(pic)

    audio.save()


def prepare_art_for_telegram(art_bytes: bytes | None) -> BytesIO | None:
    if not art_bytes:
        return None

    img = Image.open(BytesIO(art_bytes))
    if img.format == 'JPEG':
        return BytesIO(art_bytes)

    output = BytesIO()
    img.convert('RGB').save(output, format='JPEG')
    output.seek(0)
    return output