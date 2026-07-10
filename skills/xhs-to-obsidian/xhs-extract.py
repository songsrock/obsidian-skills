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

def sanitize_filename(name):
    """Strip characters unsafe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()[:120]

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.gif', '.avif'}


def run(cmd, timeout=30, capture=True, check=False):
    """Run a command, return CompletedProcess. timeout=None for no limit."""
    kwargs = dict(text=True, timeout=timeout, check=check)
    if capture:
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.PIPE
    return subprocess.run(cmd, **kwargs)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obsidian_vault import resolve_vault


def _find_existing_note(obsidian_dir, note_url, safe_title):
    """Check if a note for this URL already exists. Returns path or None."""
    if not obsidian_dir or not os.path.isdir(obsidian_dir):
        return None
    note_url = note_url.split('?')[0].rstrip('/')
    for fname in os.listdir(obsidian_dir):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(obsidian_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                head = f.read(4096)
            m = re.search(r'^url:\s*(.+)$', head, re.MULTILINE)
            if m:
                saved_url = m.group(1).strip().split('?')[0].rstrip('/')
                if saved_url == note_url:
                    return fpath
        except (OSError, UnicodeDecodeError):
            continue
    # Fallback: filename match
    expected = os.path.join(obsidian_dir, f"{safe_title}.md")
    if os.path.exists(expected):
        return expected
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

def download_media(url, output_dir, retries=3):
    """Download images/video via opencli xiaohongshu download. Returns list of downloaded files."""
    print(f"  Downloading media (images/video)...", file=sys.stderr)
    t0 = time.time()

    for attempt in range(retries):
        if attempt > 0:
            delay = 2 * attempt
            print(f"  Retry {attempt}/{retries} after {delay}s...", file=sys.stderr)
            time.sleep(delay)

        result = run(
            [
                'opencli', 'xiaohongshu', 'download', url,
                '--output', output_dir,
            ],
            timeout=900,
        )
        if result.returncode == 0:
            break
        print(f"  Download attempt {attempt+1} failed: {result.stderr.strip()[:200]}", file=sys.stderr)
    else:
        print(f"  Warning: download failed after {retries} attempts", file=sys.stderr)
        return []

    print(f"  Media downloaded in {time.time() - t0:.1f}s", file=sys.stderr)

    files = []
    for root, dirs, filenames in os.walk(output_dir):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXTENSIONS or ext == '.mp4':
                files.append(os.path.join(root, fn))
    return files


# ---------------------------------------------------------------------------
# Video transcription
# ---------------------------------------------------------------------------

def transcribe_video(video_path, output_path, lang=None):
    """Extract audio from video, transcribe with faster-whisper, save transcript.
    Returns (duration_seconds, segment_count)."""
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
    segments, info = model.transcribe(audio_path, language=lang or 'zh', beam_size=5)

    seg_count = 0
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            text = seg.text.strip()
            if text:
                f.write(text + '\n')
                seg_count += 1

    duration = info.duration
    print(
        f"  Transcription complete in {time.time() - t0:.1f}s "
        f"(audio: {duration:.0f}s, {seg_count} segments)",
        file=sys.stderr,
    )

    if seg_count == 0:
        print("  Warning: Whisper produced no text (video may have no speech)", file=sys.stderr)

    os.unlink(audio_path)

    return duration, seg_count


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
    parser.add_argument(
        '--no-skip',
        action='store_true',
        help='Do not skip notes already saved in Obsidian',
    )
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        tempfile.gettempdir(), 'xhs-summary'
    )
    os.makedirs(output_dir, exist_ok=True)

    # Resolve Obsidian vault early (needed for skip check)
    if args.obsidian_dir:
        note_dir = args.obsidian_dir
    else:
        note_dir, _ = resolve_vault('小红书笔记')

    # ------------------------------------------------------------------
    # 1. Get note metadata
    # ------------------------------------------------------------------
    meta = extract_note_meta(args.url)
    title = meta.get('title', 'Untitled')
    author = meta.get('author', '')
    note_text = meta.get('content', '')

    safe_title = sanitize_filename(title)

    # ------------------------------------------------------------------
    # Skip check: see if note already exists in Obsidian
    # ------------------------------------------------------------------
    if not args.no_skip and note_dir and os.path.isdir(note_dir):
        existing = _find_existing_note(note_dir, args.url, safe_title)
        if existing:
            print(f"  Already in Obsidian: {existing}", file=sys.stderr)
            print("\n--- JSON ---")
            print(json.dumps({'skipped': True, 'title': title, 'existing': existing}, ensure_ascii=False))
            return

    content_path = os.path.join(output_dir, f'{safe_title} - content.txt')
    media_dir = os.path.join(output_dir, 'media')
    os.makedirs(media_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 2. Download media first — then determine note type from files
    # ------------------------------------------------------------------
    media_files = download_media(args.url, media_dir)
    video_files = [f for f in media_files if f.endswith('.mp4')]
    images = [f for f in media_files if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]

    # REAL note type: check downloaded media, not the API content field
    # (video notes often have a description text that looks like "content")
    note_type = 'video' if video_files else 'image'

    print(f"  Title: {title}", file=sys.stderr)
    print(f"  Author: {author}", file=sys.stderr)
    print(f"  Type: {note_type} note", file=sys.stderr)

    # ------------------------------------------------------------------
    # 3. Extract content
    # ------------------------------------------------------------------
    source = None

    if note_type == 'image':
        if not note_text.strip():
            print("  Warning: note has no text content (image-only note)", file=sys.stderr)
        with open(content_path, 'w', encoding='utf-8') as f:
            f.write(note_text)
        source = 'note_text' if note_text.strip() else 'note_text_empty'

    else:
        # Video note: transcribe the downloaded video
        video_path = video_files[0]

        # Video cover images are not meaningful — keep only transcript
        images = []

        lang = args.lang or 'zh'

        duration, seg_count = transcribe_video(video_path, content_path, lang=lang)
        source = 'whisper' if seg_count > 0 else 'whisper_empty'

        # Clean up video file immediately — only audio was needed
        os.unlink(video_path)

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
        'note_dir': note_dir,
    }
    print("\n--- JSON ---")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
