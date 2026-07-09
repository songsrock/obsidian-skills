#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "yt-dlp",
#     "youtube-transcript-api",
#     "faster-whisper",
# ]
# ///
"""
Extract transcript and metadata from a YouTube video.
Usage: uv run --script yt-transcript <youtube-url> [--lang en] [--output-dir <path>]

Outputs:
  - Saves transcript as raw text
  - Prints video metadata (title, channel, duration, URL)
  - If no captions available, falls back to downloading audio + Whisper transcription
"""
import argparse
import json

class NoTranscriptError(RuntimeError):
    """No captions available. whisper_lang hints the language to use for Whisper fallback."""
    def __init__(self, msg, whisper_lang=None):
        super().__init__(msg)
        self.whisper_lang = whisper_lang
import os
import re
import sys
import tempfile
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

def _has_chinese(text):
    """Check if text contains Chinese characters."""
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def is_playlist_url(url):
    """Check if URL is a playlist."""
    return bool(re.search(r'(?:youtube\.com/playlist\?list=|youtube\.com/watch\?.*&list=)', url))

def get_playlist_info(url):
    """Extract playlist metadata + all video IDs from a YouTube playlist.
    Returns (playlist_title, playlist_uploader, video_ids)."""
    print(f"  Fetching playlist entries...", file=sys.stderr)
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = info.get('entries', [])
        playlist_title = info.get('title', '') or info.get('playlist_title', '') or 'YouTube Playlist'
        playlist_uploader = info.get('uploader', '') or info.get('playlist_uploader', '')
        video_ids = []
        for entry in entries:
            if entry:
                vid = entry.get('id') or entry.get('url', '')
                if vid and len(vid) == 11:
                    video_ids.append(vid)
        return (playlist_title, playlist_uploader, video_ids)

def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

def get_metadata(url):
    """Get video metadata using yt-dlp."""
    opts = {'quiet': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'title': info.get('title', 'Untitled'),
            'channel': info.get('uploader', 'Unknown'),
            'channel_url': info.get('uploader_url', ''),
            'duration': info.get('duration', 0),
            'upload_date': info.get('upload_date', ''),
            'url': info.get('webpage_url', url),
            'description': info.get('description', ''),
        }

def get_transcript(video_id, lang='en'):
    """Get transcript using youtube-transcript-api. Returns (text, source).
    Tries language variants (e.g., 'zh' → 'zh-CN', 'zh-TW') before falling back."""
    # Language code variants for broader matching
    lang_variants = {
        'zh': ['zh-CN', 'zh-TW', 'zh-Hans', 'zh-Hant', 'zh'],
        'en': ['en-US', 'en-GB', 'en'],
        'ja': ['ja-JP', 'ja'],
        'ko': ['ko-KR', 'ko'],
        'fr': ['fr-FR', 'fr'],
        'de': ['de-DE', 'de'],
        'es': ['es-ES', 'es-MX', 'es'],
    }
    languages_to_try = lang_variants.get(lang, [lang])

    api = YouTubeTranscriptApi()
    for l in languages_to_try:
        try:
            transcript = api.fetch(video_id, languages=[l])
            break
        except Exception:
            continue
    else:
        # Fallback: if user specified non-Chinese, try Chinese captions before Whisper.
        # Many Chinese YouTube channels have zh captions but won't match 'en' queries.
        if lang != 'zh':
            for l in lang_variants.get('zh', ['zh']):
                try:
                    transcript = api.fetch(video_id, languages=[l])
                    print(f"  (captions found via zh fallback: {l})", file=sys.stderr)
                    break
                except Exception:
                    continue
            else:
                # zh fallback also failed — raise with hint so Whisper uses zh
                try:
                    transcript = api.fetch(video_id)
                except Exception:
                    raise NoTranscriptError(
                        f"No transcript available for {video_id}",
                        whisper_lang='zh'
                    )
        else:
            try:
                transcript = api.fetch(video_id)
            except Exception:
                raise NoTranscriptError(
                    f"No transcript available for {video_id}",
                    whisper_lang=lang
                )

    full_text = ' '.join(
        entry.text if hasattr(entry, 'text') else entry['text']
        for entry in transcript
    )
    return full_text


def transcribe_whisper(audio_path, model_size='small', lang=None):
    """Transcribe audio with faster-whisper. Returns full text."""
    from faster_whisper import WhisperModel

    print(f"  Loading Whisper model '{model_size}'...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"  Transcribing audio ({os.path.getsize(audio_path) / 1024 / 1024:.1f}MB)...", file=sys.stderr)
    transcribe_args = {"beam_size": 5}
    if lang:
        transcribe_args["language"] = lang

    segments, info = model.transcribe(audio_path, **transcribe_args)
    print(f"  Detected: {info.language} (p={info.language_probability:.2f})", file=sys.stderr)

    full_text = []
    for seg in segments:
        full_text.append(seg.text.strip())
        mins, secs = divmod(int(seg.end), 60)
        print(f"\r  [{mins}:{secs:02d}]", end="", file=sys.stderr)

    print(file=sys.stderr)
    return ' '.join(full_text)


def download_audio(url, output_dir):
    """Download audio with yt-dlp. Returns path to audio file."""
    print("  Downloading audio...", file=sys.stderr)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': out_template,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.join(output_dir, f"{info['id']}.{info.get('ext', 'm4a')}")

def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def find_existing_note(obsidian_dir, video_url):
    """Check if a note for this video URL already exists in obsidian_dir.
    Scans YAML frontmatter of all .md files for matching url field.
    Returns the matching note path, or None."""
    if not obsidian_dir or not os.path.isdir(obsidian_dir):
        return None
    # Normalize URL (strip trailing slash, etc.)
    video_url = video_url.rstrip('/')
    for fname in os.listdir(obsidian_dir):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(obsidian_dir, fname)
        try:
            with open(fpath, 'r') as f:
                content = f.read(4096)  # frontmatter is at the top
                # Match YAML frontmatter url field: url: https://...
                m = re.search(r'^url:\s*(.+)$', content, re.MULTILINE)
                if m:
                    note_url = m.group(1).strip().rstrip('/')
                    if note_url == video_url:
                        return fpath
        except Exception:
            continue
    return None

def process_video(url, lang, out_dir, index=None, total=None, obsidian_dir=None):
    """Extract transcript for a single video. Returns (meta_json_dict, transcript_source).
    If obsidian_dir is set and a matching .md note already exists, returns ('skipped', None)."""
    video_id = extract_video_id(url)
    if not video_id:
        print(f"  Error: Could not extract video ID from: {url}", file=sys.stderr)
        return None, None

    # Get metadata
    meta = get_metadata(url)
    duration_str = format_duration(meta['duration'])
    date_str = meta['upload_date']
    if len(date_str) == 8:
        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    safe_title = re.sub(r'[<>:"/\\|?*]', '-', meta['title']).strip()[:80]

    prefix = ""
    if index is not None and total is not None:
        prefix = f"[{index}/{total}] "

    # Check if already summarized (by URL in frontmatter, then fallback to filename)
    # Also checks parent dir (e.g., notes moved from root into playlist subdir later)
    dirs_to_check = [obsidian_dir] if obsidian_dir else []
    if obsidian_dir:
        parent = os.path.dirname(obsidian_dir)
        if parent != obsidian_dir and os.path.isdir(parent):
            dirs_to_check.append(parent)

    for check_dir in dirs_to_check:
        if not check_dir or not os.path.isdir(check_dir):
            continue
        # Try URL match first
        existing = find_existing_note(check_dir, meta['url'])
        if existing:
            print(f"\n  {prefix}{meta['title']}  ⏭️  already in Obsidian (matched by URL), skipping", file=sys.stderr)
            return ('skipped', {
                'title': meta['title'],
                'channel': meta['channel'],
                'duration': duration_str,
                'date': date_str,
                'url': meta['url'],
                'note_path': existing,
            })
        # Fallback: filename match
        expected_note = os.path.join(check_dir, f"{safe_title}.md")
        if os.path.exists(expected_note):
            print(f"\n  {prefix}{meta['title']}  ⏭️  already in Obsidian (matched by filename), skipping", file=sys.stderr)
            return ('skipped', {
                'title': meta['title'],
                'channel': meta['channel'],
                'duration': duration_str,
                'date': date_str,
                'url': meta['url'],
                'note_path': expected_note,
            })

    print(f"\n  {prefix}{meta['title']}", file=sys.stderr)

    # Get transcript (try captions first, then whisper fallback)
    transcript_source = 'youtube_captions'
    try:
        transcript = get_transcript(video_id, lang)
    except NoTranscriptError as e:
        print("    No captions. Falling back to Whisper...", file=sys.stderr)
        audio_path = download_audio(url, tempfile.gettempdir())
        try:
            # Use hint from caption fallback, but verify against title.
            # e.whisper_lang='zh' means zh fallback was tried — likely Chinese video.
            # But if title has no Chinese chars, trust the original lang instead.
            whisper_lang = e.whisper_lang or lang
            if whisper_lang == 'zh' and not _has_chinese(meta['title']):
                whisper_lang = lang  # title doesn't look Chinese, don't force zh
            transcript = transcribe_whisper(audio_path, model_size='small', lang=whisper_lang)
            transcript_source = 'whisper'
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    os.makedirs(out_dir, exist_ok=True)

    # Save transcript with optional index prefix
    if index is not None:
        fname = f"{index:02d} - {safe_title} - transcript.txt"
    else:
        fname = f"{safe_title} - transcript.txt"
    transcript_path = os.path.join(out_dir, fname)

    with open(transcript_path, 'w') as f:
        f.write(f"# {meta['title']}\n")
        f.write(f"**Channel:** {meta['channel']}\n")
        f.write(f"**Duration:** {duration_str}\n")
        f.write(f"**Published:** {date_str}\n")
        f.write(f"**URL:** {meta['url']}\n\n")
        f.write("---\n\n")
        f.write(transcript)

    print(f"    Saved: {fname}  ({len(transcript):,} chars, {transcript_source})", file=sys.stderr)

    meta_dict = {
        'title': meta['title'],
        'channel': meta['channel'],
        'duration': duration_str,
        'date': date_str,
        'url': meta['url'],
        'transcript_path': transcript_path,
        'transcript_chars': len(transcript),
        'transcript_source': transcript_source,
    }
    return meta_dict, transcript_source


CONFIG_DIR = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config')), 'yt2obsidian')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


def _find_obsidian_vaults():
    """Scan common locations for directories containing .obsidian/. Returns list of paths."""
    home = os.path.expanduser('~')
    candidates = [
        os.path.join(home, 'obsidian'),
        os.path.join(home, 'Obsidian'),
        os.path.join(home, 'Documents', 'obsidian'),
        os.path.join(home, 'Documents', 'Obsidian'),
        os.path.join(home, 'Documents'),
        os.path.join(home, 'Notes'),
        os.path.join(home, 'notes'),
    ]
    if sys.platform == 'darwin':
        candidates.append(os.path.join(home, 'Library', 'Mobile Documents', 'iCloud~md~obsidian', 'Documents'))
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            candidates.append(os.path.join(appdata, 'obsidian'))

    vaults = []
    seen = set()
    for base in candidates:
        resolved = os.path.realpath(base)
        if resolved in seen or not os.path.isdir(resolved):
            continue
        seen.add(resolved)
        if os.path.isdir(os.path.join(resolved, '.obsidian')):
            vaults.append(resolved)
        else:
            try:
                for entry in os.scandir(resolved):
                    if entry.is_dir() and os.path.isdir(os.path.join(entry.path, '.obsidian')):
                        rp = os.path.realpath(entry.path)
                        if rp not in seen:
                            seen.add(rp)
                            vaults.append(rp)
            except PermissionError:
                continue
    return vaults


def resolve_obsidian_dir():
    """Resolve the Obsidian YouTube Notes directory. Priority:
    1. OBSIDIAN_VAULT env var
    2. Saved config file
    3. Auto-detect vault and save to config
    Returns (path, needs_user_confirmation: bool). If multiple vaults found and no
    config exists, returns (None, True) — caller should ask the user."""
    env_val = os.environ.get('OBSIDIAN_VAULT')
    if env_val:
        path = os.path.join(env_val, 'YouTube Notes') if 'YouTube' not in env_val else env_val
        return path, False

    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            saved = cfg.get('obsidian_dir')
            if saved and os.path.isdir(os.path.dirname(saved)):
                return saved, False
        except (json.JSONDecodeError, OSError):
            pass

    vaults = _find_obsidian_vaults()
    if len(vaults) == 1:
        yt_dir = os.path.join(vaults[0], 'YouTube Notes')
        _save_config(yt_dir)
        print(f"  Auto-detected vault: {vaults[0]}", file=sys.stderr)
        print(f"  Notes will be saved to: {yt_dir}", file=sys.stderr)
        print(f"  (saved to {CONFIG_FILE})", file=sys.stderr)
        return yt_dir, False
    elif len(vaults) > 1:
        print(f"  Multiple Obsidian vaults found:", file=sys.stderr)
        for i, v in enumerate(vaults, 1):
            print(f"    {i}. {v}", file=sys.stderr)
        print(f"  Set OBSIDIAN_VAULT env var or pass --obsidian-dir to choose.", file=sys.stderr)
        return None, True
    else:
        default = os.path.join(os.path.expanduser('~'), 'obsidian', 'YouTube Notes')
        print(f"  No Obsidian vault found. Using default: {default}", file=sys.stderr)
        print(f"  Set OBSIDIAN_VAULT env var to override.", file=sys.stderr)
        return default, False


def _save_config(obsidian_dir):
    """Save resolved obsidian_dir to config file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'obsidian_dir': obsidian_dir}, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Extract YouTube transcript')
    parser.add_argument('url', help='YouTube URL (single video or playlist)')
    parser.add_argument('--lang', default='en', help='Transcript language (default: en)')
    parser.add_argument('--output-dir', default=None, help='Save transcript to directory')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--playlist', action='store_true', help='Force playlist mode')
    parser.add_argument('--max', type=int, default=0, help='Max videos to process from playlist (0=all)')
    parser.add_argument('--obsidian-dir', default=None, help='Obsidian YouTube Notes dir (skip if note exists)')
    parser.add_argument('--no-skip', action='store_true', help='Do not skip already-summarized videos')
    args = parser.parse_args()

    out_dir = args.output_dir or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    if args.no_skip:
        obsidian_dir = None
    elif args.obsidian_dir:
        obsidian_dir = args.obsidian_dir
    else:
        obsidian_dir, _ = resolve_obsidian_dir()

    # Detect playlist URLs
    is_playlist = args.playlist or is_playlist_url(args.url)

    if is_playlist:
        # ---- Playlist mode ----
        playlist_title, playlist_uploader, video_ids = get_playlist_info(args.url)
        if not video_ids:
            print(f"Error: No videos found in playlist: {args.url}", file=sys.stderr)
            sys.exit(1)

        if args.max > 0:
            video_ids = video_ids[:args.max]

        # Create a subdirectory for this playlist under the obsidian dir
        safe_playlist = re.sub(r'[<>:"/\\|?*]', '-', playlist_title).strip()[:80]
        playlist_obsidian_dir = None
        if obsidian_dir and os.path.isdir(obsidian_dir):
            playlist_obsidian_dir = os.path.join(obsidian_dir, safe_playlist)

        print(f"Playlist: \"{playlist_title}\" — {len(video_ids)} videos", file=sys.stderr)

        summaries = []
        skipped = []
        for i, vid in enumerate(video_ids):
            video_url = f"https://www.youtube.com/watch?v={vid}"
            meta_dict, source = process_video(video_url, args.lang, out_dir, index=i+1, total=len(video_ids), obsidian_dir=playlist_obsidian_dir)
            if meta_dict == 'skipped':
                skipped.append(source)
            elif meta_dict:
                summaries.append(meta_dict)

        # Print combined JSON summary
        playlist_json = json.dumps({
            'type': 'playlist',
            'playlist_title': playlist_title,
            'playlist_uploader': playlist_uploader,
            'playlist_dir': playlist_obsidian_dir,
            'total': len(video_ids),
            'processed': len(summaries),
            'skipped': len(skipped),
            'videos': summaries,
            'skipped_videos': skipped,
        }, ensure_ascii=False)
        print(f"\n--- JSON ---")
        print(playlist_json)
        summary_line = f"Done: {len(summaries)} new, {len(skipped)} skipped, {len(video_ids)} total"
        print(f"\n{summary_line}")
        if playlist_obsidian_dir:
            print(f"Notes → {playlist_obsidian_dir}")
        return

    # ---- Single video mode ----
    video_id = extract_video_id(args.url)
    if not video_id:
        print(f"Error: Could not extract video ID from URL: {args.url}", file=sys.stderr)
        sys.exit(1)

    meta = get_metadata(args.url)
    duration_str = format_duration(meta['duration'])
    date_str = meta['upload_date']
    if len(date_str) == 8:
        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    safe_title = re.sub(r'[<>:"/\\|?*]', '-', meta['title']).strip()[:80]

    # --json mode: output transcript as JSON, no file saved
    if args.json:
        video_id = extract_video_id(args.url)
        try:
            transcript = get_transcript(video_id, args.lang)
        except NoTranscriptError as e:
            print("  No captions. Falling back to Whisper...", file=sys.stderr)
            audio_path = download_audio(args.url, tempfile.gettempdir())
            try:
                whisper_lang = e.whisper_lang or args.lang
                if whisper_lang == 'zh' and not _has_chinese(meta['title']):
                    whisper_lang = args.lang
                transcript = transcribe_whisper(audio_path, model_size='small', lang=whisper_lang)
            finally:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        result = {**meta, 'transcript': transcript, 'video_id': video_id, 'duration_formatted': duration_str, 'upload_date_formatted': date_str}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Standard single video mode
    meta_dict, source = process_video(args.url, args.lang, out_dir)
    if meta_dict is None:
        sys.exit(1)

    print(f"\n--- Video Info ---")
    print(f"Title:    {meta['title']}")
    print(f"Channel:  {meta['channel']}")
    print(f"Duration: {duration_str}")
    print(f"Date:     {date_str}")
    print(f"URL:      {meta['url']}")
    print(f"Transcript length: {meta_dict['transcript_chars']:,} chars")

    meta_json = json.dumps(meta_dict, ensure_ascii=False)
    print(f"\n--- JSON ---")
    print(meta_json)

if __name__ == '__main__':
    main()
