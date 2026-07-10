---
name: xhs-to-obsidian
description: Extract content from Xiaohongshu (小红书) notes and save AI-summarized markdown to Obsidian. Handles image notes (text extraction) and video notes (Whisper transcription). Use when user sends a Xiaohongshu URL with keywords like "总结", "summarize", "obsidian", "保存", "笔记", "摘要".
compatibility: This skill requires uv, ffmpeg, opencli, and Chrome logged into xiaohongshu.com. Without opencli (which handles Xiaohongshu auth/browser automation), the skill cannot extract notes. Dependencies (faster-whisper) are auto-installed by uv.
---

# 小红书 → Obsidian Summary

Extracts content from 小红书 notes (text for image notes, Whisper transcription for video notes), summarizes key points, and saves as a formatted markdown note in Obsidian.

## Trigger Keywords

Any of these in the user's message alongside a 小红书 URL (xiaohongshu.com/explore/..., xhslink.com/...):

- 总结, 摘要, 笔记, 保存, 总结到obsidian
- summarize, summary, note, save, obsidian
- A bare 小红书 URL with implicit summarization intent

## Prerequisites

| 依赖 | 用途 | 安装 |
|------|------|------|
| **opencli CLI** | 🔑 小红书登录认证 + 笔记提取 + 媒体下载 | `npm install -g opencli` |
| **opencli Chrome 扩展** | 🌉 CLI 与浏览器之间的通信桥梁 | Chrome Web Store 搜索 "opencli"（首次运行 CLI 时会提示安装） |
| Chrome | opencli 复用 Chrome 登录态 | 系统自带即可 |
| uv | Python PEP 723 脚本运行 | macOS/Linux: `brew install uv` · Windows: `winget install astral-sh.uv` |
| ffmpeg | 视频音频提取 | macOS/Linux: `brew install ffmpeg` · Windows: `winget install Gyan.FFmpeg` |

### 初始化流程

```bash
# 1. 安装 CLI
npm install -g opencli

# 2. 安装 Chrome 扩展（首次运行会提示 Web Store 链接，点击安装即可）
#    验证是否就绪：
opencli doctor

# 3. 登录小红书（会弹出 Chrome 窗口，扫码一次即可）
opencli xiaohongshu login
```

> ⚠️ 如果没有安装 opencli + Chrome 扩展 + 登录小红书，此 skill 完全无法使用。这是不同于 youtube-to-obsidian 的关键差异——后者不需要登录也不需要浏览器扩展。

## Note Types

| Type | Content extraction | Media handling |
|------|-------------------|----------------|
| 图文笔记 | Text directly from `opencli xiaohongshu note` | Download images to Obsidian assets |
| 视频笔记 | Download video → extract audio → Whisper transcribe → delete video | Only transcript kept (video + cover image discarded after audio extraction) |

> **Note type detection:** The script downloads media first, then checks for .mp4 files to determine the real note type. Video notes often have description text in the API — this is NOT used as the primary content.

## Workflow

### Step 1: Extract content

Use the bundled script. Scripts are in the skill directory — use `$SKILL_DIR` to reference the install path.

> The script auto-detects note type by checking downloaded media: if an .mp4 file is present, it's a video note (even if the API shows text content).

```bash
uv run --script "$SKILL_DIR/xhs-extract.py" "<xiaohongshu-url>" --output-dir "$TMPDIR/xhs-summary"
```

The URL must include `xsec_token` (from browser share or feed). Short links (xhslink.com) are also accepted.

**Timeout budget:**
- 图文笔记: <15s (just fetching text)
- 视频笔记: 300-600s (downloading the .mp4 + Whisper transcription)
  - Video download: ~60-120s for typical 100-300MB videos
  - Whisper transcription: ~10s per minute of video content
  - Use `timeout=900` for videos longer than 30 minutes

The script outputs JSON after a `--- JSON ---` separator:
- `source: "note_text"` for 图文笔记 with text
- `source: "note_text_empty"` for image-only notes (no text body — summarize from images instead)
- `source: "whisper"` for 视频笔记 (transcribed audio)
- `source: "whisper_empty"` for video with no speech (only title/metadata available)
- `skipped: true` if note already exists in Obsidian (skip further processing)
- Transcript/content saved to `$TMPDIR/xhs-summary/<title> - content.txt`
- Downloaded images saved to `$TMPDIR/xhs-summary/media/`
- JSON fields: `title`, `author`, `url`, `type`, `likes`, `source`, `content_path`, `images`, `note_dir`

### Step 2: Read content

```bash
read "$TMPDIR/xhs-summary/<title> - content.txt"
```

### Step 3: Summarize and save

Create a structured markdown note with:

- **YAML frontmatter**: `title`, `author`, `url`, `type`, `likes`, `published`, `tags`, `source`
- **Structured body**: use headings, tables, bullet points
- **Key points only**: extract actionable insights, core ideas, recommendations
- **Language**: match the note's language (Chinese note → Chinese summary)
- **Image references**: embed downloaded images with Obsidian wikilinks

Save to:
```
$OBSIDIAN_VAULT/<title>.md    (default: ~/obsidian/小红书笔记/)
```

### Step 4: Cleanup

```bash
rm -rf "$TMPDIR/xhs-summary"
```

## Image Notes (图文笔记)

对于 图文笔记, the script:
1. Extracts title, body text, and metadata via `opencli xiaohongshu note`
2. Downloads all images via `opencli xiaohongshu download`
3. Saves text to content file and images to `images/` subdirectory

When saving to Obsidian:
- Copy images to `$OBSIDIAN_VAULT/assets/<note-title>/`
- Use `![[assets/<note-title>/image.jpg]]` wikilinks in the markdown

## Video Notes (视频笔记)

对于 视频笔记, the script:
1. Extracts title and metadata via `opencli xiaohongshu note` (content is empty for videos)
2. Downloads the video via `opencli xiaohongshu download`
3. Extracts audio track with ffmpeg (`ffmpeg -i video.mp4 -vn -acodec pcm_s16le audio.wav`)
4. Transcribes with faster-whisper (`small` model, CPU)
5. Saves transcript to content file

⚠️ Video files are 100-500MB. The script cleans up the video after audio extraction. Only the transcript is kept.

> **Video cover images are discarded** — the cover thumbnail that downloads alongside the video is not meaningful content and is not saved to Obsidian. Only 图文 notes have their images preserved.

## Obsidian Vault

The script resolves the vault automatically (in priority order):

1. **`OBSIDIAN_VAULT` env var** — if set, used directly
2. **Config file** (`~/.config/xhs2obsidian/config.json`) — saved after first successful detection
3. **Auto-detect** — scans common locations for `.obsidian/` directories:
   - `~/obsidian`, `~/Documents/obsidian`, `~/Documents`, `~/Notes`
   - macOS: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/`
   - Windows: `%APPDATA%/obsidian`

Notes are saved to `<vault>/小红书笔记/` (created if needed).

## Scripts

- `uv run --script "$SKILL_DIR/xhs-extract.py"` — Extract note content or transcribe video (deps auto-installed by uv)

## Known Issues

### xsec_token expiration
小红书 share URLs contain `xsec_token` that expire. If the URL returns 404, ask the user to re-share the note from the app.

### Video download timeout
Video downloads are large (100-500MB). Use `timeout=900` for the extract command. If it times out, the partial download is cleaned up automatically.

### Whisper on long videos
Whisper `small` model on CPU: ~10s per minute. For 20+ min videos, the transcription alone needs 3-5 minutes. Be patient.

### Music-only videos
If the video has no spoken content (music, ambient), Whisper produces empty output. The workflow will still save a note with just title and metadata.

## Notes

- The script handles both 图文 and 视频 notes automatically
- Video files are cleaned up after audio extraction — only the transcript is preserved
- Whisper language detection is automatic (uses `--lang zh` if title contains Chinese)
- clean up temp files after summarization
