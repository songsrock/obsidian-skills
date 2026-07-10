# 小红书 → Obsidian Skill

Extracts content from Xiaohongshu (小红书) notes — text for image posts, Whisper transcription for video posts — summarizes key points, and saves formatted markdown notes to Obsidian.

## Setup

### 1. Prerequisites

**macOS / Linux:**
```bash
brew install uv ffmpeg
npm install -g opencli
```

**Windows:**
```powershell
winget install astral-sh.uv
winget install Gyan.FFmpeg
npm install -g opencli
```

### 2. opencli setup (required)

opencli handles Xiaohongshu authentication via your Chrome browser session:

```bash
# Install the Chrome extension (first run will prompt Web Store link)
opencli doctor

# Login to Xiaohongshu (opens Chrome, scan QR code once)
opencli xiaohongshu login
```

> Without opencli + Chrome extension + Xiaohongshu login, this skill cannot function.

### 3. Install the skill

**Ask your agent** — paste this into your AI agent (Claude Code, etc.):

> Install the xhs-to-obsidian skill from github.com/songsrock/obsidian-skills

The agent will clone the repo and copy the skill into its skills directory.

**Or install manually:**

```bash
# One-liner (requires npx)
npx skills add songsrock/obsidian-skills --skill xhs-to-obsidian -g -y

# Or manually clone and copy
git clone https://github.com/songsrock/obsidian-skills.git /tmp/obsidian-skills
cp -r /tmp/obsidian-skills/skills/xhs-to-obsidian ~/.claude/skills/
rm -rf /tmp/obsidian-skills
```

### 4. Obsidian vault

The skill **auto-detects** your Obsidian vault on first run by scanning common locations for `.obsidian/` directories. The result is saved to `~/.config/obsidian-skills/config.json`.

To override, set `OBSIDIAN_VAULT`:
```bash
# macOS / Linux
export OBSIDIAN_VAULT="$HOME/Documents/MyVault"

# Windows (PowerShell)
$env:OBSIDIAN_VAULT = "$HOME\Documents\MyVault"
```

Notes are saved to `<vault>/小红书笔记/`.

## Usage

Send your agent a Xiaohongshu URL with keywords like "保存", "总结", "笔记" — the skill loads automatically.

```
保存 https://www.xiaohongshu.com/explore/...?xsec_token=...
```

### Manual (CLI)
```bash
uv run --script xhs-extract.py "https://www.xiaohongshu.com/explore/...?xsec_token=..."
```

## Platform Notes

- **`xhs-extract.py` (Python)**: Cross-platform via `uv run --script`.
- **opencli**: Requires Chrome with the opencli extension. Works on macOS, Linux, and Windows.
- **Skip logic**: Notes already saved (matched by URL in frontmatter or filename) are skipped. Pass `--no-skip` to force re-extraction.
