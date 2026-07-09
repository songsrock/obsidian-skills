# YouTube → Obsidian Skill

Extracts transcripts from YouTube videos (captions or Whisper), summarizes key points, and saves formatted markdown notes to Obsidian.

## Setup

### 1. Prerequisites

**macOS / Linux:**
```bash
brew install uv ffmpeg
```

**Windows:**
```powershell
winget install astral-sh.uv
winget install Gyan.FFmpeg
```

No `pip install` needed — `uv run --script` handles `yt-dlp`, `youtube-transcript-api`, and `faster-whisper` automatically.

### 2. Install the skill

Copy this directory into your agent's skills folder. For example:

```bash
# Claude Code
cp -r youtube-to-obsidian ~/.claude/skills/

# Or any other agent harness that supports skill directories
cp -r youtube-to-obsidian /path/to/your/agent/skills/
```

### 3. Obsidian vault

The skill **auto-detects** your Obsidian vault on first run by scanning common locations for `.obsidian/` directories. The result is saved to `~/.config/yt2obsidian/config.json` so detection only happens once.

To override, set `OBSIDIAN_VAULT`:
```bash
# macOS / Linux
export OBSIDIAN_VAULT="$HOME/Documents/MyVault/YouTube Notes"

# Windows (PowerShell)
$env:OBSIDIAN_VAULT = "$HOME\Documents\MyVault\YouTube Notes"
```

## Usage

Send your agent a YouTube URL with keywords like "summarize", "总结", "obsidian", "笔记" — the skill loads automatically.

### Single video
```
summarize https://www.youtube.com/watch?v=...
```

### Playlist
```
summarize this playlist https://www.youtube.com/playlist?list=...
```

### Manual (CLI)
```bash
# Extract transcript only
uv run --script yt-transcript.py "https://youtube.com/watch?v=..." --lang en

# Extract + print next-step instructions (macOS/Linux, or Windows with Git Bash/WSL)
./yt2obsidian.sh "https://youtube.com/watch?v=..."
```

## Platform Notes

- **`yt-transcript` (Python)**: Cross-platform. Works on macOS, Linux, and Windows via `uv run --script`.
- **`yt2obsidian` (Bash wrapper)**: Requires a bash-compatible shell. On Windows, use Git Bash, WSL, or invoke `yt-transcript` directly.
- **Temp files**: The scripts use the system temp directory (`$TMPDIR` on Unix, `%TEMP%` on Windows). The agent is responsible for cleanup after summarization.
