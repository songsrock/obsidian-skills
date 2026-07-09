#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "faster-whisper",
# ]
# ///
"""
Extract content from a Xiaohongshu note.
Usage: uv run --script xhs-extract <xiaohongshu-url> [--output-dir <path>]

Handles both:
  - 图文 notes: direct text extraction via opencli
  - 视频 notes: download video → extract audio → Whisper transcription

Outputs:
  - Saves content/transcript as raw text
  - Downloads images to images/ subdirectory
  - Prints JSON metadata line with title, author, type, url, content_path, images
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def sanitize_filename(name):
    """Strip characters unsafe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()[:120]

def run(cmd, timeout=30, capture=True, check=False):
    """Run a command, return CompletedProcess. timeout=None for no limit."""
    kwargs = dict(text=True, timeout=timeout)
    if capture:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE
    return subprocess.run(cmd, **kwargs)

def find_obsidian_vault():
    """Find the Obsidian vault path (same logic as yt-transcript)."""
    if os.environ.get('OBSIDIAN_VAULT'):
        return os.environ['OBSIDIAN_VAULT']

    config_path = os.path.expanduser('~/.config/xhs2obsidian/config.json')
    try:
        with open(config_path) as f:
            return json.load(f)['vault']
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass

    candidates = [
        os.path.expanduser('~/obsidian'),
        os.path.expanduser('~/Documents/obsidian'),
        os.path.expanduser('~/Documents'),
        os.path.expanduser('~/Notes'),
    ]
    if sys.platform == 'darwin':
        candidates.append(
            os.path.expanduser(
                '~/Library/Mobile Documents/iCloud~md~obsidian/Documents'
            )
        )
    elif sys.platform == 'win32':
        candidates.append(os.path.join(os.environ.get('APPDATA', ''), 'obsidian'))

    vaults = []
    for c in candidates:
        if os.path.isdir(os.path.join(c, '.obsidian')):
            vaults.append(c)

    if len(vaults) == 1:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump({'vault': vaults[0]}, f)
        return vaults[0]
    elif len(vaults) > 1:
        print(
            f"Multiple vaults found: {vaults}. "
            "Set OBSIDIAN_VAULT env var or pass --obsidian-dir.",
            file=sys.stderr,
        )
        return None
    return None


# ---------------------------------------------------------------------------
# Extract note metadata via opencli
# ---------------------------------------------------------------------------

def extract_note_meta(url):
    """Call opencli xiaohongshu note and return parsed metadata dict."""
    print(f"  Fetching note metadata...", file=sys.stderr)
    t0 = time.time()
    result = run(
        ['opencli', 'xiaohongshu', 'note', url, '-f', 'json'],
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"opencli xiaohongshu note failed: {result.stderr.strip()}"
        )
    print(f"  Metadata fetched in {time.time() - t0:.1f}s", file=sys.stderr)

    data = json.loads(result.stdout)
    # Convert list of {field, value} into a dict
    meta = {}
    for item in data:
        meta[item['field']] = item.get('value', '')
    return meta


# ---------------------------------------------------------------------------
# Download images
# ---------------------------------------------------------------------------

def download_media(url, output_dir):
    """Download images/video via opencli xiaohongshu download. Returns list of downloaded files."""
    print(f"  Downloading media (images/video)...", file=sys.stderr)
    t0 = time.time()
    result = run(
        [
            'opencli', 'xiaohongshu', 'download', url,
            '--output', output_dir,
            '-f', 'json',
        ],
        timeout=900,  # generous: video can be 500MB
    )
    if result.returncode != 0:
        print(f"  Warning: download failed — {result.stderr.strip()}", file=sys.stderr)
        return []
    print(f"  Media downloaded in {time.time() - t0:.1f}s", file=sys.stderr)

    # Parse the JSON output to find downloaded files
    files = []
    for root, dirs, filenames in os.walk(output_dir):
        for fn in filenames:
            if not fn.endswith('.tmp'):
                files.append(os.path.join(root, fn))
    return files


# ---------------------------------------------------------------------------
# Video transcription
# ---------------------------------------------------------------------------

def transcribe_video(video_path, output_path, lang=None):
    """Extract audio from video, transcribe with faster-whisper, save transcript."""
    import shutil

    audio_path = video_path + '.wav'

    # 1. Extract audio with ffmpeg
    print(f"  Extracting audio with ffmpeg...", file=sys.stderr)
    t0 = time.time()
    result = run(
        [
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1',
            audio_path,
        ],
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr.strip()}")
    print(f"  Audio extracted in {time.time() - t0:.1f}s", file=sys.stderr)

    # 2. Transcribe with faster-whisper
    print(f"  Transcribing with Whisper (small model, {'zh' if lang == 'zh' else 'auto'} lang)...", file=sys.stderr)
    t0 = time.time()

    from faster_whisper import WhisperModel

    model = WhisperModel('small', device='cpu', compute_type='int8')
    segments, info = model.transcribe(audio_path, language=lang, beam_size=5)

    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            f.write(seg.text.strip() + '\n')

    duration = info.duration
    print(
        f"  Transcription complete in {time.time() - t0:.1f}s "
        f"(audio: {duration:.0f}s)",
        file=sys.stderr,
    )

    # Clean up audio
    os.unlink(audio_path)

    return info.duration


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Extract content from Xiaohongshu note'
    )
    parser.add_argument('url', help='Xiaohongshu note URL (with xsec_token)')
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Output directory (default: system temp)',
    )
    parser.add_argument(
        '--lang',
        default=None,
        help='Whisper language hint for video notes (zh, en, auto)',
    )
    parser.add_argument(
        '--obsidian-dir',
        default=None,
        help='Obsidian vault path (overrides auto-detect)',
    )
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        tempfile.gettempdir(), 'xhs-summary'
    )
    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Get note metadata
    # ------------------------------------------------------------------
    meta = extract_note_meta(args.url)
    title = meta.get('title', 'Untitled')
    author = meta.get('author', '')
    content = meta.get('content', '')
    note_type = 'video' if not content else 'image'

    print(f"  Title: {title}", file=sys.stderr)
    print(f"  Author: {author}", file=sys.stderr)
    print(f"  Type: {note_type} note", file=sys.stderr)

    safe_title = sanitize_filename(title)
    content_path = os.path.join(output_dir, f'{safe_title} - content.txt')
    media_dir = os.path.join(output_dir, 'media')
    os.makedirs(media_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 2. Extract content
    # ------------------------------------------------------------------
    source = None
    images = []

    if note_type == 'image':
        # Direct text extraction
        with open(content_path, 'w', encoding='utf-8') as f:
            f.write(content)
        source = 'note_text'

        # Download images
        media_files = download_media(args.url, media_dir)
        images = [f for f in media_files if not f.endswith('.mp4')]

    else:
        # Video note: download, extract audio, transcribe
        media_files = download_media(args.url, media_dir)
        video_files = [f for f in media_files if f.endswith('.mp4')]
        images = [f for f in media_files if not f.endswith('.mp4')]

        if not video_files:
            print("  Warning: no video file found after download", file=sys.stderr)
            # Still create a content file with just metadata
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(f"标题: {title}\n作者: {author}\n(视频下载失败)\n")
            source = 'metadata_only'
        else:
            # Use the first (and usually only) video
            video_path = video_files[0]

            # Determine language for Whisper
            lang = args.lang
            if not lang:
                lang = 'zh' if _has_chinese(title) else None

            duration = transcribe_video(video_path, content_path, lang=lang)
            source = 'whisper'

            # Clean up video file (too large to keep)
            os.unlink(video_path)

    # ------------------------------------------------------------------
    # 3. Resolve Obsidian vault
    # ------------------------------------------------------------------
    vault = args.obsidian_dir or find_obsidian_vault()

    # ------------------------------------------------------------------
    # 4. Output metadata as JSON
    # ------------------------------------------------------------------
    output = {
        'title': title,
        'author': author,
        'url': args.url,
        'type': note_type,
        'likes': meta.get('likes', ''),
        'collects': meta.get('collects', ''),
        'comments': meta.get('comments', ''),
        'source': source,
        'content_path': content_path,
        'images': images,
        'output_dir': output_dir,
        'obsidian_vault': vault,
        'note_dir': os.path.join(vault or '', '小红书笔记') if vault else None,
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
