#!/bin/bash
# yt2obsidian - Extract YouTube transcript and prepare for Obsidian
# Usage: yt2obsidian <youtube-url> [--lang en] [--playlist] [--max N]
#
# Supports single videos and playlists.
# Skips videos that already have notes in Obsidian (pass --no-skip to override).
# Output: saves transcript(s) to $TMPDIR/yt-summary/ and prints a prompt for the agent to summarize.

SCRIPT="$(dirname "$0")/yt-transcript.py"
TMPDIR="${TMPDIR:-/tmp}/yt-summary"

mkdir -p "$TMPDIR"

# Let yt-transcript handle vault discovery (auto-detect or config file).
# Only pass --obsidian-dir if OBSIDIAN_VAULT is explicitly set.
OBSIDIAN_ARGS=""
if [ -n "$OBSIDIAN_VAULT" ]; then
    OBSIDIAN_ARGS="--obsidian-dir $OBSIDIAN_VAULT"
fi

# Extract transcript(s) - uses uv run --script to auto-install PEP 723 dependencies
OUTPUT=$(uv run --script "$SCRIPT" "$@" --output-dir "$TMPDIR" $OBSIDIAN_ARGS 2>&1)
echo "$OUTPUT"

# Extract the JSON line for metadata
META=$(echo "$OUTPUT" | grep -A1 '^--- JSON ---$' | tail -1)

# Check if it's a playlist (JSON has "type": "playlist")
TYPE=$(echo "$META" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('type','video'))" 2>/dev/null)

if [ "$TYPE" = "playlist" ]; then
    # Playlist: extract all video entries
    PLAYLIST_DIR=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin).get('playlist_dir',''))" 2>/dev/null)
    echo ""
    echo "=== Playlist Summary ==="
    TOTAL=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])" 2>/dev/null)
    NEW=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin)['processed'])" 2>/dev/null)
    SKIPPED=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin)['skipped'])" 2>/dev/null)
    echo "$NEW new, $SKIPPED skipped, $TOTAL total"
    if [ "$SKIPPED" -gt 0 ]; then
        echo ""
        echo "Skipped (already in Obsidian):"
        echo "$META" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for v in d.get('skipped_videos',[]):
    print(f'  ⏭️  {v[\"title\"]}')"
    fi
    echo ""
    echo "To summarize new videos and save to Obsidian:"
    echo ""
    echo "  For each transcript in $TMPDIR/*-transcript.txt (sorted): read it, summarize as markdown with frontmatter, save to '$PLAYLIST_DIR/<title>.md'"
else
    # Single video
    TRANSCRIPT=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin)['transcript_path'])" 2>/dev/null)

    echo ""
    echo "=== Next step ==="
    echo "To summarize and save to Obsidian:"
    echo ""
    echo "  Read $TRANSCRIPT, summarize key points as a concise markdown note with frontmatter (title, channel, url, duration, published, tags), then save to the Obsidian vault."
    echo ""
    echo "Transcript: $TRANSCRIPT"
fi
