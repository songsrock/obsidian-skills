# Obsidian Skills

AI agent skills for saving and summarizing content to Obsidian.

## Skills

| Skill | Description |
|-------|-------------|
| [youtube-to-obsidian](./skills/youtube-to-obsidian/) | Extract YouTube transcripts, summarize with AI, and save structured markdown notes to Obsidian |
| [xhs-to-obsidian](./skills/xhs-to-obsidian/) | Extract 小红书 notes (text + video transcription) and save AI-summarized markdown to Obsidian |

## Install

**Ask your agent** — paste one of these into your AI agent (Claude Code, Cursor, etc.):

> Install the youtube-to-obsidian skill from github.com/songsrock/obsidian-skills

> Install the xhs-to-obsidian skill from github.com/songsrock/obsidian-skills

The agent will handle cloning and setup for you.

**Or use the CLI:**

```bash
# Install a specific skill (requires npx)
npx skills add songsrock/obsidian-skills --skill youtube-to-obsidian -g -y
npx skills add songsrock/obsidian-skills --skill xhs-to-obsidian -g -y

# List available skills
npx skills add songsrock/obsidian-skills --list
```

**Or manually:**

```bash
git clone https://github.com/songsrock/obsidian-skills.git
cp -r obsidian-skills/skills/youtube-to-obsidian ~/.claude/skills/
cp -r obsidian-skills/skills/xhs-to-obsidian ~/.claude/skills/
```

## Prerequisites

See each skill's README for specific dependencies. Common requirements:

- [uv](https://docs.astral.sh/uv/) — Python script runner (manages dependencies automatically)
- [ffmpeg](https://ffmpeg.org/) — audio/video processing (Whisper fallback)
