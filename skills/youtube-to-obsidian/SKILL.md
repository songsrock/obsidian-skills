---
name: youtube-to-obsidian
description: Summarize YouTube videos and save structured markdown notes to Obsidian. Extracts captions or transcribes audio via Whisper. Use when user sends a YouTube URL with keywords like "总结", "summarize", "obsidian", "保存", "笔记", "摘要".
compatibility: Requires uv (for PEP 723 inline dependency management), ffmpeg, and an Obsidian vault. Set OBSIDIAN_VAULT env var or default is ~/obsidian/YouTube Notes. Dependencies (yt-dlp, youtube-transcript-api, faster-whisper) are auto-installed by uv.
---

# YouTube → Obsidian Summary

Extracts transcript from YouTube (captions first, Whisper fallback), summarizes key points, and saves as a formatted markdown note in the Obsidian vault.

Supports **single videos** and **playlists**.

## Trigger Keywords

Any of these in the user's message alongside a YouTube URL:

- 总结, 摘要, 笔记, 保存, 总结到obsidian
- summarize, summary, note, save, obsidian, playlist
- A bare YouTube URL with implicit summarization intent from context

## Workflow

### Single Video

#### Step 1: Extract transcript

> Scripts are bundled in the skill directory. Use `$SKILL_DIR` to reference the skill's install path.

**Choose `--lang` based on the video title:**
- Title has Chinese characters → `--lang zh`
- Title is English → `--lang en` (default)
- If unclear, prefer `--lang zh` for channels known to be Chinese

```bash
# For Chinese videos (recommended: always specify --lang zh)
uv run --script "$SKILL_DIR/yt-transcript.py" "<youtube-url>" --output-dir "$TMPDIR/yt-summary" --lang zh

# For English videos
uv run --script "$SKILL_DIR/yt-transcript.py" "<youtube-url>" --output-dir "$TMPDIR/yt-summary"
```

> `$TMPDIR` resolves to `/tmp` on macOS/Linux and `%TEMP%` on Windows. Agents should use the platform's temp directory.

**Timeout budget:** Captions extraction is fast (<10s). Whisper fallback needs ~10s per minute of audio — for a 30-min video use `timeout=600`. If the command times out, check if captions exist for another language before retrying.

The script outputs:
- `Source: youtube_captions` if captions exist (fast, seconds)
- `Source: whisper` if it falls back to audio download + transcription (slower, minutes)
- Transcript saved to `$TMPDIR/yt-summary/<title> - transcript.txt`
- JSON metadata line with `title`, `channel`, `duration`, `date`, `url`, `transcript_path`

#### Step 2: Read transcript

```bash
read $TMPDIR/yt-summary/<title> - transcript.txt
```

#### Step 3: Summarize and save

Create a structured markdown note with:

- **YAML frontmatter**: `title`, `channel`, `url`, `duration`, `published`, `tags`
- **Structured body**: use headings, tables, bullet points, code blocks as appropriate
- **Key points only**: extract actionable insights, data, comparisons, recommendations
- **Language**: match the video's language (Chinese video → Chinese summary)

Save to:
```
$OBSIDIAN_VAULT/<title>.md    (default: ~/obsidian/YouTube Notes/)
```

#### Step 4: Cleanup

```bash
rm -rf $TMPDIR/yt-summary   # or equivalent cleanup on Windows
```

---

### Playlist

#### Step 1: Extract all transcripts (skip existing)

```bash
uv run --script "$SKILL_DIR/yt-transcript.py" "<playlist-url>" --output-dir "$TMPDIR/yt-summary"
```

Or use the wrapper:
```bash
"$SKILL_DIR/yt2obsidian.sh" "<playlist-url>"
```

The script auto-resolves the Obsidian vault (see "Obsidian Vault" section below). Pass `--obsidian-dir <path>` to override.

The script auto-detects playlist URLs (`youtube.com/playlist?list=` or `watch?v=...&list=`).
You can also pass `--playlist` to force playlist mode, or `--max N` to limit processing.

The script fetches the **playlist title** from YouTube and creates a subdirectory:
```
$OBSIDIAN_VAULT/<playlist-title>/
```

**Skip logic:** Before processing each video, the script checks if a matching note already exists in the playlist subdirectory — first by matching the `url` field in YAML frontmatter (robust), then by filename as fallback. If found, it skips transcript extraction. Pass `--no-skip` to force re-extraction.

Each new video is saved as:
```
$TMPDIR/yt-summary/01 - <title> - transcript.txt
$TMPDIR/yt-summary/02 - <title> - transcript.txt
...
```

The JSON output contains `type: "playlist"`, `playlist_title`, `playlist_dir`, `processed`, `skipped`, `total` counts, and lists all videos.

#### Step 2: Summarize only new videos

Process only the new transcripts (skipped ones already have notes):

1. `read $TMPDIR/yt-summary/<NN> - <title> - transcript.txt`
2. Summarize with the same structured format as single videos
3. Save to `$OBSIDIAN_VAULT/<playlist-title>/<title>.md` (use `playlist_dir` from JSON output)
4. After all are done, run cleanup

#### Step 3: Cleanup

```bash
rm -rf $TMPDIR/yt-summary   # or equivalent cleanup on Windows
```

## Obsidian Vault

The script resolves the vault automatically (in priority order):

1. **`OBSIDIAN_VAULT` env var** — if set, used directly
2. **Config file** (`~/.config/yt2obsidian/config.json`) — saved after first successful detection
3. **Auto-detect** — scans common locations for `.obsidian/` directories:
   - `~/obsidian`, `~/Documents/obsidian`, `~/Documents`, `~/Notes`
   - macOS: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/`
   - Windows: `%APPDATA%/obsidian`

If exactly one vault is found, it's used and saved to config. If multiple are found, the script prints the list and asks the user to choose (via env var or `--obsidian-dir`).

Notes are saved to `<vault>/YouTube Notes/` (created if needed).

## Scripts

- `uv run --script "$SKILL_DIR/yt-transcript.py"` — Extract captions or transcribe via Whisper (deps auto-installed by uv)
- `"$SKILL_DIR/yt2obsidian.sh"` — Convenience wrapper (extract + print next-step instructions, uses `uv run --script` internally)

## Language Detection Strategy

**Always inspect the video title before choosing `--lang`.** If the title contains Chinese characters, use `--lang zh`. If mixed or unclear, try `--lang zh` first for Chinese channels, then fall back to `--lang en`.

When captions are not found for the specified language, the script falls back to Whisper — but Whisper's auto-detection is unreliable for Chinese (often misdetects as English). **Specifying `--lang` is critical for reliability.**

## Known Issues

### SABR-only streaming (new videos)
YouTube may block yt-dlp audio downloads with HTTP 403 on recently published videos. Workaround:
```bash
# Download audio separately with browser cookies
yt-dlp --cookies-from-browser chrome -f "bestaudio[ext=m4a]/bestaudio" \
  -o "$TMPDIR/yt-summary/%(id)s.%(ext)s" "<url>"
# Then transcribe manually with faster-whisper (see yt-transcript for model setup)
```

### Whisper timeout
Whisper `small` model on CPU: budget ~10s per minute of audio. A 36-min video needs ~6 minutes. Default 120s timeout is insufficient for videos over ~15 mins. Use `timeout=600` for longer videos.

### Caption language fallback
If captions aren't found for `--lang en` (default), the script immediately falls to Whisper without trying other languages like `zh`. For videos that look Chinese, **always specify `--lang zh` upfront** to avoid unnecessary Whisper fallback.

## Notes

- The script handles both captioned and uncaptioned videos automatically
- Whisper uses the `small` model on CPU — budget ~10s per minute of audio
- If the video has no captions AND no spoken audio (e.g., music-only), the workflow will fail — inform the user
- Always clean up temp audio files after transcription
